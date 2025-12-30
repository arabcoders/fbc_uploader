"""Tests for mimetype validation during upload."""

import shutil
from pathlib import Path
from fastapi import status

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.main import app


@pytest.mark.asyncio
async def test_mimetype_spoofing_rejected():
    """Test that files with fake mimetypes are rejected after upload."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Video Only",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["video/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED, "Token creation should return 201"
        token_data = resp.json()
        token_value = token_data["token"]

        fake_video = b"This is actually a text file, not a video!"

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "test.mp4",
                "filetype": "video/mp4",
                "size_bytes": len(fake_video),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=fake_video,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(fake_video)),
            },
        )

        assert patch_resp.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Fake video file should be rejected with 415"
        assert "does not match allowed types" in patch_resp.json()["detail"], "Error should indicate type mismatch"

        head_resp = await client.head(app.url_path_for("tus_head", upload_id=upload_id))
        assert head_resp.status_code == status.HTTP_404_NOT_FOUND, "Rejected upload should be removed"


@pytest.mark.asyncio
async def test_valid_mimetype_accepted():
    """Test that files with correct mimetypes are accepted."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Text Only",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["text/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED, "Token creation should return 201"
        token_data = resp.json()
        token_value = token_data["token"]

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": 20,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        text_content = b"This is a text file."

        head_resp = await client.head(app.url_path_for("tus_head", upload_id=upload_id))
        assert head_resp.status_code == status.HTTP_200_OK, "TUS HEAD should return 200"

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )

        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Valid text file should be accepted"

        head_resp = await client.head(app.url_path_for("tus_head", upload_id=upload_id))
        assert head_resp.status_code == status.HTTP_200_OK, "Upload should still exist after completion"


@pytest.mark.asyncio
async def test_mimetype_updated_on_completion():
    """Test that mimetype is updated with detected value on completion."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Unrestricted",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED, "Token creation should return 201"
        token_data = resp.json()
        token_value = token_data["token"]

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "test.txt",
                "filetype": "application/octet-stream",
                "size_bytes": 20,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        text_content = b"This is a text file."

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Upload completion should return 204"

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None, "Upload record should exist"
            assert upload.mimetype.startswith("text/"), "Mimetype should be detected as text"


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not available")
async def test_ffprobe_extracts_metadata_for_video():
    """Test that ffprobe metadata is extracted for video files."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Video Upload",
                "max_size_bytes": 50_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["video/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED, "Token creation should return 201"
        token_data = resp.json()
        token_value = token_data["token"]

        file = Path(__file__).parent / "fixtures" / "sample.mp4"

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "sample.mp4",
                "filetype": "video/mp4",
                "size_bytes": file.stat().st_size,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=file.read_bytes(),
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(file.stat().st_size),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Video upload should complete successfully"

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None, "Upload record should exist"
            assert upload.mimetype == "video/mp4", "Mimetype should be video/mp4"
            assert upload.meta_data is not None, "Metadata should be extracted"
            if "ffprobe" in upload.meta_data:
                assert isinstance(upload.meta_data["ffprobe"], dict), "ffprobe data should be a dict"
                assert "format" in upload.meta_data["ffprobe"] or "streams" in upload.meta_data["ffprobe"], (
                    "ffprobe should contain format or streams info"
                )


@pytest.mark.asyncio
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not available")
async def test_ffprobe_not_run_for_non_multimedia():
    """Test that ffprobe is not run for non-multimedia files."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Text Upload",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == status.HTTP_201_CREATED, "Token creation should return 201"
        token_data = resp.json()
        token_value = token_data["token"]

        text_content = b"This is just text content, not multimedia."
        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": len(text_content),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Text upload should complete successfully"

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None, "Upload record should exist"
            assert upload.mimetype.startswith("text/"), "Mimetype should be text"
            assert upload.meta_data is not None, "Metadata should exist"
            assert "ffprobe" not in upload.meta_data, "ffprobe should not run for text files"
