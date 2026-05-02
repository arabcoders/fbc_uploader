import pytest
from fastapi import status
from httpx import ASGITransport, AsyncClient

from backend.app.main import app
from backend.tests.conftest import seed_schema
from backend.tests.utils import validate_metadata


@pytest.mark.asyncio
async def test_metadata_schema_and_validation_success():
    schema = [
        {"key": "title", "label": "Title", "type": "string", "required": True},
        {"key": "source", "label": "Source", "type": "select", "options": ["tv", "web"]},
    ]
    seed_schema(schema)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get(app.url_path_for("metadata_schema"))
        assert resp.status_code == status.HTTP_200_OK, "Schema endpoint should return 200"
        data = resp.json()["fields"]
        assert len(data) == 2, "Schema should contain 2 fields"

        status_code, result = await validate_metadata(client, {"title": "News clip", "source": "tv"})
        assert status_code == status.HTTP_200_OK, "Valid metadata should pass validation"
        assert result["metadata"]["title"] == "News clip", "Metadata title should be preserved"


@pytest.mark.asyncio
async def test_metadata_validation_rejects_invalid_option():
    schema = [
        {"key": "source", "label": "Source", "type": "select", "options": ["tv", "web"], "required": True},
    ]
    seed_schema(schema)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        status_code, result = await validate_metadata(client, {"source": "radio"})
        assert status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, "Invalid select option should return 422"
        assert result["detail"]["field"] == "source", "Error should indicate 'source' field"


@pytest.mark.asyncio
async def test_metadata_extraction_returns_matching_fields():
    schema = [
        {
            "key": "broadcast_date",
            "label": "Broadcast Date",
            "type": "date",
            "extract_regex": "(?P<year>\\d{2})(?P<month>\\d{2})(?P<day>\\d{2})",
        },
        {
            "key": "title",
            "label": "Title",
            "type": "string",
            "extract_regex": "^(?:.*?\\b\\d{6,8}\\b\\s*)?(.+?)(?=\\s*[\\[(]|\\.\\w+$)",
        },
        {
            "key": "source",
            "label": "Source",
            "type": "select",
            "extract_regex": "(?:^|[^A-Za-z0-9])((?:youtube|tver))(?:[^A-Za-z0-9]|$)",
        },
        {
            "key": "source_id",
            "label": "Source ID",
            "type": "string",
            "extract_regex": "(?:^|[^A-Za-z0-9])\\[(?:youtube|tver)-([^\\]]+)\\](?:[^A-Za-z0-9]|$)",
        },
    ]
    seed_schema(schema)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            app.url_path_for("metadata_schema_extract"),
            json={"filename": "240101 Example Show [youtube-dQw4w9WgXcQ].mp4"},
        )

        assert resp.status_code == status.HTTP_200_OK, "Extraction endpoint should return 200"
        assert resp.json()["metadata"] == {
            "broadcast_date": "2024-01-01",
            "title": "Example Show",
            "source": "youtube",
            "source_id": "dQw4w9WgXcQ",
        }, "Extraction endpoint should return parsed metadata"


@pytest.mark.asyncio
async def test_metadata_extraction_returns_empty_metadata_when_nothing_matches():
    seed_schema(
        [
            {
                "key": "title",
                "label": "Title",
                "type": "string",
                "extract_regex": "source-(\\w+)",
            },
        ]
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            app.url_path_for("metadata_schema_extract"),
            json={"filename": "plain-file.mp4"},
        )

        assert resp.status_code == status.HTTP_200_OK, "Extraction endpoint should return 200"
        assert resp.json()["metadata"] == {}, "Extraction endpoint should return an empty object when nothing matches"
