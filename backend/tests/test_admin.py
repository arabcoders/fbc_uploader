import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import create_token, initiate_upload


@pytest.mark.asyncio
async def test_admin_validate():
    """Test admin API key validation endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.get(
            app.url_path_for("validate_api_key"),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == status.HTTP_200_OK, "Valid API key via header should return 200"
        assert r.json() == {"status": True}, "Valid API key should return status True"

        r = await client.get(
            app.url_path_for("validate_api_key"),
            params={"api_key": settings.admin_api_key},
        )
        assert r.status_code == status.HTTP_200_OK, "Valid API key via query param should return 200"
        assert r.json() == {"status": True}, "Valid API key via query param should return status True"

        r = await client.get(
            app.url_path_for("validate_api_key"),
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, "Invalid API key via header should return 401"

        r = await client.get(
            app.url_path_for("validate_api_key"),
            params={"api_key": "invalid-key"},
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, "Invalid API key via query param should return 401"

        r = await client.get(app.url_path_for("validate_api_key"))
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, "Missing API key should return 401"


@pytest.mark.asyncio
async def test_delete_upload():
    """Test admin can delete an upload and its file."""
    seed_schema()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client)
        token = token_data["token"]

        upload_data = await initiate_upload(
            client,
            token=token,
            filename="test.mp4",
            size_bytes=1000,
            filetype="video/mp4",
            meta_data={"broadcast_date": "2025-01-01", "title": "Test Video", "source": "youtube"},
        )
        upload_id = upload_data["upload_id"]

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None, "Upload should exist before deletion"

        delete_resp = await client.delete(
            app.url_path_for("delete_upload", upload_id=upload_id),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert delete_resp.status_code == status.HTTP_200_OK, "Delete upload should return 200"
        assert delete_resp.json()["status"] == "deleted", "Response should indicate deletion"

        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is None, "Upload should be deleted from database"


@pytest.mark.asyncio
async def test_delete_upload_not_found():
    """Test deleting non-existent upload returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.delete(
            app.url_path_for("delete_upload", upload_id=99999),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == status.HTTP_404_NOT_FOUND, "Deleting non-existent upload should return 404"


@pytest.mark.asyncio
async def test_delete_upload_requires_admin():
    """Test delete upload requires admin authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.delete(app.url_path_for("delete_upload", upload_id=1))
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, "Delete without auth should return 401"

        r = await client.delete(
            app.url_path_for("delete_upload", upload_id=1),
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert r.status_code == status.HTTP_401_UNAUTHORIZED, "Delete with invalid key should return 401"
