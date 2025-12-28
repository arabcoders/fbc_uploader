"""Tests for upload cancellation endpoint."""

import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import create_token, get_token_info, upload_file_via_tus


@pytest.mark.asyncio
async def test_cancel_upload_restores_slot():
    """Test that canceling an upload restores the upload slot."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=2, max_size_bytes=1000)
        token = token_data["token"]

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
        assert response.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        data = response.json()
        upload_id_1 = data["upload_id"]
        assert data["remaining_uploads"] == 1, "Remaining uploads should decrease to 1"

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id_1),
            params={"token": token},
        )
        assert response.status_code == status.HTTP_200_OK, "Upload cancellation should return 200"
        data = response.json()
        assert data["message"] == "Upload cancelled successfully", "Cancel response should contain success message"
        assert data["remaining_uploads"] == 2, "Remaining uploads should be restored to 2"

        info = await get_token_info(client, token)
        assert info["remaining_uploads"] == 2, "Token info should confirm 2 remaining uploads"


@pytest.mark.asyncio
async def test_cancel_upload_invalid_token():
    """Test that canceling with wrong token fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data1 = await create_token(client, max_uploads=1, max_size_bytes=1000)
        token1 = token_data1["token"]

        token_data2 = await create_token(client, max_uploads=1, max_size_bytes=1000)
        token2 = token_data2["token"]

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
        assert response.status_code == status.HTTP_201_CREATED, "Upload initiation should return 201"
        upload_id = response.json()["upload_id"]

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": token2},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN, "Canceling with wrong token should return 403"
        assert "does not belong to this token" in response.json()["detail"], "Error should indicate token mismatch"


@pytest.mark.asyncio
async def test_cancel_upload_invalid_upload_id():
    """Test that canceling non-existent upload fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=999999),
            params={"token": token},
        )
        assert response.status_code == 404, "Canceling non-existent upload should return 404"
        assert response.json()["detail"] == "Upload not found", "Error should indicate upload not found"


@pytest.mark.asyncio
async def test_cancel_completed_upload_fails():
    """Test that canceling a completed upload fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

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
        assert init_response.status_code == 201, "Upload initiation should return 201"
        upload_id = init_response.json()["upload_id"]

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
        assert patch_response.status_code == 204, "TUS PATCH should return 204"

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": token},
        )
        assert response.status_code == 400, "Canceling completed upload should return 400"
        assert "Cannot cancel completed upload" in response.json()["detail"], "Error should indicate upload is completed"


@pytest.mark.asyncio
async def test_cancel_multiple_uploads():
    """Test canceling multiple uploads restores all slots."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 3, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

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
            assert response.status_code == 201, f"Upload initiation {i} should return 201"
            upload_ids.append(response.json()["upload_id"])

        info_url = app.url_path_for("get_public_token_info", token_value=token)
        info = await client.get(info_url)
        assert info.json()["remaining_uploads"] == 0, "All upload slots should be used"

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_ids[0]),
            params={"token": token},
        )
        assert response.status_code == 200, "First cancellation should return 200"
        assert response.json()["remaining_uploads"] == 1, "First cancellation should restore one slot"

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_ids[1]),
            params={"token": token},
        )
        assert response.status_code == 200, "Second cancellation should return 200"
        assert response.json()["remaining_uploads"] == 2, "Second cancellation should restore another slot"

        info = await client.get(info_url)
        assert info.json()["remaining_uploads"] == 2, "Token info should confirm 2 remaining uploads"


@pytest.mark.asyncio
async def test_cancel_with_nonexistent_token():
    """Test that canceling with non-existent token fails."""
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

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
        assert response.status_code == 201, "Upload initiation should return 201"
        upload_id = response.json()["upload_id"]

        response = await client.delete(
            app.url_path_for("cancel_upload", upload_id=upload_id),
            params={"token": "fake_token"},
        )
        assert response.status_code == 404, "Non-existent token should return 404"
        assert response.json()["detail"] == "Token not found", "Error should indicate token not found"
