import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.tests.conftest import seed_schema


@pytest.mark.asyncio
async def test_metadata_schema_and_validation_success():
    schema = [
        {"key": "title", "label": "Title", "type": "string", "required": True},
        {"key": "source", "label": "Source", "type": "select", "options": ["tv", "web"]},
    ]
    seed_schema(schema)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/metadata/")
        assert resp.status_code == 200
        data = resp.json()["fields"]
        assert len(data) == 2

        valid_payload = {"metadata": {"title": "News clip", "source": "tv"}}
        validate = await client.post("/api/metadata/validate", json=valid_payload)
        assert resp.status_code == 200
        assert validate.json()["metadata"]["title"] == "News clip"

        valid_payload = {"metadata": {"title": "News clip", "source": "tv"}}
        validate = await client.post("/api/metadata/validate", json=valid_payload)
        assert validate.status_code == 200
        assert validate.json()["metadata"]["title"] == "News clip"


@pytest.mark.asyncio
async def test_metadata_validation_rejects_invalid_option():
    schema = [
        {"key": "source", "label": "Source", "type": "select", "options": ["tv", "web"], "required": True},
    ]
    seed_schema(schema)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        invalid_payload = {"metadata": {"source": "radio"}}
        resp = await client.post("/api/metadata/validate", json=invalid_payload)
        assert resp.status_code == 422
        body = resp.json()
        assert body["detail"]["field"] == "source"
