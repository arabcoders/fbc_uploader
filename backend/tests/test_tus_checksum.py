import base64
import hashlib

import pytest
from fastapi import status

from backend.app.main import app
from backend.tests.utils import complete_upload, create_token, initiate_upload, tus_head

HTTP_460_CHECKSUM_MISMATCH = 460


def _upload_checksum_header(content: bytes, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm, content).digest()
    return f"{algorithm} {base64.b64encode(digest).decode()}"


@pytest.mark.asyncio
async def test_tus_options_advertises_checksum_support(client):
    resp = await client.options(app.url_path_for("tus_options"))

    assert resp.status_code == status.HTTP_204_NO_CONTENT, "TUS OPTIONS should return 204"
    assert resp.headers["Tus-Extension"] == "creation,termination,checksum", "TUS OPTIONS should advertise checksum support"
    assert resp.headers["Tus-Checksum-Algorithm"] == "sha1,sha256", "TUS OPTIONS should list supported checksum algorithms"


@pytest.mark.asyncio
async def test_tus_patch_checksum_mismatch_keeps_offset_unchanged(client):
    token_data = await create_token(client, max_uploads=1, max_size_bytes=1000)
    upload_data = await initiate_upload(client, token_data["token"], filename="test.txt", size_bytes=5, meta_data={})
    upload_id = upload_data["upload_id"]

    patch_resp = await client.patch(
        app.url_path_for("tus_patch", upload_id=upload_id),
        content=b"hello",
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
            "Content-Length": "5",
            "Upload-Checksum": _upload_checksum_header(b"world"),
        },
    )

    assert patch_resp.status_code == HTTP_460_CHECKSUM_MISMATCH, "PATCH should reject chunks whose checksum does not match"

    head_status, head_headers = await tus_head(client, upload_id)

    assert head_status == status.HTTP_200_OK, "HEAD should still succeed after checksum mismatch"
    assert head_headers["upload-offset"] == "0", "Checksum mismatch should not advance the upload offset"


@pytest.mark.asyncio
async def test_tus_patch_checksum_success_records_uploaded_file_digest(client):
    token_data = await create_token(client, max_uploads=1, max_size_bytes=1000)
    upload_data = await initiate_upload(client, token_data["token"], filename="test.txt", size_bytes=5, meta_data={})
    upload_id = upload_data["upload_id"]
    content = b"hello"

    patch_resp = await client.patch(
        app.url_path_for("tus_patch", upload_id=upload_id),
        content=content,
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": "0",
            "Content-Length": str(len(content)),
            "Upload-Checksum": _upload_checksum_header(content),
        },
    )

    assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "PATCH should accept chunks whose checksum matches"

    head_status, head_headers = await tus_head(client, upload_id)

    assert head_status == status.HTTP_200_OK, "HEAD should succeed after a checksum-verified PATCH"
    assert head_headers["upload-offset"] == str(len(content)), "Successful checksum verification should advance the upload offset"

    complete_status, complete_data = await complete_upload(client, upload_id, token_data["token"])

    assert complete_status == status.HTTP_200_OK, "Completion should succeed after checksum-verified upload"
    assert complete_data["meta_data"]["upload_checksums"]["patch_algorithm"] == "sha256", (
        "Completion response should retain the algorithm used for PATCH checksums"
    )
    assert complete_data["meta_data"]["upload_checksums"]["file"]["algorithm"] == "sha256", (
        "Completion response should record the uploaded file digest algorithm"
    )
    assert complete_data["meta_data"]["upload_checksums"]["file"]["digest"] == hashlib.sha256(content).hexdigest(), (
        "Completion response should include the digest of the uploaded bytes"
    )
