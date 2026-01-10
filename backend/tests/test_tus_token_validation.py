"""Tests to verify TUS protocol endpoints enforce token expiry/disabled validation."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.tests.utils import create_token, initiate_upload, tus_head


@pytest.mark.asyncio
async def test_tus_head_blocked_for_expired_token():
    """TUS HEAD should fail when token is expired."""
    from backend.app.db import get_db
    from backend.app.models import UploadToken
    from sqlalchemy import select, update

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create valid token and initiate upload
        token_data = await create_token(client)
        token_value = token_data["token"]

        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=100,
        )
        upload_id = upload_data["upload_id"]

        # Manually expire the token in database
        async for db in get_db():
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            stmt = update(UploadToken).where(UploadToken.token == token_value).values(expires_at=expired_time)
            await db.execute(stmt)
            await db.commit()
            break

        # TUS HEAD should fail for expired token
        status_code, headers = await tus_head(client, upload_id)
        assert status_code == status.HTTP_403_FORBIDDEN, "HEAD should fail with expired token"


@pytest.mark.asyncio
async def test_tus_head_blocked_for_disabled_token():
    """TUS HEAD should fail when token is disabled."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token
        token_data = await create_token(client)
        token_value = token_data["token"]

        # Initiate upload
        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=100,
        )
        upload_id = upload_data["upload_id"]

        # Disable the token
        admin_key = "test-admin"
        disable_response = await client.patch(
            f"/api/tokens/{token_value}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert disable_response.status_code == status.HTTP_200_OK, "Token should be disabled successfully"

        # TUS HEAD should now fail
        status_code, headers = await tus_head(client, upload_id)
        assert status_code == status.HTTP_403_FORBIDDEN, "HEAD should fail with disabled token"


@pytest.mark.asyncio
async def test_tus_patch_blocked_for_expired_token():
    """TUS PATCH should fail when token is expired."""
    from backend.app.db import get_db
    from backend.app.models import UploadToken
    from sqlalchemy import select, update

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create valid token and initiate upload
        token_data = await create_token(client)
        token_value = token_data["token"]

        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=11,
        )
        upload_id = upload_data["upload_id"]

        # Manually expire the token in database
        async for db in get_db():
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            stmt = update(UploadToken).where(UploadToken.token == token_value).values(expires_at=expired_time)
            await db.execute(stmt)
            await db.commit()
            break

        # Try to upload data via PATCH
        patch_response = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=b"Hello World",
            headers={
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
                "Content-Length": "11",
            },
        )
        assert patch_response.status_code == status.HTTP_403_FORBIDDEN, "PATCH should fail with expired token"


@pytest.mark.asyncio
async def test_tus_patch_blocked_for_disabled_token():
    """TUS PATCH should fail when token is disabled."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token
        token_data = await create_token(client)
        token_value = token_data["token"]

        # Initiate upload
        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=11,
        )
        upload_id = upload_data["upload_id"]

        # Disable the token
        admin_key = "test-admin"
        disable_response = await client.patch(
            f"/api/tokens/{token_value}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert disable_response.status_code == status.HTTP_200_OK, "Token should be disabled successfully"

        # Try to upload data via PATCH
        patch_response = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=b"Hello World",
            headers={
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
                "Content-Length": "11",
            },
        )
        assert patch_response.status_code == status.HTTP_403_FORBIDDEN, "PATCH should fail with disabled token"


@pytest.mark.asyncio
async def test_tus_delete_blocked_for_expired_token():
    """TUS DELETE should fail when token is expired."""
    from backend.app.db import get_db
    from backend.app.models import UploadToken
    from sqlalchemy import select, update

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create valid token and initiate upload
        token_data = await create_token(client)
        token_value = token_data["token"]

        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=100,
        )
        upload_id = upload_data["upload_id"]

        # Manually expire the token in database
        async for db in get_db():
            expired_time = datetime.now(UTC) - timedelta(hours=1)
            stmt = update(UploadToken).where(UploadToken.token == token_value).values(expires_at=expired_time)
            await db.execute(stmt)
            await db.commit()
            break

        # Try to delete via TUS DELETE
        delete_response = await client.delete(f"/api/uploads/{upload_id}/tus")
        assert delete_response.status_code == status.HTTP_403_FORBIDDEN, "DELETE should fail with expired token"


@pytest.mark.asyncio
async def test_tus_delete_blocked_for_disabled_token():
    """TUS DELETE should fail when token is disabled."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token
        token_data = await create_token(client)
        token_value = token_data["token"]

        # Initiate upload
        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=100,
        )
        upload_id = upload_data["upload_id"]

        # Disable the token
        admin_key = "test-admin"
        disable_response = await client.patch(
            f"/api/tokens/{token_value}",
            json={"disabled": True},
            headers={"Authorization": f"Bearer {admin_key}"},
        )
        assert disable_response.status_code == status.HTTP_200_OK, "Token should be disabled successfully"

        # Try to delete via TUS DELETE
        delete_response = await client.delete(f"/api/uploads/{upload_id}/tus")
        assert delete_response.status_code == status.HTTP_403_FORBIDDEN, "DELETE should fail with disabled token"


@pytest.mark.asyncio
async def test_tus_delete_works_with_valid_token():
    """TUS DELETE should work when token is valid."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token
        token_data = await create_token(client)
        token_value = token_data["token"]

        # Initiate upload
        upload_data = await initiate_upload(
            client,
            token_value,
            filename="test.txt",
            filetype="text/plain",
            size_bytes=100,
        )
        upload_id = upload_data["upload_id"]

        # Delete should work with valid token
        delete_response = await client.delete(f"/api/uploads/{upload_id}/tus")
        assert delete_response.status_code == status.HTTP_204_NO_CONTENT, "DELETE should work with valid token"

        # Verify upload is gone
        status_code, headers = await tus_head(client, upload_id)
        assert status_code == status.HTTP_404_NOT_FOUND, "Upload should be deleted"
