import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import complete_upload, create_token, get_token_info


@pytest.mark.asyncio
async def test_token_info_and_initiate():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000)
        token = token_data["token"]

        info = await get_token_info(client, token)
        assert info["remaining_uploads"] == 1, "Token should have 1 remaining upload"

        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
                "filename": "file.txt",
                "size_bytes": 10,
            },
        )
        body = init.json()
        print(f"init response: {body}")
        assert init.status_code == status.HTTP_201_CREATED, "Initiate upload should return 201"
        assert isinstance(body["upload_id"], str) and len(body["upload_id"]) > 0, "Upload ID should be a non-empty string"

        assert body["remaining_uploads"] == 0, "Remaining uploads should decrease to 0"
        assert body["recommended_chunk_bytes"] == 10, "Initiate should recommend a chunk size aligned to the file size"

        tus_head_url = app.url_path_for("tus_head", upload_id=body["upload_id"])
        head = await client.head(tus_head_url)
        assert head.status_code == status.HTTP_200_OK, "TUS HEAD should return 200"
        assert head.headers["Upload-Offset"] == "0", "Initial upload offset should be 0"
        assert head.headers["Upload-Length"] == "10", "Upload length should match size_bytes"


@pytest.mark.asyncio
async def test_upload_requires_explicit_completion_without_resending_token():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000)
        token = token_data["token"]

        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
                "filename": "file.txt",
                "filetype": "text/plain",
                "size_bytes": 5,
            },
        )
        assert init.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_id = init.json()["upload_id"]

        patch = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=b"hello",
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": "5",
            },
        )
        assert patch.status_code == status.HTTP_204_NO_CONTENT, "TUS PATCH should accept the uploaded bytes"

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            result = await session.execute(stmt)
            record = result.scalar_one()
            assert record.status == "in_progress", "Upload should remain incomplete until the explicit completion call"
            assert record.completed_at is None, "Upload should not have a completion timestamp before completion"

        complete_status, complete_data = await complete_upload(client, upload_id)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should finalize uploaded files"
        assert complete_data["status"] == "completed", "Text upload should be marked completed after explicit completion"


@pytest.mark.asyncio
async def test_token_info_exposes_recommended_chunk_size_for_resume():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=2000)
        token = token_data["token"]

        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
                "filename": "resume.txt",
                "filetype": "text/plain",
                "size_bytes": 1500,
            },
        )
        assert init.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_id = init.json()["upload_id"]

        info = await get_token_info(client, token)
        upload_row = next(upload for upload in info["uploads"] if upload["public_id"] == upload_id)
        assert upload_row["recommended_chunk_bytes"] == 1500, "Token info should expose the recommended chunk size for resumed uploads"
