import pytest
from fastapi import status

from backend.app.config import settings
from backend.app.main import app
from backend.app.routers import tokens as tokens_router


@pytest.mark.asyncio
async def test_generated_tokens_skip_leading_and_trailing_hyphens(client, monkeypatch):
    generated_values = iter(["-bad-upload", "good-upload", "bad-download-", "good-download"])

    def fake_token_urlsafe(_: int) -> str:
        return next(generated_values)

    monkeypatch.setattr(tokens_router.secrets, "token_urlsafe", fake_token_urlsafe)

    response = await client.post(
        app.url_path_for("create_token"),
        json={
            "max_uploads": 1,
            "max_size_bytes": 1000,
        },
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )

    assert response.status_code == status.HTTP_201_CREATED, "Token creation should succeed after regenerating invalid token values"

    data = response.json()

    assert data["token"] == "good-upload", "Upload token should be regenerated until it no longer starts or ends with a hyphen"
    assert data["download_token"] == "fbc_good-download", (
        "Download token should be regenerated until its generated value no longer starts or ends with a hyphen"
    )
    assert not data["token"].startswith("-"), "Upload token should not start with a hyphen"
    assert not data["token"].endswith("-"), "Upload token should not end with a hyphen"
    assert not data["download_token"].endswith("-"), "Download token should not end with a hyphen"
