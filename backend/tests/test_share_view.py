"""Test share view endpoint returns appropriate data based on token type."""

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import utils
from backend.app import models
from backend.app.main import app
from backend.tests.utils import complete_upload, create_token
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
        assert "max_chunk_bytes" in data, "Should include max_chunk_bytes field"


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
        assert "max_chunk_bytes" in data, "Should include max_chunk_bytes field"


@pytest.mark.asyncio
async def test_get_token_invalid_token_returns_404():
    """Test that invalid token returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(app.url_path_for("get_token", token_value="invalid_token"))

        assert response.status_code == status.HTTP_404_NOT_FOUND, "Should return 404 for invalid token"
        data = response.json()
        assert response.headers["content-type"].startswith("application/json"), "Invalid token should return a JSON error response"
        assert "detail" in data, "Invalid token response should include error detail"


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
        assert response_bot.headers["content-type"].startswith("text/html"), "Bot share page should render HTML"
        assert "<html" in html_content.lower(), "Bot share page should render an HTML document"

        response_browser = await client.get(f"/f/{upload_token}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        assert response_browser.status_code == status.HTTP_200_OK, "Should return 200 for regular browser"
        html_browser = response_browser.text
        assert response_browser.headers["content-type"].startswith("text/html"), "Browser share page should render HTML"
        assert "<html" in html_browser.lower(), "Browser share page should render an HTML document"


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_share_page_bot_preview_with_video(client):
    """Discord bot preview should expose playable video embed tags alongside the thumbnail image."""
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

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"
        assert complete_data["status"] == "postprocessing", "Video should enter postprocessing after explicit completion"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        response = await client.get(f"/f/{token_value}", headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"})

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for Discord bot"
        html_content = response.text
        assert '<meta property="og:image"' in html_content, "Bot preview should expose an OpenGraph image"
        assert '<meta name="twitter:image"' in html_content, "Bot preview should expose a Twitter image"
        assert '<meta name="twitter:card" content="player"' in html_content, "Bot preview should use a player card"
        assert '<meta property="og:video"' in html_content, "Bot preview should expose playable video metadata"
        assert '<meta property="og:video" content="http://testserver/api/tokens/' in html_content, (
            "Bot preview should point OpenGraph video metadata at the hosted media endpoint"
        )
        assert '/stream/"' in html_content, "Bot preview should fall back to the original stream when no preview sidecar exists"
        assert '/thumbnail/"' in html_content, "Bot preview should point to the thumbnail endpoint"
        assert "<title>sample.mp4</title>" in html_content, "Bot preview should use the filename as the embed title"


@pytest.mark.asyncio
async def test_token_embed_page_renders_preview_for_public_token(client):
    """Human embed page should keep video embed metadata while avoiding eager autoplay."""
    with patch("backend.app.security.settings.allow_public_downloads", True):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]
        public_token = token_data["download_token"]

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

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"
        assert complete_data["status"] == "postprocessing", "Video should enter postprocessing after explicit completion"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        response = await client.get(app.url_path_for("token_embed", token=public_token))

        assert response.status_code == status.HTTP_200_OK, "Embed endpoint should return HTML for valid shared media"
        html_content = response.text
        assert '<meta property="og:image"' in html_content, "Embed page should include OpenGraph image metadata"
        assert '<meta property="og:video"' in html_content, "Embed page should still include playable video metadata"
        assert '<meta property="og:video" content="http://testserver/api/tokens/' in html_content, (
            "User embed page should keep full-stream metadata for playback"
        )
        assert '/stream/"' in html_content, "Embed page should keep the full stream URL for playback"
        assert '/thumbnail/"' in html_content, "Embed page should include the thumbnail endpoint"
        assert '<video class="fullscreen" controls preload="none" playsinline' in html_content, (
            "Embed page should avoid eager media preloading"
        )
        assert "autoplay" not in html_content, "Embed page should not autoplay media"
        assert "<title>sample.mp4</title>" in html_content, "Embed page should include the filename in the document title"


@pytest.mark.asyncio
async def test_thumbnail_endpoint_returns_shared_fallback_when_no_thumbnail_exists(client):
    """Thumbnail endpoint should return the shared fallback image when no sidecar exists."""
    with patch("backend.app.security.settings.allow_public_downloads", True):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]
        download_token = token_data["download_token"]
        file_content = b"hello world"

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "sample.txt",
                "filetype": "text/plain",
                "size_bytes": len(file_content),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should succeed"
        upload_id = init_resp.json()["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=file_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(file_content)),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Upload bytes should be accepted"

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded files"
        assert complete_data["status"] == "completed", "Non-video uploads should complete without postprocessing"

        response = await client.get(app.url_path_for("get_file_thumbnail", download_token=download_token, upload_id=upload_id))

        assert response.status_code == status.HTTP_200_OK, "Thumbnail endpoint should return a response"
        assert response.headers["content-type"].startswith("image/jpeg"), "Fallback thumbnail should use the shared JPEG asset"
        assert response.headers["content-disposition"].startswith("inline;"), "Fallback thumbnail should render inline"
        assert response.content, "Thumbnail endpoint should return image bytes"


@pytest.mark.asyncio
async def test_share_page_bot_preview_uses_generated_preview_sidecar(client):
    """Bot preview should prefer the generated short preview clip when one exists."""
    with (
        patch("backend.app.security.settings.allow_public_downloads", True),
        patch("backend.app.embed_preview.settings.embed_preview_min_size_bytes", 1),
    ):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]

        video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
        file_size = video_file.stat().st_size

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
        upload_id = init_resp.json()["upload_id"]

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

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"
        assert complete_data["status"] == "postprocessing", "Video should enter postprocessing after explicit completion"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        from backend.app.db import SessionLocal

        async with SessionLocal() as session:
            token_stmt = select(models.UploadToken).where(models.UploadToken.token == token_value)
            token_res = await session.execute(token_stmt)
            token_row = token_res.scalar_one()

            upload_stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            upload_res = await session.execute(upload_stmt)
            upload_row = upload_res.scalar_one()

        preview_path = utils.get_preview_path(upload_row.storage_path or "")
        preview_path.write_bytes(b"preview-bytes")

        response = await client.get(f"/f/{token_row.download_token}", headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"})

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for Discord bot"
        assert "/preview.mp4" in response.text, "Bot preview should prefer the short preview endpoint when available"
        assert 'property="og:description"' in response.text, "Bot preview should include description metadata"
        assert 'name="fbc:preview-mode" content="generated-short-clip"' in response.text, (
            "Bot preview should expose a stable marker when it embeds a generated short preview clip"
        )


@pytest.mark.asyncio
async def test_share_page_bot_preview_ignores_sidecar_when_preview_feature_disabled(client):
    """Bot preview should fall back to the full stream when preview sidecars are disabled by config."""
    with (
        patch("backend.app.security.settings.allow_public_downloads", True),
        patch("backend.app.embed_preview.settings.embed_preview_min_size_bytes", 0),
    ):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]

        video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
        file_size = video_file.stat().st_size

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
        upload_id = init_resp.json()["upload_id"]

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

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"
        assert complete_data["status"] == "postprocessing", "Video should enter postprocessing after explicit completion"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        from backend.app.db import SessionLocal

        async with SessionLocal() as session:
            token_stmt = select(models.UploadToken).where(models.UploadToken.token == token_value)
            token_res = await session.execute(token_stmt)
            token_row = token_res.scalar_one()

            upload_stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
            upload_res = await session.execute(upload_stmt)
            upload_row = upload_res.scalar_one()

        preview_path = utils.get_preview_path(upload_row.storage_path or "")
        preview_path.write_bytes(b"preview-bytes")

        response = await client.get(f"/f/{token_row.download_token}", headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"})

        assert response.status_code == status.HTTP_200_OK, "Should return 200 for Discord bot"
        assert "/preview.mp4" not in response.text, "Disabled preview feature should not advertise preview sidecars"
        assert "/stream/" in response.text, "Disabled preview feature should fall back to the original stream"
        assert 'name="fbc:preview-mode" content="generated-short-clip"' not in response.text, (
            "Bot preview should not expose the generated-preview marker when it falls back to the full stream"
        )


@pytest.mark.asyncio
async def test_share_embed_routes_can_be_requested_repeatedly(client):
    """Repeated embed requests should succeed without leaking database sessions."""
    with patch("backend.app.security.settings.allow_public_downloads", True):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]
        public_token = token_data["download_token"]

        video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
        file_size = video_file.stat().st_size

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
        upload_id = init_resp.json()["upload_id"]

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

        complete_status, _ = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        for _ in range(5):
            bot_response = await client.get(
                f"/f/{token_value}",
                headers={"User-Agent": "Mozilla/5.0 (compatible; Discordbot/2.0)"},
            )
            assert bot_response.status_code == status.HTTP_200_OK, "Bot share preview should keep succeeding"

            embed_response = await client.get(app.url_path_for("token_embed", token=public_token))
            assert embed_response.status_code == status.HTTP_200_OK, "Embed preview should keep succeeding"
