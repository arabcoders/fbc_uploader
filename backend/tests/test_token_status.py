"""Test token status handling - disabled and expired tokens."""

import pytest
from datetime import UTC, datetime, timedelta
from httpx import ASGITransport, AsyncClient
from fastapi import status

from backend.app.main import app
from backend.app.config import settings
from backend.tests.utils import create_token


@pytest.mark.asyncio
async def test_disabled_token_can_be_viewed_but_not_used():
    """Test that disabled tokens return info via get_token but cannot upload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create and disable a token
        token_data = await create_token(client, max_uploads=2)
        upload_token = token_data["token"]

        # Disable the token
        await client.patch(
            app.url_path_for("update_token", token_value=upload_token),
            json={"disabled": True},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )

        # get_token should still work and return the token info
        response = await client.get(app.url_path_for("get_token", token_value=upload_token))
        assert response.status_code == status.HTTP_200_OK, "get_token should work for disabled tokens"
        data = response.json()
        assert data["disabled"] is True, "Token should be marked as disabled"
        assert data["token"] == upload_token, "Should return token info"

        # But uploads should be blocked
        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": upload_token},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {},
            },
        )
        assert upload_resp.status_code == status.HTTP_403_FORBIDDEN, "Disabled token should not allow uploads"


@pytest.mark.asyncio
async def test_expired_token_can_be_viewed_but_not_used():
    """Test that expired tokens return info via get_token but cannot upload."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a token that expires in the past
        expired_time = datetime.now(UTC) - timedelta(hours=1)
        token_data = await create_token(client, max_uploads=2, expiry_datetime=expired_time.isoformat())
        upload_token = token_data["token"]

        # get_token should still work and return the token info
        response = await client.get(app.url_path_for("get_token", token_value=upload_token))
        assert response.status_code == status.HTTP_200_OK, "get_token should work for expired tokens"
        data = response.json()
        assert data["token"] == upload_token, "Should return token info"

        # Verify it's expired by checking the timestamp
        expires_at_str = data["expires_at"]
        if expires_at_str.endswith("Z"):
            expires_at_str = expires_at_str[:-1] + "+00:00"
        expires_at = datetime.fromisoformat(expires_at_str)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        now = datetime.now(UTC)
        assert expires_at < now, f"Token should be expired: {expires_at} < {now}"

        # But uploads should be blocked
        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": upload_token},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {},
            },
        )
        assert upload_resp.status_code == status.HTTP_403_FORBIDDEN, "Expired token should not allow uploads"


@pytest.mark.asyncio
async def test_download_token_view_works_for_disabled():
    """Test that share page (download token view) works for disabled tokens."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create and disable a token
        token_data = await create_token(client, max_uploads=2)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        # Disable the token
        await client.patch(
            app.url_path_for("update_token", token_value=upload_token),
            json={"disabled": True},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )

        # Access with download token should still work
        response = await client.get(app.url_path_for("get_token", token_value=download_token))
        assert response.status_code == status.HTTP_200_OK, "Share view should work for disabled tokens"
        data = response.json()
        assert data["disabled"] is True, "Token should be marked as disabled"
        assert data["download_token"] == download_token, "Should return download token"
