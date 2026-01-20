"""Test share view endpoint returns appropriate data based on token type."""

import asyncio
import pytest
from pathlib import Path
from httpx import ASGITransport, AsyncClient
from fastapi import status
from unittest.mock import patch

from backend.app.main import app
from backend.tests.utils import create_token
from backend.tests.test_postprocessing import wait_for_processing


@pytest.mark.asyncio
async def test_get_token_with_upload_token_returns_full_info():
    """Test that accessing with upload token returns full token info including upload token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000000)
        upload_token = token_data["token"]

        response = await client.get(app.url_path_for("get_token", token_value=upload_token))

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for valid upload token with auth"
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

        response = await client.get(app.url_path_for("get_token", token_value=download_token))

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for valid download token"
        data = response.json()
        assert data["token"] is None or data["token"] == "", "Token field should be empty/None for share info"
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
        response = await client.get(app.url_path_for("get_token", token_value="invalid_token"))

        assert response.status_code == status.HTTP_404_NOT_FOUND, "Should return 404 for invalid token"
        data = response.json()
        assert "detail" in data, "Should include error detail"
        assert "not found" in data["detail"].lower(), "Error should mention token not found"


@pytest.mark.asyncio
async def test_share_page_route_exists_and_responds():
    """Test that /f/{token} route exists and responds appropriately."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]

        response_bot = await client.get(f"/f/{upload_token}", headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"})
        assert response_bot.status_code == status.HTTP_200_OK, "Should return 200 for bot accessing share page"
        html_content = response_bot.text
        assert "<!DOCTYPE html>" in html_content or "<html" in html_content.lower(), "Should return HTML content for bot"

        response_browser = await client.get(f"/f/{upload_token}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        assert response_browser.status_code == status.HTTP_200_OK, "Should return 200 for regular browser"
        html_browser = response_browser.text
        assert "<!DOCTYPE html>" in html_browser or "<html" in html_browser.lower(), "Should return HTML content for browser"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_share_page_bot_preview_with_video(client):
    """Test that Discord bot gets video embed preview when video file exists."""
    with patch("backend.app.security.settings.allow_public_downloads", True):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]

        video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
        file_size = video_file.stat().st_size

        from backend.app.main import app

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "sample.mp4",
                "filetype": "video/mp4",
                "size_bytes": file_size,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should succeed"
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=video_file.read_bytes(),
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(file_size),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Video upload should complete"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        response = await client.get(f"/f/{token_value}", headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"})

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for Discord bot"
        html_content = response.text
        assert "og:video" in html_content or "og:type" in html_content, "Should include OpenGraph video metadata"
        assert "sample.mp4" in html_content, "Should include video filename"
