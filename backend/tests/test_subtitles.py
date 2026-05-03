from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status

from backend.app.main import app
from backend.tests.utils import create_token, initiate_upload, upload_file_via_tus


def _write_subtitle_file(root: Path, relative_path: str, content: str) -> Path:
    subtitle_path = root / relative_path
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path.write_text(content, encoding="utf-8")
    return subtitle_path


@pytest.mark.asyncio
async def test_list_file_subtitles_prefers_native_formats(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-native"
    _write_subtitle_file(subtitle_root, "show/episode.vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")
    _write_subtitle_file(subtitle_root, "show/episode.ass", "[Script Info]\nTitle: Example\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "episode.mkv", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(app.url_path_for("list_file_subtitles", download_token=download_token, upload_id=upload_id))

        assert response.status_code == status.HTTP_200_OK, "Subtitle manifest should be returned"
        data = response.json()
        assert [item["source_format"] for item in data["subtitles"]] == ["vtt", "ass"], (
            "Native subtitle formats should be returned before ASS"
        )
        assert data["subtitles"][0]["renderer"] == "native", "VTT should use the native browser renderer"


@pytest.mark.asyncio
async def test_list_file_subtitles_skips_ambiguous_extension_matches(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-ambiguous"
    _write_subtitle_file(subtitle_root, "one/sample.ass", "[Script Info]\nTitle: A\n")
    _write_subtitle_file(subtitle_root, "two/sample.ass", "[Script Info]\nTitle: B\n")
    _write_subtitle_file(subtitle_root, "three/sample.vtt", "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "sample.mp4", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(app.url_path_for("list_file_subtitles", download_token=download_token, upload_id=upload_id))

        assert response.status_code == status.HTTP_200_OK, "Subtitle manifest should still be returned"
        data = response.json()
        assert [item["source_format"] for item in data["subtitles"]] == ["vtt"], (
            "Ambiguous extension matches should be ignored instead of guessing"
        )


@pytest.mark.asyncio
async def test_get_file_subtitle_converts_srt_to_vtt(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-srt"
    _write_subtitle_file(
        subtitle_root,
        "sample.srt",
        "1\n00:00:01,000 --> 00:00:02,250\nHello there\n",
    )

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "sample.mp4", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="srt")
        )

        assert response.status_code == status.HTTP_200_OK, "SRT subtitle endpoint should return converted content"
        assert response.headers["content-type"].startswith("text/vtt"), "SRT subtitles should be delivered as WebVTT"
        assert response.text.startswith("WEBVTT\n\n1\n00:00:01.000 --> 00:00:02.250\nHello there\n"), (
            "SRT timestamps should be converted to WebVTT format"
        )


@pytest.mark.asyncio
async def test_get_file_subtitle_respects_download_access_rules(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-access"
    _write_subtitle_file(subtitle_root, "secure.ass", "[Script Info]\nTitle: Example\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", False),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "secure.mp4", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED, (
            "Subtitle delivery should require the same authentication as other protected download endpoints"
        )


@pytest.mark.asyncio
async def test_get_file_subtitle_returns_404_when_feature_disabled(client):
    token_data = await create_token(client, max_uploads=1)
    upload_token = token_data["token"]
    download_token = token_data["download_token"]

    upload_data = await initiate_upload(client, upload_token, "missing.mp4", 5, "video/mp4")
    upload_id = upload_data["upload_id"]
    status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

    assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

    with patch("backend.app.config.settings.subtitle_path", None), patch("backend.app.security.settings.allow_public_downloads", True):
        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="vtt")
        )

    assert response.status_code == status.HTTP_404_NOT_FOUND, "Subtitle endpoints should be disabled when no subtitle path is configured"
