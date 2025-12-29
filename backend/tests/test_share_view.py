"""Test share view endpoint returns appropriate data based on token type."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.tests.utils import create_token


@pytest.mark.asyncio
async def test_get_token_with_upload_token_returns_full_info():
    """Test that accessing with upload token returns full token info including upload token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000000)
        upload_token = token_data["token"]

        response = await client.get(app.url_path_for("get_public_token_info", token_value=upload_token))

        assert response.status_code == 200, "Should return 200 for valid upload token with auth"
        data = response.json()
        assert "token" in data, "Should include upload token field"
        assert data["token"] == upload_token, "Upload token should match"
        assert "download_token" in data, "Should include download token field"
        assert "remaining_uploads" in data, "Should include remaining_uploads field"


@pytest.mark.asyncio
async def test_get_token_with_download_token_returns_limited_info():
    """Test that accessing with download token returns share info without upload token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000000)
        download_token = token_data["download_token"]

        response = await client.get(app.url_path_for("get_public_token_info", token_value=download_token))

        assert response.status_code == 200, "Should return 200 for valid download token"
        data = response.json()
        assert data["token"] == "", "Token field should be empty for share info"
        assert "download_token" in data, "Should include download token field"
        assert data["download_token"] == download_token, "Download token should match"
        assert "max_uploads" in data, "Should include max_uploads field"
        assert "allowed_mime" in data, "Should include allowed_mime field"
        assert "allow_public_downloads" in data, "Should include allow_public_downloads field"


@pytest.mark.asyncio
async def test_get_token_invalid_token_returns_404():
    """Test that invalid token returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(app.url_path_for("get_public_token_info", token_value="invalid_token"))

        assert response.status_code == 404, "Should return 404 for invalid token"
        data = response.json()
        assert "detail" in data, "Should include error detail"
        assert "not found" in data["detail"].lower(), "Error should mention token not found"
