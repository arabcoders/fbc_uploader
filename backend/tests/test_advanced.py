import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import create_token, validate_metadata


@pytest.mark.asyncio
async def test_create_token_with_allowed_mime_types():
    """Test token creation with MIME type restrictions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(
            client,
            max_uploads=3,
            max_size_bytes=50_000_000,
            allowed_mimes=["video/mp4", "video/webm"],
        )
        assert "token" in token_data, "Response should include token"
        assert "download_token" in token_data, "Response should include download_token"


@pytest.mark.asyncio
async def test_create_token_with_expiry():
    """Test token creation with expiry date."""
    from datetime import UTC, datetime, timedelta

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        expiry = (datetime.now(UTC) + timedelta(hours=48)).isoformat()
        token_data = await create_token(
            client,
            max_uploads=5,
            max_size_bytes=100_000_000,
            expires_at=expiry,
        )
        assert "expires_at" in token_data, "Response should include expires_at field"


@pytest.mark.asyncio
async def test_reject_upload_with_disallowed_mime():
    """Test that uploads with disallowed MIME types are rejected."""
    seed_schema()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, allowed_mime=["video/mp4"])

        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "filename": "test.mkv",
                "size_bytes": 1000,
                "filetype": "video/x-matroska",
                "meta_data": {"broadcast_date": "2025-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert upload_resp.status_code in [status.HTTP_201_CREATED, status.HTTP_403_FORBIDDEN, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE], "Disallowed MIME type should be rejected or require special handling"


@pytest.mark.asyncio
async def test_reject_upload_exceeding_size():
    """Test that uploads exceeding max size are rejected."""
    seed_schema()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_size_bytes=1000)

        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "filename": "large.mp4",
                "size_bytes": 10_000,
                "mimetype": "video/mp4",
                "meta_data": {"broadcast_date": "2025-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert upload_resp.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_413_CONTENT_TOO_LARGE], "Upload exceeding size limit should be rejected"
        assert (
            "exceeds" in upload_resp.json()["detail"].lower()
            or "too large" in upload_resp.json()["detail"].lower()
            or "entity" in upload_resp.json()["detail"].lower()
        ), "Error message should indicate size limit exceeded"


@pytest.mark.asyncio
async def test_token_list_pagination():
    """Test token listing with pagination."""
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        for i in range(15):
            await create_token(client, max_uploads=1, max_size_bytes=1000)

        r = await client.get(
            app.url_path_for("list_tokens"),
            params={"skip": 0, "limit": 10},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == status.HTTP_200_OK, "Token list endpoint should return 200"
        data = r.json()
        assert len(data["tokens"]) == 10, "First page should have 10 tokens"
        assert data["total"] >= 15, "Total should be at least 15 tokens"

        r = await client.get(
            app.url_path_for("list_tokens"),
            params={"skip": 10, "limit": 10},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert r.status_code == status.HTTP_200_OK, "Second page request should return 200"
        data = r.json()
        assert len(data["tokens"]) >= 5, "Second page should have at least 5 tokens"


@pytest.mark.asyncio
async def test_disabled_token_cannot_upload():
    """Test that disabled tokens cannot be used for uploads."""
    seed_schema()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        from backend.app.config import settings

        token_data = await create_token(client)
        token = token_data["token"]

        await client.patch(
            app.url_path_for("update_token", token_value=token),
            json={"disabled": True},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )

        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {"broadcast_date": "2025-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert upload_resp.status_code == status.HTTP_403_FORBIDDEN, "Disabled token should not be able to initiate uploads"


@pytest.mark.asyncio
async def test_metadata_required_fields():
    """Test that required metadata fields are enforced."""
    schema = [
        {"key": "title", "label": "Title", "type": "string", "required": True},
        {"key": "description", "label": "Description", "type": "string", "required": False},
    ]
    seed_schema(schema)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client)

        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {"description": "Some description"},
            },
        )
        assert upload_resp.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, "Missing required field should return 422"

        upload_resp = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "filename": "test.mp4",
                "size_bytes": 1000,
                "mimetype": "video/mp4",
                "meta_data": {"title": "Test Video"},
            },
        )
        assert upload_resp.status_code == status.HTTP_201_CREATED, "Upload with required fields should succeed"


@pytest.mark.asyncio
async def test_metadata_type_validation():
    """Test that metadata types are validated correctly."""
    schema = [
        {"key": "count", "label": "Count", "type": "number", "required": True},
        {"key": "active", "label": "Active", "type": "boolean", "required": True},
    ]
    seed_schema(schema)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        status_code, result = await validate_metadata(client, {"count": 42, "active": True})
        assert status_code == status.HTTP_200_OK, "Valid metadata types should pass validation"

        status_code, result = await validate_metadata(client, {"count": "not a number", "active": True})
        assert status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid number type should fail validation"

        status_code, result = await validate_metadata(client, {"count": 42, "active": "not a boolean"})
        assert status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid boolean type should fail validation"
