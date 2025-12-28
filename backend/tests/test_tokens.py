import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.db import SessionLocal
from backend.app.main import app
from backend.tests.utils import create_token


@pytest.mark.asyncio
async def test_create_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=2, max_size_bytes=12345)

        assert "token" in token_data and "download_token" in token_data, "Response should include both token and download_token"
        assert token_data["max_uploads"] == 2, "Token should have max_uploads set to 2"

        async with SessionLocal() as session:
            stmt = select(models.UploadToken).where(models.UploadToken.token == token_data["token"])
            res = await session.execute(stmt)
            token_row = res.scalar_one()
            assert token_row.download_token == token_data["download_token"], "Download token in DB should match response"
