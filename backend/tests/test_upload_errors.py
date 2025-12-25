import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema


async def _create_token(client: AsyncClient, **overrides) -> dict:
    payload = {"max_uploads": 2, "max_size_bytes": 1000, "allowed_mime": ["video/mp4"]}
    payload.update(overrides)
    resp = await client.post(
        app.url_path_for("create_token"),
        json=payload,
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_initiate_upload_rejects_large_file():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token = await _create_token(client, max_size_bytes=50)
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "big.bin",
                "filetype": "video/mp4",
                "size_bytes": 100,
            },
        )
        assert init.status_code == 413
        assert "File size exceeds token limit" in init.text


@pytest.mark.asyncio
async def test_initiate_upload_rejects_disallowed_mime():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token = await _create_token(client, allowed_mime=["video/mp4"])
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "text.txt",
                "filetype": "text/plain",
                "size_bytes": 10,
            },
        )
        assert init.status_code == 415
        assert "File type not allowed" in init.text


@pytest.mark.asyncio
async def test_download_fails_until_completed():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token = await _create_token(client)
        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token["token"]},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Clip", "source": "youtube"},
                "filename": "clip.mp4",
                "filetype": "video/mp4",
                "size_bytes": 5,
            },
        )
        upload_id = init.json()["upload_id"]

        download = await client.get(
            app.url_path_for("download_file", download_token=token["download_token"], upload_id=upload_id),
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert download.status_code == 409
        assert "not yet completed" in download.text
