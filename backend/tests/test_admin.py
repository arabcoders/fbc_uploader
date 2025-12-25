import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.tests.conftest import seed_schema


@pytest.mark.asyncio
async def test_admin_validate():
    """Test admin API key validation endpoint."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Valid key via header
        r = await client.get(
            "/api/admin/validate",
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == 200
        assert r.json() == {"status": True}

        # Valid key via query param
        r = await client.get(
            "/api/admin/validate",
            params={"api_key": settings.admin_api_key},
        )
        assert r.status_code == 200
        assert r.json() == {"status": True}

        # Invalid key via header
        r = await client.get(
            "/api/admin/validate",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert r.status_code == 401

        # Invalid key via query param
        r = await client.get(
            "/api/admin/validate",
            params={"api_key": "invalid-key"},
        )
        assert r.status_code == 401

        # No authentication
        r = await client.get("/api/admin/validate")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_delete_upload():
    """Test admin can delete an upload and its file."""
    seed_schema()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a token
        token_resp = await client.post(
            "/api/tokens/",
            json={"max_uploads": 5, "max_size_bytes": 10_000_000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert token_resp.status_code == 201
        token = token_resp.json()["token"]

        # Initiate an upload
        upload_resp = await client.post(
            "/api/uploads/initiate",
            params={"token": token},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {"broadcast_date": "2025-01-01", "title": "Test Video", "source": "youtube"},
            },
        )
        assert upload_resp.status_code == 201
        upload_id = upload_resp.json()["upload_id"]

        # Verify upload exists
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None

        # Delete the upload as admin
        delete_resp = await client.delete(
            f"/api/admin/uploads/{upload_id}",
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert delete_resp.status_code == 200
        assert delete_resp.json()["status"] == "deleted"

        # Verify upload is deleted
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is None


@pytest.mark.asyncio
async def test_delete_upload_not_found():
    """Test deleting non-existent upload returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        r = await client.delete(
            "/api/admin/uploads/99999",
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_upload_requires_admin():
    """Test delete upload requires admin authentication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # No auth
        r = await client.delete("/api/admin/uploads/1")
        assert r.status_code == 401

        # Invalid auth
        r = await client.delete(
            "/api/admin/uploads/1",
            headers={"Authorization": "Bearer invalid-key"},
        )
        assert r.status_code == 401
