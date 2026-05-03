from __future__ import annotations

import contextlib
import re
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


def list_subtitle_tracks(filename: str | None) -> list[SubtitleTrack]:
    subtitle_root = get_subtitle_root()
    if subtitle_root is None or not filename:
        return []

    target_stem = Path(filename).stem.casefold()
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

    return subtitle_tracks


def get_subtitle_track(filename: str | None, source_format: str) -> SubtitleTrack | None:
    normalized_source_format = normalize_source_format(source_format)
    if normalized_source_format is None:
        return None

    return next(
        (track for track in list_subtitle_tracks(filename) if track.source_format == normalized_source_format),
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


def _collect_matching_subtitles(subtitle_root: Path, target_stem: str) -> dict[str, list[Path]]:
    matches_by_format: dict[str, list[Path]] = {source_format: [] for source_format in SUPPORTED_SUBTITLE_SOURCE_FORMATS}

    for candidate in subtitle_root.rglob("*"):
        source_format = normalize_source_format(candidate.suffix.lstrip("."))
        if source_format is None or candidate.stem.casefold() != target_stem:
            continue

        resolved_candidate = _resolve_within_root(candidate, subtitle_root)
        if resolved_candidate is None:
            continue

        matches_by_format[source_format].append(resolved_candidate)

    return matches_by_format


def _resolve_within_root(candidate: Path, subtitle_root: Path) -> Path | None:
    with contextlib.suppress(OSError, RuntimeError):
        resolved_candidate = candidate.resolve()
        if resolved_candidate.is_file() and resolved_candidate.is_relative_to(subtitle_root):
            return resolved_candidate

    return None
