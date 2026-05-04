from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status

from backend.app import subtitles
from backend.app.main import app
from backend.tests.utils import create_token, initiate_upload, upload_file_via_tus


def _write_subtitle_file(root: Path, relative_path: str, content: str) -> Path:
    subtitle_path = root / relative_path
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    subtitle_path.write_text(content, encoding="utf-8")
    return subtitle_path


@pytest.fixture(autouse=True)
def clear_subtitle_lookup_cache():
    subtitles.clear_subtitle_lookup_cache()
    yield
    subtitles.clear_subtitle_lookup_cache()


def test_list_subtitle_tracks_caches_hits_by_upload(test_run_dir):
    subtitle_root = test_run_dir / "subtitles-cache-hit"
    _write_subtitle_file(subtitle_root, "cacheme.ass", "[Script Info]\nTitle: Cached\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.config.settings.subtitle_cache_ttl_seconds", 600),
        patch("backend.app.subtitles._collect_matching_subtitles", wraps=subtitles._collect_matching_subtitles) as collect_matches,
    ):
        first_tracks = subtitles.list_subtitle_tracks("upload-1", "cacheme.mp4")
        second_tracks = subtitles.list_subtitle_tracks("upload-1", "cacheme.mp4")

    assert [track.source_format for track in first_tracks] == ["ass"], "Initial subtitle lookup should find the ASS track"
    assert [track.source_format for track in second_tracks] == ["ass"], "Cached hit should return the same subtitle track"
    assert collect_matches.call_count == 1, "Cached subtitle hits should avoid rescanning the subtitle directory"


def test_list_subtitle_tracks_caches_misses_by_upload(test_run_dir):
    subtitle_root = test_run_dir / "subtitles-cache-miss"
    subtitle_root.mkdir(parents=True, exist_ok=True)

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.config.settings.subtitle_cache_ttl_seconds", 600),
        patch("backend.app.subtitles._collect_matching_subtitles", wraps=subtitles._collect_matching_subtitles) as collect_matches,
    ):
        first_tracks = subtitles.list_subtitle_tracks("upload-1", "missing.mp4")
        _write_subtitle_file(subtitle_root, "missing.ass", "[Script Info]\nTitle: Added Later\n")
        second_tracks = subtitles.list_subtitle_tracks("upload-1", "missing.mp4")

    assert first_tracks == [], "Initial lookup should return no subtitle tracks"
    assert second_tracks == [], "Cached misses should suppress rescans during the TTL window"
    assert collect_matches.call_count == 1, "Cached misses should avoid rescanning the subtitle directory"


def test_list_subtitle_tracks_cache_is_scoped_per_upload(test_run_dir):
    subtitle_root = test_run_dir / "subtitles-cache-scope"
    subtitle_root.mkdir(parents=True, exist_ok=True)

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.config.settings.subtitle_cache_ttl_seconds", 600),
        patch("backend.app.subtitles._collect_matching_subtitles", wraps=subtitles._collect_matching_subtitles) as collect_matches,
    ):
        first_tracks = subtitles.list_subtitle_tracks("upload-1", "shared.mp4")
        _write_subtitle_file(subtitle_root, "shared.ass", "[Script Info]\nTitle: Shared\n")
        second_tracks = subtitles.list_subtitle_tracks("upload-2", "shared.mp4")

    assert first_tracks == [], "The first upload should cache a miss before subtitles exist"
    assert [track.source_format for track in second_tracks] == ["ass"], (
        "A different upload ID should not reuse another upload's cached subtitle miss"
    )
    assert collect_matches.call_count == 2, "Subtitle caching should be keyed per upload rather than by filename alone"


