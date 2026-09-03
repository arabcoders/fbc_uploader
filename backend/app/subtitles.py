from __future__ import annotations

import contextlib
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from backend.app import config

SubtitleSourceFormat = Literal["vtt", "srt", "ass"]
SubtitleDeliveryFormat = Literal["vtt", "ass"]
SubtitleRenderer = Literal["native", "assjs"]

SUPPORTED_SUBTITLE_SOURCE_FORMATS: tuple[SubtitleSourceFormat, ...] = ("vtt", "srt", "ass")
DELIVERY_FORMAT_BY_SOURCE_FORMAT: dict[SubtitleSourceFormat, SubtitleDeliveryFormat] = {
    "vtt": "vtt",
    "srt": "vtt",
    "ass": "ass",
}
RENDERER_BY_SOURCE_FORMAT: dict[SubtitleSourceFormat, SubtitleRenderer] = {
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
BRACKETED_SEGMENT_RE = re.compile(r"\[[^\[\]]*\]")
WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SubtitleTrack:
    path: Path
    source_format: SubtitleSourceFormat
    delivery_format: SubtitleDeliveryFormat
    renderer: SubtitleRenderer


@dataclass(frozen=True, slots=True)
class SubtitleLookupCacheEntry:
    tracks: tuple[SubtitleTrack, ...]
    expires_at: float


SubtitleLookupCacheKey = tuple[str, str, tuple[str, ...]]
_subtitle_lookup_cache: dict[SubtitleLookupCacheKey, SubtitleLookupCacheEntry] = {}


def get_subtitle_root() -> Path | None:
    subtitle_path = config.settings.subtitle_path
    if not subtitle_path:
        return None

    return Path(subtitle_path).expanduser().resolve()


def normalize_source_format(source_format: str) -> SubtitleSourceFormat | None:
    normalized_source_format = source_format.strip().casefold()
    if normalized_source_format == "vtt":
        return "vtt"
    if normalized_source_format == "srt":
        return "srt"
    if normalized_source_format == "ass":
        return "ass"
    return None


def normalize_subtitle_stem(stem: str) -> str:
    return unicodedata.normalize("NFKC", stem).casefold().strip()


def normalize_cache_identity(identity: str) -> str:
    return unicodedata.normalize("NFC", identity).strip()


def build_subtitle_cache_key(upload_id: str, filename: str | None, target_stems: list[str]) -> SubtitleLookupCacheKey:
    return normalize_cache_identity(upload_id), normalize_cache_identity(filename or ""), tuple(target_stems)


def clear_subtitle_lookup_cache() -> None:
    _subtitle_lookup_cache.clear()


def list_subtitle_tracks(
    upload_id: str | None,
    filename: str | None,
    meta_data: dict | None = None,
) -> list[SubtitleTrack]:
    subtitle_root = get_subtitle_root()
    if subtitle_root is None or not upload_id:
        return []

    target_stems = _build_target_stems(filename, meta_data)
    cache_ttl_seconds = config.settings.subtitle_cache_ttl_seconds
    cache_key = build_subtitle_cache_key(upload_id, filename, target_stems)
    cached_tracks = _get_cached_subtitle_tracks(cache_key, cache_ttl_seconds)
    if cached_tracks is not None:
        return cached_tracks

    subtitle_tracks = _build_subtitle_tracks(_collect_matching_subtitles(subtitle_root, normalize_subtitle_stem(upload_id), target_stems))

    _store_cached_subtitle_tracks(cache_key, subtitle_tracks, cache_ttl_seconds)
    return subtitle_tracks


def get_subtitle_track(
    upload_id: str | None,
    filename: str | None,
    source_format: str,
    meta_data: dict | None = None,
) -> SubtitleTrack | None:
    normalized_source_format = normalize_source_format(source_format)
    if normalized_source_format is None:
        return None

    return next(
        (track for track in list_subtitle_tracks(upload_id, filename, meta_data) if track.source_format == normalized_source_format),
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


def _build_subtitle_tracks(matches_by_format: dict[str, list[Path]]) -> list[SubtitleTrack]:
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

    return subtitle_tracks


def _build_target_stems(filename: str | None, meta_data: dict | None) -> list[str]:
    stems: list[str] = []
    if filename:
        stems.append(Path(filename).stem)

    title = meta_data.get("title") if isinstance(meta_data, dict) else None
    if isinstance(title, str) and title.strip():
        broadcast_date = meta_data.get("broadcast_date") if isinstance(meta_data, dict) else None
        if isinstance(broadcast_date, str):
            date_match = re.fullmatch(r"(?P<year>\d{4})[-._]?(?P<month>\d{2})[-._]?(?P<day>\d{2})", broadcast_date.strip())
            if date_match:
                year = date_match.group("year")
                month_day = f"{date_match.group('month')}{date_match.group('day')}"
                stems.extend((f"{year[2:]}{month_day} {title}", f"{year}{month_day} {title}"))
        stems.append(title)

    normalized_stems: list[str] = []
    for stem in stems:
        normalized_stem = normalize_subtitle_stem(stem)
        if normalized_stem and normalized_stem not in normalized_stems:
            normalized_stems.append(normalized_stem)

    return normalized_stems


def _empty_matches() -> dict[str, list[Path]]:
    return {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}


def _collect_matching_subtitles(subtitle_root: Path, upload_id: str, target_stems: list[str]) -> dict[str, list[Path]]:
    upload_matches_by_format = _empty_matches()
    normal_matches = [(_empty_matches(), _empty_matches()) for _ in target_stems]
    stripped_matches = [(_empty_matches(), _empty_matches()) for _ in target_stems]
    stripped_target_stems = [_strip_bracketed_segments(target_stem) for target_stem in target_stems]

    for candidate in subtitle_root.rglob("*"):
        source_format = normalize_source_format(candidate.suffix.lstrip("."))
        if source_format is None:
            continue

        candidate_stem = normalize_subtitle_stem(candidate.stem)
        if not candidate_stem:
            continue

        resolved_candidate = _resolve_within_root(candidate, subtitle_root)
        if resolved_candidate is None:
            continue

        if upload_id and upload_id in candidate_stem:
            upload_matches_by_format[source_format].append(resolved_candidate)

        stripped_candidate_stem = _strip_bracketed_segments(candidate_stem)
        for index, target_stem in enumerate(target_stems):
            exact_matches, prefix_matches = normal_matches[index]
            if candidate_stem == target_stem:
                exact_matches[source_format].append(resolved_candidate)
            elif _contains_subtitle_stem(candidate_stem, target_stem):
                prefix_matches[source_format].append(resolved_candidate)

            stripped_target_stem = stripped_target_stems[index]
            if not stripped_target_stem or not stripped_candidate_stem:
                continue

            stripped_exact_matches, stripped_prefix_matches = stripped_matches[index]
            if stripped_candidate_stem == stripped_target_stem:
                stripped_exact_matches[source_format].append(resolved_candidate)
            elif _contains_subtitle_stem(stripped_candidate_stem, stripped_target_stem):
                stripped_prefix_matches[source_format].append(resolved_candidate)

    if any(upload_matches_by_format.values()):
        return upload_matches_by_format

    for index, (exact_matches, prefix_matches) in enumerate(normal_matches):
        matches_by_format = _merge_matching_subtitles(exact_matches, prefix_matches)
        if _build_subtitle_tracks(matches_by_format):
            return matches_by_format

        stripped_exact_matches, stripped_prefix_matches = stripped_matches[index]
        matches_by_format = _merge_matching_subtitles(stripped_exact_matches, stripped_prefix_matches)
        if _build_subtitle_tracks(matches_by_format):
            return matches_by_format

    return _empty_matches()


def _resolve_within_root(candidate: Path, subtitle_root: Path) -> Path | None:
    with contextlib.suppress(OSError, RuntimeError):
        resolved_candidate = candidate.resolve()
        if resolved_candidate.is_file() and resolved_candidate.is_relative_to(subtitle_root):
            return resolved_candidate

    return None


def _contains_subtitle_stem(candidate_stem: str, target_stem: str) -> bool:
    match_start = candidate_stem.find(target_stem)
    while match_start != -1:
        match_end = match_start + len(target_stem)
        has_left_boundary = match_start == 0 or not candidate_stem[match_start - 1].isalnum()
        has_right_boundary = match_end == len(candidate_stem) or not candidate_stem[match_end].isalnum()
        if has_left_boundary and has_right_boundary:
            return True
        match_start = candidate_stem.find(target_stem, match_start + 1)

    return False


def _strip_bracketed_segments(stem: str) -> str:
    stripped_stem = BRACKETED_SEGMENT_RE.sub(" ", stem)
    return WHITESPACE_RE.sub(" ", stripped_stem).strip()


def _merge_matching_subtitles(
    exact_matches_by_format: dict[str, list[Path]],
    prefix_matches_by_format: dict[str, list[Path]],
) -> dict[str, list[Path]]:
    matches_by_format: dict[str, list[Path]] = {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}

    for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS:
        exact_matches = exact_matches_by_format[source_format]
        prefix_matches = prefix_matches_by_format[source_format]
        matches_by_format[source_format] = exact_matches or prefix_matches

    return matches_by_format
