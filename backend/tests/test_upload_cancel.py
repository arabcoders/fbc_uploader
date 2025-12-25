"""Tests for upload cancellation endpoint."""

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema


@pytest.mark.asyncio
async def test_cancel_upload_restores_slot():
    """Test that canceling an upload restores the upload slot."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token with 2 max uploads
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 2, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Initiate first upload
        response = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "filename": "test1.txt",
                "filetype": "text/plain",
                "size_bytes": 100,
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert response.status_code == 201
        data = response.json()
        upload_id_1 = data["upload_id"]
        assert data["remaining_uploads"] == 1

        # Cancel the upload
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id_1),
            params={"token": token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Upload cancelled successfully"
        assert data["remaining_uploads"] == 2

        # Verify we can now initiate 2 more uploads
        info_url = app.url_path_for("get_public_token_info", token_value=token)
        info = await client.get(info_url)
        assert info.status_code == 200
        assert info.json()["remaining_uploads"] == 2


@pytest.mark.asyncio
async def test_cancel_upload_invalid_token():
    """Test that canceling with wrong token fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create two tokens
        create_url = app.url_path_for("create_token")
        r1 = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token1 = r1.json()["token"]

        r2 = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token2 = r2.json()["token"]

        # Initiate upload with token1
        response = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token1},
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": 100,
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert response.status_code == 201
        upload_id = response.json()["upload_id"]

        # Try to cancel with token2 (wrong token)
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": token2},
        )
        assert response.status_code == 403
        assert "does not belong to this token" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_upload_invalid_upload_id():
    """Test that canceling non-existent upload fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a token
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Try to cancel non-existent upload
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=999999),
            params={"token": token},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Upload not found"


@pytest.mark.asyncio
async def test_cancel_completed_upload_fails():
    """Test that canceling a completed upload fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Initiate and complete upload via TUS
        init_response = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": 5,
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert init_response.status_code == 201
        upload_id = init_response.json()["upload_id"]

        # Upload the file via TUS PATCH
        tus_patch_url = app.url_path_for("tus_patch", upload_id=upload_id)
        patch_response = await client.patch(
            tus_patch_url,
            headers={
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
                "Tus-Resumable": "1.0.0",
            },
            content=b"hello",
        )
        assert patch_response.status_code == 204

        # Try to cancel completed upload
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": token},
        )
        assert response.status_code == 400
        assert "Cannot cancel completed upload" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_multiple_uploads():
    """Test canceling multiple uploads restores all slots."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token with 3 max uploads
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 3, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Initiate 3 uploads
        upload_ids = []
        for i in range(3):
            response = await client.post(
                app.url_path_for("initiate_upload"),
                params={"token": token},
                json={
                    "filename": f"test{i}.txt",
                    "filetype": "text/plain",
                    "size_bytes": 100,
                    "meta_data": {"broadcast_date": "2024-01-01", "title": f"Test{i}", "source": "youtube"},
                },
            )
            assert response.status_code == 201
            upload_ids.append(response.json()["upload_id"])

        # Verify all slots consumed
        info_url = app.url_path_for("get_public_token_info", token_value=token)
        info = await client.get(info_url)
        assert info.json()["remaining_uploads"] == 0

        # Cancel first upload
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_ids[0]),
            params={"token": token},
        )
        assert response.status_code == 200
        assert response.json()["remaining_uploads"] == 1

        # Cancel second upload
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_ids[1]),
            params={"token": token},
        )
        assert response.status_code == 200
        assert response.json()["remaining_uploads"] == 2

        # Verify uploads_used is back to 1 (one upload still exists)
        info = await client.get(info_url)
        assert info.json()["remaining_uploads"] == 2


@pytest.mark.asyncio
async def test_cancel_with_nonexistent_token():
    """Test that canceling with non-existent token fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create a real token
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Initiate upload
        response = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": 100,
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
            },
        )
        assert response.status_code == 201
        upload_id = response.json()["upload_id"]

        # Try to cancel with non-existent token
        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": "fake_token"},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Token not found"
