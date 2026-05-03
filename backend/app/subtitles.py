from __future__ import annotations

import contextlib
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from backend.app import config

SUPPORTED_SUBTITLE_SOURCE_FORMATS: tuple[str, ...] = ("vtt", "srt", "ass")
DELIVERY_FORMAT_BY_SOURCE_FORMAT: dict[str, str] = {
    "vtt": "vtt",
    "srt": "vtt",
    "ass": "ass",
}
RENDERER_BY_SOURCE_FORMAT: dict[str, str] = {
    "vtt": "native",
    "srt": "native",
    "ass": "assjs",
}
DELIVERY_MEDIA_TYPE_BY_FORMAT: dict[str, str] = {
    "vtt": "text/vtt; charset=utf-8",
    "ass": "text/x-ssa; charset=utf-8",
}
TEXT_DECODING_CANDIDATES: tuple[str, ...] = ("utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252")
SRT_TIMESTAMP_RE = re.compile(r"(?P<time>\d{1,2}:\d{2}:\d{2}),(?P<millis>\d{3})")


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    path: Path
    source_format: str
    delivery_format: str
    renderer: str


@dataclass(frozen=True, slots=True)
class SubtitleLookupCacheEntry:
    tracks: tuple[SubtitleTrack, ...]
    expires_at: float


SubtitleLookupCacheKey = tuple[str, str]
_subtitle_lookup_cache: dict[SubtitleLookupCacheKey, SubtitleLookupCacheEntry] = {}


def get_subtitle_root() -> Path | None:
    subtitle_path = config.settings.subtitle_path
    if not subtitle_path:
        return None

    return Path(subtitle_path).expanduser().resolve()


def normalize_source_format(source_format: str) -> str | None:
    normalized_source_format = source_format.strip().casefold()
    if normalized_source_format not in SUPPORTED_SUBTITLE_SOURCE_FORMATS:
        return None

    return normalized_source_format


def normalize_subtitle_stem(stem: str) -> str:
    return unicodedata.normalize("NFC", stem).casefold().strip()


def normalize_cache_identity(identity: str) -> str:
    return unicodedata.normalize("NFC", identity).strip()


def build_subtitle_cache_key(upload_id: str, filename: str) -> SubtitleLookupCacheKey:
    return normalize_cache_identity(upload_id), normalize_cache_identity(filename)


def clear_subtitle_lookup_cache() -> None:
    _subtitle_lookup_cache.clear()


def list_subtitle_tracks(upload_id: str | None, filename: str | None) -> list[SubtitleTrack]:
    subtitle_root = get_subtitle_root()
    if subtitle_root is None or not upload_id or not filename:
        return []

    cache_ttl_seconds = config.settings.subtitle_cache_ttl_seconds
    cache_key = build_subtitle_cache_key(upload_id, filename)
    cached_tracks = _get_cached_subtitle_tracks(cache_key, cache_ttl_seconds)
    if cached_tracks is not None:
        return cached_tracks

    target_stem = normalize_subtitle_stem(Path(filename).stem)
    if not target_stem:
        return []

    matches_by_format = _collect_matching_subtitles(subtitle_root, target_stem)
    subtitle_tracks: list[SubtitleTrack] = []

    for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS:
        matches = matches_by_format.get(source_format, [])
        if len(matches) != 1:
            continue

        subtitle_tracks.append(
            SubtitleTrack(
                path=matches[0],
                source_format=source_format,
                delivery_format=DELIVERY_FORMAT_BY_SOURCE_FORMAT[source_format],
                renderer=RENDERER_BY_SOURCE_FORMAT[source_format],
            )
        )

    _store_cached_subtitle_tracks(cache_key, subtitle_tracks, cache_ttl_seconds)
    return subtitle_tracks


def get_subtitle_track(upload_id: str | None, filename: str | None, source_format: str) -> SubtitleTrack | None:
    normalized_source_format = normalize_source_format(source_format)
    if normalized_source_format is None:
        return None

    return next(
        (track for track in list_subtitle_tracks(upload_id, filename) if track.source_format == normalized_source_format),
        None,
    )


def read_subtitle_text(path: str | Path) -> str:
    subtitle_bytes = Path(path).read_bytes()
    for encoding in TEXT_DECODING_CANDIDATES:
        with contextlib.suppress(UnicodeDecodeError):
            return subtitle_bytes.decode(encoding)

    return subtitle_bytes.decode("utf-8", errors="replace")


def get_delivery_content(track: SubtitleTrack) -> str:
    subtitle_text = read_subtitle_text(track.path)
    if track.source_format == "srt":
        return convert_srt_to_vtt(subtitle_text)

    return subtitle_text


def get_delivery_media_type(track: SubtitleTrack) -> str:
    return DELIVERY_MEDIA_TYPE_BY_FORMAT[track.delivery_format]


def convert_srt_to_vtt(srt_content: str) -> str:
    normalized_content = srt_content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    converted_content = SRT_TIMESTAMP_RE.sub(r"\g<time>.\g<millis>", normalized_content).lstrip("\n")
    return f"WEBVTT\n\n{converted_content}" if converted_content else "WEBVTT\n\n"


def _get_cached_subtitle_tracks(
    cache_key: SubtitleLookupCacheKey,
    cache_ttl_seconds: int,
) -> list[SubtitleTrack] | None:
    if cache_ttl_seconds <= 0:
        return None

    now = time.monotonic()
    cache_entry = _subtitle_lookup_cache.get(cache_key)
    if cache_entry is None:
        return None

    if cache_entry.expires_at <= now:
        _subtitle_lookup_cache.pop(cache_key, None)
        return None

    return list(cache_entry.tracks)


def _store_cached_subtitle_tracks(
    cache_key: SubtitleLookupCacheKey,
    subtitle_tracks: list[SubtitleTrack],
    cache_ttl_seconds: int,
) -> None:
    if cache_ttl_seconds <= 0:
        return

    _subtitle_lookup_cache[cache_key] = SubtitleLookupCacheEntry(
        tracks=tuple(subtitle_tracks),
        expires_at=time.monotonic() + cache_ttl_seconds,
    )


def _collect_matching_subtitles(subtitle_root: Path, target_stem: str) -> dict[str, list[Path]]:
    matches_by_format: dict[str, list[Path]] = {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}
    exact_matches_by_format: dict[str, list[Path]] = {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}
    prefix_matches_by_format: dict[str, list[Path]] = {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}

    for candidate in subtitle_root.rglob("*"):
        source_format = normalize_source_format(candidate.suffix.lstrip("."))
        if source_format is None:
            continue

        candidate_stem = normalize_subtitle_stem(candidate.stem)
        if not candidate_stem.startswith(target_stem):
            continue

        resolved_candidate = _resolve_within_root(candidate, subtitle_root)
        if resolved_candidate is None:
            continue

        if candidate_stem == target_stem:
            exact_matches_by_format[source_format].append(resolved_candidate)
            continue

        prefix_matches_by_format[source_format].append(resolved_candidate)

    for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS:
        exact_matches = exact_matches_by_format[source_format]
        prefix_matches = prefix_matches_by_format[source_format]
        matches_by_format[source_format] = exact_matches or prefix_matches

    return matches_by_format


def _resolve_within_root(candidate: Path, subtitle_root: Path) -> Path | None:
    with contextlib.suppress(OSError, RuntimeError):
        resolved_candidate = candidate.resolve()
        if resolved_candidate.is_file() and resolved_candidate.is_relative_to(subtitle_root):
            return resolved_candidate

    return None
