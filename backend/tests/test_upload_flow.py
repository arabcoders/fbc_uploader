import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.main import app
from backend.tests.conftest import seed_schema


@pytest.mark.asyncio
async def test_token_info_and_initiate():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create token - new route
        create_url = app.url_path_for("create_token")
        r = await client.post(
            create_url,
            json={"max_uploads": 1, "max_size_bytes": 1000},
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        token = r.json()["token"]

        # Get token info - new route: /api/tokens/{token_value}/info
        info_url = app.url_path_for("get_public_token_info", token_value=token)
        info = await client.get(info_url)
        assert info.status_code == 200
        assert info.json()["remaining_uploads"] == 1

        # Initiate upload - route unchanged
        init_url = app.url_path_for("initiate_upload")
        init = await client.post(
            init_url,
            params={"token": token},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
                "filename": "file.txt",
                "size_bytes": 10,
            },
        )
        body = init.json()
        print(f"init response: {body}")
        assert init.status_code == 201
        assert body["upload_id"] > 0
        # Upload is counted immediately on initiation to prevent cheating
        assert body["remaining_uploads"] == 0

        # TUS HEAD - route unchanged
        tus_head_url = app.url_path_for("tus_head", upload_id=body["upload_id"])
        head = await client.head(tus_head_url)
        assert head.status_code == 200
        assert head.headers["Upload-Offset"] == "0"
        assert head.headers["Upload-Length"] == "10"
