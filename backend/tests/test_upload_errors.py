import pytest
from fastapi import status
from httpx import AsyncClient, ASGITransport

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import create_token


@pytest.mark.asyncio
async def test_initiate_upload_rejects_large_file():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_size_bytes=50, allowed_mime=["video/mp4"])
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "big.bin",
                "filetype": "video/mp4",
                "size_bytes": 100,
            },
        )
        assert init.status_code == status.HTTP_413_CONTENT_TOO_LARGE, "Large file should be rejected with 413"
        data = init.json()
        assert init.headers["content-type"].startswith("application/json"), "Large file rejection should return a JSON error response"
        assert "detail" in data, "Large file rejection should include error detail"


@pytest.mark.asyncio
async def test_initiate_upload_rejects_disallowed_mime():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, allowed_mime=["video/mp4"])
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "text.txt",
                "filetype": "text/plain",
                "size_bytes": 10,
            },
        )
        assert init.status_code == status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Disallowed MIME type should be rejected with 415"
        data = init.json()
        assert init.headers["content-type"].startswith("application/json"), "Disallowed MIME rejection should return a JSON error response"
        assert "detail" in data, "Disallowed MIME rejection should include error detail"


@pytest.mark.asyncio
async def test_download_fails_until_completed():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, allowed_mime=["video/mp4"])
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token_data["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "clip.mp4",
                "filetype": "video/mp4",
                "size_bytes": 5,
            },
        )
        upload_id = init.json()["upload_id"]

        download = await client.get(
            app.url_path_for("download_file", download_token=token_data["download_token"], upload_id=upload_id),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert download.status_code == status.HTTP_409_CONFLICT, "Download incomplete upload should return 409"
        data = download.json()
        assert download.headers["content-type"].startswith("application/json"), "Incomplete download should return a JSON error response"
        assert "detail" in data, "Incomplete download should include error detail"
