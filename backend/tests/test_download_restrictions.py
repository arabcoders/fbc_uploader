"""Test download restrictions for expired/disabled tokens."""

import pytest
from datetime import UTC, datetime, timedelta
from httpx import ASGITransport, AsyncClient
from fastapi import status
from unittest.mock import patch

from backend.app.main import app
from backend.app.config import settings
from backend.tests.utils import create_token, initiate_upload, upload_file_via_tus


@pytest.mark.asyncio
async def test_download_blocked_for_disabled_token():
    """Test that downloads are blocked when token is disabled and public downloads are off."""
    with patch("backend.app.security.settings.allow_public_downloads", False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            token_data = await create_token(client, max_uploads=1)
            upload_token = token_data["token"]
            download_token = token_data["download_token"]

            upload_data = await initiate_upload(client, upload_token, "test.txt", 12)
            upload_id = upload_data["upload_id"]
            await upload_file_via_tus(client, upload_id, b"test content")

            await client.patch(
                app.url_path_for("update_token", token_value=upload_token),
                json={"disabled": True},
                headers={"Authorization": f"Bearer {settings.admin_api_key}"},
            )

            download_url = app.url_path_for("download_file", download_token=download_token, upload_id=upload_id)
            response = await client.get(download_url)
            assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN], (
                "Download should be blocked for disabled token without auth"
            )


@pytest.mark.asyncio
async def test_download_blocked_for_expired_token():
    """Test that downloads are blocked when token is expired and public downloads are off."""
    with patch("backend.app.security.settings.allow_public_downloads", False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            token_data = await create_token(client, max_uploads=1)
            upload_token = token_data["token"]
            download_token = token_data["download_token"]

            upload_data = await initiate_upload(client, upload_token, "test.txt", 12)
            upload_id = upload_data["upload_id"]
            await upload_file_via_tus(client, upload_id, b"test content")

            expired_time = datetime.now(UTC) - timedelta(hours=1)
            await client.patch(
                app.url_path_for("update_token", token_value=upload_token),
                json={"expiry_datetime": expired_time.isoformat()},
                headers={"Authorization": f"Bearer {settings.admin_api_key}"},
            )

            download_url = app.url_path_for("download_file", download_token=download_token, upload_id=upload_id)
            response = await client.get(download_url)
            assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN], (
                "Download should be blocked for expired token without auth"
            )


@pytest.mark.asyncio
async def test_download_allowed_for_disabled_token_with_admin_key():
    """Test that admin can download from disabled tokens."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token and upload a file
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "test.txt", 12)
        upload_id = upload_data["upload_id"]
        await upload_file_via_tus(client, upload_id, b"test content")

        # Disable the token
        await client.patch(
            app.url_path_for("update_token", token_value=upload_token),
            json={"disabled": True},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )

        # Download should work with admin key
        download_url = app.url_path_for("download_file", download_token=download_token, upload_id=upload_id)
        response = await client.get(download_url, headers={"Authorization": f"Bearer {settings.admin_api_key}"})
        assert response.status_code == status.HTTP_200_OK, "Admin should be able to download from disabled token"
        assert response.content == b"test content", "Downloaded content should match"


@pytest.mark.asyncio
async def test_get_file_info_blocked_for_disabled_token():
    """Test that file info is blocked when token is disabled and public downloads are off."""
    with patch("backend.app.security.settings.allow_public_downloads", False):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            token_data = await create_token(client, max_uploads=1)
            upload_token = token_data["token"]
            download_token = token_data["download_token"]

            upload_data = await initiate_upload(client, upload_token, "test.txt", 12)
            upload_id = upload_data["upload_id"]
            await upload_file_via_tus(client, upload_id, b"test content")

            await client.patch(
                app.url_path_for("update_token", token_value=upload_token),
                json={"disabled": True},
                headers={"Authorization": f"Bearer {settings.admin_api_key}"},
            )

            info_url = app.url_path_for("get_file_info", download_token=download_token, upload_id=upload_id)
            response = await client.get(info_url)
            assert response.status_code in [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN], (
                "File info should be blocked for disabled token without auth"
            )


@pytest.mark.asyncio
async def test_get_file_info_allowed_for_disabled_token_with_admin_key():
    """Test that admin can get file info from disabled tokens."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token and upload a file
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "test.txt", 12)
        upload_id = upload_data["upload_id"]
        await upload_file_via_tus(client, upload_id, b"test content")

        # Disable the token
        await client.patch(
            app.url_path_for("update_token", token_value=upload_token),
            json={"disabled": True},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )

        # File info should work with admin key
        info_url = app.url_path_for("get_file_info", download_token=download_token, upload_id=upload_id)
        response = await client.get(info_url, headers={"Authorization": f"Bearer {settings.admin_api_key}"})
        assert response.status_code == status.HTTP_200_OK, "Admin should be able to get file info from disabled token"
        data = response.json()
        assert data["filename"] == "test.txt", "File info should be returned"
