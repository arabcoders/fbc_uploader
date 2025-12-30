"""
Test that API responses don't expose admin API key in download URLs.
The frontend should append the API key when needed.
"""

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.utils import create_token, initiate_upload, upload_file_via_tus


@pytest.mark.asyncio
async def test_list_token_uploads_does_not_expose_api_key():
    """Test that list_token_uploads returns clean download URLs without API key."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client)
        upload_data = await initiate_upload(
            client, token_data["token"], filename="test.txt", size_bytes=11, filetype="text/plain", meta_data={}
        )
        await upload_file_via_tus(client, upload_data["upload_id"], b"hello world")

        # Get uploads list as admin
        response = await client.get(
            app.url_path_for("list_token_uploads", token_value=token_data["token"]),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert response.status_code == status.HTTP_200_OK, "Should return uploads list"
        uploads = response.json()
        assert len(uploads) > 0, "Should have at least one upload"

        # Verify download_url does NOT contain api_key
        download_url = uploads[0]["download_url"]
        assert "api_key" not in download_url, "Download URL should not contain api_key"
        assert "?api_key=" not in download_url, "Download URL should not have api_key query param"


@pytest.mark.asyncio
async def test_get_file_info_does_not_expose_api_key():
    """Test that get_file_info returns clean download URLs without API key."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token and upload a file
        token_data = await create_token(client)
        upload_data = await initiate_upload(
            client, token_data["token"], filename="test.txt", size_bytes=11, filetype="text/plain", meta_data={}
        )
        await upload_file_via_tus(client, upload_data["upload_id"], b"hello world")

        response = await client.get(
            app.url_path_for(
                "get_file_info",
                download_token=token_data["download_token"],
                upload_id=upload_data["upload_id"],
            ),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert response.status_code == status.HTTP_200_OK, "Should return file info"
        file_info = response.json()

        # Verify download_url does NOT contain api_key
        download_url = file_info["download_url"]
        assert "api_key" not in download_url, "Download URL should not contain api_key"
        assert "?api_key=" not in download_url, "Download URL should not have api_key query param"
