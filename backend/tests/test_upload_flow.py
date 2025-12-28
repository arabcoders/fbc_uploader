import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import create_token, get_token_info


@pytest.mark.asyncio
async def test_token_info_and_initiate():
    seed_schema()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        token_data = await create_token(client, max_uploads=1, max_size_bytes=1000)
        token = token_data["token"]

        info = await get_token_info(client, token)
        assert info["remaining_uploads"] == 1, "Token should have 1 remaining upload"

        init = await client.post(
            app.url_path_for("initiate_upload"),
            params={"token": token},
            json={
                "meta_data": {"broadcast_date": "2024-01-01", "title": "Test", "source": "youtube"},
                "filename": "file.txt",
                "size_bytes": 10,
            },
        )
        body = init.json()
        print(f"init response: {body}")
        assert init.status_code == status.HTTP_201_CREATED, "Initiate upload should return 201"
        assert body["upload_id"] > 0, "Upload ID should be a positive integer"

        assert body["remaining_uploads"] == 0, "Remaining uploads should decrease to 0"

        tus_head_url = app.url_path_for("tus_head", upload_id=body["upload_id"])
        head = await client.head(tus_head_url)
        assert head.status_code == status.HTTP_200_OK, "TUS HEAD should return 200"
        assert head.headers["Upload-Offset"] == "0", "Initial upload offset should be 0"
        assert head.headers["Upload-Length"] == "10", "Upload length should match size_bytes"
