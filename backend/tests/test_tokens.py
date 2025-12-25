import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.main import app


@pytest.mark.asyncio
async def test_create_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        payload = {"max_uploads": 2, "max_size_bytes": 12345}
        # New route: /api/tokens/ instead of /api/admin/upload_tokens
        url = app.url_path_for("create_token")
        r = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert "token" in data and "download_token" in data
        assert data["max_uploads"] == 2

        async with SessionLocal() as session:
            stmt = select(models.UploadToken).where(models.UploadToken.token == data["token"])
            res = await session.execute(stmt)
            token_row = res.scalar_one()
            assert token_row.download_token == data["download_token"]