def test_list_subtitle_tracks_rechecks_after_cache_ttl_expires(test_run_dir):
    subtitle_root = test_run_dir / "subtitles-cache-expiry"
    subtitle_root.mkdir(parents=True, exist_ok=True)

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.config.settings.subtitle_cache_ttl_seconds", 10),
        patch("backend.app.subtitles._collect_matching_subtitles", wraps=subtitles._collect_matching_subtitles) as collect_matches,
        patch("backend.app.subtitles.time.monotonic", side_effect=[100.0, 100.0, 105.0, 111.0, 111.0]),
    ):
        first_tracks = subtitles.list_subtitle_tracks("upload-1", "expiring.mp4")
        _write_subtitle_file(subtitle_root, "expiring.ass", "[Script Info]\nTitle: Expired\n")
        cached_tracks = subtitles.list_subtitle_tracks("upload-1", "expiring.mp4")
        refreshed_tracks = subtitles.list_subtitle_tracks("upload-1", "expiring.mp4")

    assert first_tracks == [], "The initial lookup should cache the missing subtitle result"
    assert cached_tracks == [], "The cached miss should still apply before the TTL expires"
    assert [track.source_format for track in refreshed_tracks] == ["ass"], "Subtitle discovery should rescan once the cache TTL has expired"
    assert collect_matches.call_count == 2, "Expired cache entries should trigger a fresh subtitle scan"


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
async def test_list_file_subtitles_supports_prefix_language_suffixes(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-prefix"
    _write_subtitle_file(subtitle_root, "show/episode.en-US.ass", "[Script Info]\nTitle: Example\n")

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
        assert [item["source_format"] for item in data["subtitles"]] == ["ass"], (
            "Prefix-matching language-tagged subtitles should be detected"
        )


@pytest.mark.asyncio
async def test_list_file_subtitles_supports_duplicate_leading_prefixes(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-duplicate-prefix"
    _write_subtitle_file(
        subtitle_root, "260503 260503 Rajira! Sunday 川﨑桜、梅澤美波 [REQUEST].ass", "[Script Info]\nTitle: Duplicate Prefix\n"
    )

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "260503 Rajira! Sunday 川﨑桜、梅澤美波.mp4", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, "Repeated leading prefixes should still allow subtitle matching"
        assert "Title: Duplicate Prefix" in response.text, (
            "Subtitle matching should tolerate duplicate leading date prefixes before the shared filename stem"
        )


@pytest.mark.asyncio
async def test_list_file_subtitles_uses_bracket_stripping_as_last_resort(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-bracket-fallback"
    _write_subtitle_file(subtitle_root, "260602 foo [fbc-bar].ass", "[Script Info]\nTitle: Bracket Fallback\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "260602 foo [youtube-bar].mkv", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, "Bracket-stripped fallback should recover subtitle matches as a last resort"
        assert "Title: Bracket Fallback" in response.text, (
            "When normal matching fails, differing bracketed source tags should be ignored for subtitle matching"
        )


@pytest.mark.asyncio
async def test_list_file_subtitles_uses_bracket_stripping_with_contains_fallback(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-bracket-contains"
    _write_subtitle_file(subtitle_root, "260602 260602 foo [fbc-bar] [REQUEST].ass", "[Script Info]\nTitle: Bracket Contains\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "260602 foo [youtube-bar].mkv", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, (
            "Bracket stripping should still use the same bounded contains logic as the normal subtitle matcher"
        )
        assert "Title: Bracket Contains" in response.text, (
            "Bracket-stripped fallback should support duplicate leading prefixes and bracket suffixes together"
        )


@pytest.mark.asyncio
async def test_list_file_subtitles_prefers_normal_match_over_bracket_stripping_fallback(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-bracket-precedence"
    _write_subtitle_file(subtitle_root, "260602 foo [youtube-bar].ass", "[Script Info]\nTitle: Exact Bracket\n")
    _write_subtitle_file(subtitle_root, "260602 foo [fbc-bar].ass", "[Script Info]\nTitle: Fallback Bracket\n")

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, "260602 foo [youtube-bar].mkv", 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, "Subtitle should still be returned when an exact bracketed match exists"
        assert "Title: Exact Bracket" in response.text, "Bracket stripping should only run after normal subtitle matching fails"


@pytest.mark.asyncio
async def test_list_file_subtitles_prefers_exact_stem_over_prefix_matches(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-exact-first"
    _write_subtitle_file(subtitle_root, "show/episode.ass", "[Script Info]\nTitle: Exact\n")
    _write_subtitle_file(subtitle_root, "show/episode.en.ass", "[Script Info]\nTitle: Prefix\n")

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

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, "Exact stem subtitle should be returned"
        assert "Title: Exact" in response.text, "Exact stem matches should win over language-suffixed prefix matches"


@pytest.mark.asyncio
async def test_list_file_subtitles_ignores_midword_contains_matches(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-midword"
    _write_subtitle_file(subtitle_root, "myepisode.ass", "[Script Info]\nTitle: Midword\n")

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

        assert response.status_code == status.HTTP_200_OK, "Subtitle manifest should still be returned"
        assert response.json()["subtitles"] == [], "Contains matching should not match unrelated mid-word stems"


@pytest.mark.asyncio
async def test_list_file_subtitles_skips_ambiguous_extension_matches(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-ambiguous"
    _write_subtitle_file(subtitle_root, "one/sample.en.ass", "[Script Info]\nTitle: A\n")
    _write_subtitle_file(subtitle_root, "two/sample.fr.ass", "[Script Info]\nTitle: B\n")
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
async def test_list_file_subtitles_matches_normalized_japanese_filenames(client, test_run_dir):
    subtitle_root = test_run_dir / "subtitles-japanese"
    _write_subtitle_file(subtitle_root, "森川 優.ass", "[Script Info]\nTitle: Japanese\n")

    decomposed_filename = "森川 優".replace("優", "優") + ".mp4"

    with (
        patch("backend.app.config.settings.subtitle_path", str(subtitle_root)),
        patch("backend.app.security.settings.allow_public_downloads", True),
    ):
        token_data = await create_token(client, max_uploads=1)
        upload_token = token_data["token"]
        download_token = token_data["download_token"]

        upload_data = await initiate_upload(client, upload_token, decomposed_filename, 5, "video/mp4")
        upload_id = upload_data["upload_id"]
        status_code = await upload_file_via_tus(client, upload_id, b"hello", upload_token)

        assert status_code == status.HTTP_200_OK, "Upload should complete successfully"

        response = await client.get(
            app.url_path_for("get_file_subtitle", download_token=download_token, upload_id=upload_id, source_format="ass")
        )

        assert response.status_code == status.HTTP_200_OK, "Normalized Japanese subtitle stems should match"
        assert "Title: Japanese" in response.text, "Japanese subtitle content should be returned"


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
