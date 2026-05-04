"""Utility functions for file handling and validation."""

import asyncio
import contextlib
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import aiofiles
import magic

MIME = magic.Magic(mime=True)

MULTIPLIERS: dict[str, int] = {
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3,
    "t": 1024**4,
}

SUPPORTED_WEB_STREAM_TYPES: set[str] = {"video", "audio"}
WEBM_SAFE_VIDEO_CODECS: set[str] = {"vp8", "vp9", "av1"}
WEBM_SAFE_AUDIO_CODECS: set[str] = {"opus", "vorbis"}
MP4_SAFE_VIDEO_CODECS: set[str] = {"h264"}
MP4_SAFE_AUDIO_CODECS: set[str] = {"aac"}
THUMBNAIL_SUFFIX = ".thumb.jpg"
THUMBNAIL_MEDIA_TYPE = "image/jpeg"
PREVIEW_SUFFIX = ".preview.mp4"
PREVIEW_MEDIA_TYPE = "video/mp4"
THUMBNAIL_SAMPLE_FRAMES = 200
THUMBNAIL_DEFAULT_SEEK_SECONDS = 3.0
THUMBNAIL_MIN_SEEK_SECONDS = 1.0
THUMBNAIL_MAX_SEEK_SECONDS = 15.0
THUMBNAIL_END_MARGIN_SECONDS = 0.1


def recommend_chunk_size(upload_length: int | None, max_chunk_bytes: int) -> int:
    """Return a server-chosen TUS chunk size for the given upload length."""
    if max_chunk_bytes <= 0:
        msg = "max_chunk_bytes must be greater than zero"
        raise ValueError(msg)

    if upload_length is None or upload_length <= 0:
        return max_chunk_bytes

    chunk_count = max(1, math.ceil(upload_length / max_chunk_bytes))
    return max(1, math.ceil(upload_length / chunk_count))


def get_thumbnail_path(file_path: str | Path) -> Path:
    """Return the deterministic sidecar thumbnail path for an upload file."""
    path = Path(file_path)
    return path.with_name(f"{path.name}{THUMBNAIL_SUFFIX}")


def get_preview_path(file_path: str | Path) -> Path:
    """Return the deterministic sidecar preview path for an upload file."""
    path = Path(file_path)
    return path.with_name(f"{path.name}{PREVIEW_SUFFIX}")


def thumbnail_exists(file_path: str | Path) -> bool:
    """Return True when a non-empty thumbnail sidecar exists for the given upload file."""
    thumbnail_path = get_thumbnail_path(file_path)
    with contextlib.suppress(OSError):
        return thumbnail_path.exists() and thumbnail_path.stat().st_size > 0

    return False


def preview_exists(file_path: str | Path) -> bool:
    """Return True when a non-empty preview sidecar exists for the given upload file."""
    preview_path = get_preview_path(file_path)
    with contextlib.suppress(OSError):
        return preview_path.exists() and preview_path.stat().st_size > 0

    return False


def delete_upload_artifacts(file_path: str | Path | None) -> None:
    """Delete an upload file and any derived preview or thumbnail sidecars."""
    if not file_path:
        return

    path = Path(file_path)
    for candidate in (get_preview_path(path), get_thumbnail_path(path), path):
        if candidate.exists():
            with contextlib.suppress(OSError):
                candidate.unlink()


def _get_media_duration_seconds(ffprobe_data: dict | None) -> float | None:
    if not ffprobe_data:
        return None

    format_data = ffprobe_data.get("format")
    if not isinstance(format_data, dict):
        return None

    with contextlib.suppress(TypeError, ValueError):
        duration = float(format_data.get("duration"))
        if duration > 0:
            return duration

    return None


def _get_thumbnail_seek_seconds(ffprobe_data: dict | None) -> float | None:
    """Pick a seek offset that avoids intros without jumping past short videos."""
    duration = _get_media_duration_seconds(ffprobe_data)
    if duration is None:
        return THUMBNAIL_DEFAULT_SEEK_SECONDS

    if duration <= THUMBNAIL_END_MARGIN_SECONDS:
        return None

    return min(
        max(duration * 0.1, THUMBNAIL_MIN_SEEK_SECONDS),
        THUMBNAIL_MAX_SEEK_SECONDS,
        duration - THUMBNAIL_END_MARGIN_SECONDS,
    )


def should_generate_video_preview(size_bytes: int | None, *, min_size_bytes: int) -> bool:
    """Return True when a video file is large enough to warrant a generated bot preview."""
    if min_size_bytes <= 0:
        return False

    return size_bytes is not None and size_bytes >= min_size_bytes


def _build_thumbnail_command(
    ffmpeg_bin: str,
    source_path: Path,
    output_path: Path,
    *,
    seek_seconds: float | None,
) -> list[str]:
    command = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
    if seek_seconds is not None and seek_seconds > 0:
        command.extend(["-ss", f"{seek_seconds:.3f}"])

    command.extend(
        [
            "-i",
            str(source_path),
            "-vf",
            f"thumbnail={THUMBNAIL_SAMPLE_FRAMES},scale=1280:-1:force_original_aspect_ratio=decrease",
            "-frames:v",
            "1",
            "-q:v",
            "3",
            str(output_path),
        ]
    )
    return command


def _build_preview_command(
    ffmpeg_bin: str,
    source_path: Path,
    output_path: Path,
    *,
    seek_seconds: float | None,
    clip_seconds: int,
) -> list[str]:
    command = [ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y"]
    if seek_seconds is not None and seek_seconds > 0:
        command.extend(["-ss", f"{seek_seconds:.3f}"])

    command.extend(
        [
            "-i",
            str(source_path),
            "-t",
            str(clip_seconds),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-sn",
            "-dn",
            "-vf",
            "scale='trunc(min(1280,iw*min(1280/iw,720/ih))/2)*2':'trunc(min(720,ih*min(1280/iw,720/ih))/2)*2'",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(output_path),
        ]
    )
    return command


async def generate_video_thumbnail(source_path: str | Path, *, ffmpeg_bin: str = "ffmpeg") -> Path | None:
    """Generate a JPEG thumbnail sidecar for a video file when ffmpeg is available."""
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(src)

    thumbnail_path = get_thumbnail_path(src)
    if thumbnail_exists(src):
        return thumbnail_path

    if thumbnail_path.exists():
        thumbnail_path.unlink(missing_ok=True)

    if shutil.which(ffmpeg_bin) is None:
        return None

    fd, tmp_out = tempfile.mkstemp(prefix=thumbnail_path.name + ".", suffix=".part.jpg", dir=src.parent)
    os.close(fd)
    tmp_out_path = Path(tmp_out)
    proc: asyncio.subprocess.Process | None = None
    generated_thumbnail: Path | None = None
    ffprobe_data = await extract_ffprobe_metadata(src)
    seek_seconds = _get_thumbnail_seek_seconds(ffprobe_data)
    attempt_seek_offsets = [seek_seconds]
    if seek_seconds is not None and seek_seconds > 0:
        attempt_seek_offsets.append(None)

    try:
        last_error = "ffmpeg produced an empty thumbnail file"
        for attempt_seek_seconds in attempt_seek_offsets:
            tmp_out_path.unlink(missing_ok=True)
            cmd = _build_thumbnail_command(ffmpeg_bin, src, tmp_out_path, seek_seconds=attempt_seek_seconds)
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()

            if proc.returncode == 0 and tmp_out_path.exists() and tmp_out_path.stat().st_size > 0:
                tmp_out_path.replace(thumbnail_path)
                generated_thumbnail = thumbnail_path
                break

            if proc.returncode != 0:
                last_error = (
                    f"ffmpeg thumbnail generation failed (rc={proc.returncode}).\n"
                    f"stdout:\n{out.decode(errors='replace')}\n"
                    f"stderr:\n{err.decode(errors='replace')}"
                )
            else:
                last_error = "ffmpeg produced an empty thumbnail file"

        if generated_thumbnail is None:
            raise RuntimeError(last_error)

    except asyncio.CancelledError:
        if proc is not None:
            await _terminate_subprocess(proc)
        raise

    finally:
        with contextlib.suppress(Exception):
            if tmp_out_path.exists():
                tmp_out_path.unlink()

    return generated_thumbnail


async def ensure_video_thumbnail(source_path: str | Path, *, ffmpeg_bin: str = "ffmpeg") -> Path | None:
    """Return the existing thumbnail sidecar or generate it when missing."""
    if thumbnail_exists(source_path):
        return get_thumbnail_path(source_path)

    return await generate_video_thumbnail(source_path, ffmpeg_bin=ffmpeg_bin)


async def generate_video_preview(
    source_path: str | Path,
    *,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_data: dict | None = None,
    clip_seconds: int = 10,
    min_size_bytes: int = 195 * 1024 * 1024,
    ignore_size_threshold: bool = False,
) -> Path | None:
    """Generate a short MP4 preview sidecar for bot embeds when the source file is large enough."""
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(src)

    preview_path = get_preview_path(src)
    if preview_exists(src):
        return preview_path

    if preview_path.exists():
        preview_path.unlink(missing_ok=True)

    if clip_seconds < 1 or min_size_bytes <= 0 or shutil.which(ffmpeg_bin) is None:
        return None

    if not ignore_size_threshold and not should_generate_video_preview(src.stat().st_size, min_size_bytes=min_size_bytes):
        return None

    if ffprobe_data is None:
        ffprobe_data = await extract_ffprobe_metadata(src)

    seek_seconds = _get_thumbnail_seek_seconds(ffprobe_data)
    attempt_seek_offsets = [seek_seconds]
    if seek_seconds is not None and seek_seconds > 0:
        attempt_seek_offsets.append(None)

    fd, tmp_out = tempfile.mkstemp(prefix=preview_path.name + ".", suffix=".part.mp4", dir=src.parent)
    os.close(fd)
    tmp_out_path = Path(tmp_out)
    proc: asyncio.subprocess.Process | None = None
    generated_preview: Path | None = None

    try:
        last_error = "ffmpeg produced an empty preview file"
        for attempt_seek_seconds in attempt_seek_offsets:
            tmp_out_path.unlink(missing_ok=True)
            cmd = _build_preview_command(
                ffmpeg_bin,
                src,
                tmp_out_path,
                seek_seconds=attempt_seek_seconds,
                clip_seconds=clip_seconds,
            )
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()

            if proc.returncode == 0 and tmp_out_path.exists() and tmp_out_path.stat().st_size > 0:
                tmp_out_path.replace(preview_path)
                generated_preview = preview_path
                break

            if proc.returncode != 0:
                last_error = (
                    f"ffmpeg preview generation failed (rc={proc.returncode}).\n"
                    f"stdout:\n{out.decode(errors='replace')}\n"
                    f"stderr:\n{err.decode(errors='replace')}"
                )
            else:
                last_error = "ffmpeg produced an empty preview file"

        if generated_preview is None:
            raise RuntimeError(last_error)

    except asyncio.CancelledError:
        if proc is not None:
            await _terminate_subprocess(proc)
        raise

    finally:
        with contextlib.suppress(Exception):
            if tmp_out_path.exists():
                tmp_out_path.unlink()

    return generated_preview


async def ensure_video_preview(
    source_path: str | Path,
    *,
    ffmpeg_bin: str = "ffmpeg",
    ffprobe_data: dict | None = None,
    clip_seconds: int = 10,
    min_size_bytes: int = 195 * 1024 * 1024,
    ignore_size_threshold: bool = False,
) -> Path | None:
    """Return the existing preview sidecar or generate it when missing."""
    if preview_exists(source_path):
        return get_preview_path(source_path)

    return await generate_video_preview(
        source_path,
        ffmpeg_bin=ffmpeg_bin,
        ffprobe_data=ffprobe_data,
        clip_seconds=clip_seconds,
        min_size_bytes=min_size_bytes,
        ignore_size_threshold=ignore_size_threshold,
    )


async def _terminate_subprocess(proc: asyncio.subprocess.Process) -> None:
    """Terminate a subprocess cleanly and wait for it to exit."""
    if proc.returncode is not None:
        return

    with contextlib.suppress(ProcessLookupError):
        proc.terminate()

    try:
        await proc.wait()
    except asyncio.CancelledError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(ProcessLookupError):
            await proc.wait()
        raise


def detect_mimetype(file_path: str | Path) -> str:
    """
    Detect the actual MIME type of a file using libmagic.

    Args:
        file_path: Path to the file to analyze

    Returns:
        MIME type string (e.g., 'video/mp4', 'application/pdf')

    Raises:
        FileNotFoundError: If the file does not exist
        OSError: If the file cannot be read

    """
    path: Path = Path(file_path)
    if not path.exists():
        msg: str = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    return MIME.from_file(str(path))


def is_multimedia(mimetype: str) -> bool:
    """
    Check if a MIME type represents multimedia content (video or audio).

    Args:
        mimetype: MIME type string to check

    Returns:
        True if the MIME type is video/* or audio/*, False otherwise

    """
    return mimetype.startswith(("video/", "audio/"))


async def compute_file_digest(file_path: str | Path, algorithm: str = "sha256", chunk_size: int = 1024 * 1024) -> str:
    """Compute a digest for a file by streaming it from disk."""
    path = Path(file_path)
    digest = hashlib.new(algorithm)

    async with aiofiles.open(path, "rb") as file_obj:
        while chunk := await file_obj.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


async def extract_ffprobe_metadata(file_path: str | Path) -> dict | None:
    """
    Extract multimedia metadata using ffprobe.

    Args:
        file_path (str | Path): Path to the multimedia file

    Returns:
        Dictionary containing ffprobe output in JSON format, or None if extraction fails

    Raises:
        FileNotFoundError: If the file does not exist

    """
    path = Path(file_path)
    if not path.exists():
        msg: str = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    proc: asyncio.subprocess.Process | None = None

    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()

        if proc.returncode != 0:
            return None

        dct: dict | None = json.loads(stdout.decode())
        if dct and "format" in dct and "filename" in dct.get("format"):
            dct["format"].pop("filename", None)
    except asyncio.CancelledError:
        if proc is not None:
            await _terminate_subprocess(proc)
        raise
    except Exception:
        return None
    else:
        return dct


def _get_ffprobe_streams(ffprobe_data: dict | None) -> list[dict]:
    if not ffprobe_data:
        return []

    streams = ffprobe_data.get("streams")
    if not isinstance(streams, list):
        return []

    return [stream for stream in streams if isinstance(stream, dict)]


def _has_only_supported_web_streams(streams: list[dict]) -> bool:
    return bool(streams) and all(stream.get("codec_type") in SUPPORTED_WEB_STREAM_TYPES for stream in streams)


def _streams_have_allowed_codecs(streams: list[dict], codec_type: str, allowed_codecs: set[str], *, require_stream: bool) -> bool:
    matching_streams = [stream for stream in streams if stream.get("codec_type") == codec_type]
    if require_stream and not matching_streams:
        return False

    return all(str(stream.get("codec_name") or "").lower() in allowed_codecs for stream in matching_streams)


def _get_stream_codecs(streams: list[dict], codec_type: str) -> list[str]:
    return sorted({str(stream.get("codec_name") or "unknown").lower() for stream in streams if stream.get("codec_type") == codec_type})


def _describe_unsupported_streams(streams: list[dict]) -> list[str]:
    unsupported_types = sorted(
        {
            str(stream.get("codec_type") or "unknown").lower()
            for stream in streams
            if stream.get("codec_type") not in SUPPORTED_WEB_STREAM_TYPES
        }
    )
    descriptions: list[str] = []

    for stream_type in unsupported_types:
        codecs = ", ".join(_get_stream_codecs(streams, stream_type))
        descriptions.append(f"{stream_type} ({codecs})" if codecs else stream_type)

    return descriptions


def is_web_safe_webm(ffprobe_data: dict | None) -> bool:
    """Return True when ffprobe metadata describes a browser-safe WebM stream set."""
    streams = _get_ffprobe_streams(ffprobe_data)
    if not _has_only_supported_web_streams(streams):
        return False

    return _streams_have_allowed_codecs(streams, "video", WEBM_SAFE_VIDEO_CODECS, require_stream=True) and _streams_have_allowed_codecs(
        streams,
        "audio",
        WEBM_SAFE_AUDIO_CODECS,
        require_stream=False,
    )


def is_directly_embeddable_video(mimetype: str | None, ffprobe_data: dict | None) -> bool:
    """Return True when a video can be embedded directly without a generated preview."""
    if mimetype == "video/mp4":
        return True

    if mimetype == "video/webm":
        return is_web_safe_webm(ffprobe_data)

    return False


def get_mp4_remux_skip_reason(mimetype: str | None, ffprobe_data: dict | None) -> str | None:
    """Return a human-readable reason when copy-remuxing into MP4 should be skipped."""
    if mimetype == "video/mp4":
        return "it is already an MP4 file"

    streams = _get_ffprobe_streams(ffprobe_data)
    if not streams:
        return "ffprobe metadata did not contain any streams"

    if unsupported_streams := _describe_unsupported_streams(streams):
        return f"it contains unsupported non-audio/video streams: {', '.join(unsupported_streams)}"

    if mimetype == "video/webm" and is_web_safe_webm(ffprobe_data):
        return "it is already a browser-safe WebM file"

    if not _streams_have_allowed_codecs(streams, "video", MP4_SAFE_VIDEO_CODECS, require_stream=True):
        video_codecs = _get_stream_codecs(streams, "video")
        if not video_codecs:
            return "it does not contain an H.264 video stream"
        return f"its video codecs are not MP4 copy-remuxable: {', '.join(video_codecs)}"

    if not _streams_have_allowed_codecs(streams, "audio", MP4_SAFE_AUDIO_CODECS, require_stream=False):
        return f"its audio codecs are not MP4 copy-remuxable: {', '.join(_get_stream_codecs(streams, 'audio'))}"

    return None


def should_remux_to_mp4(mimetype: str | None, ffprobe_data: dict | None) -> bool:
    """Return True when a non-MP4 video can be safely copy-remuxed into MP4."""
    return get_mp4_remux_skip_reason(mimetype, ffprobe_data) is None


def mime_allowed(filetype: str | None, allowed: list[str] | None) -> bool:
    """
    Check if a given MIME type is allowed based on a list of allowed patterns.

    Args:
        filetype: The MIME type to check (e.g., 'video/mp4')
        allowed: List of allowed MIME patterns (e.g., ['application/pdf', 'video/*

    Returns:
        True if the MIME type is allowed, False otherwise

    """
    if not allowed or not filetype:
        return True

    for pattern in allowed:
        if pattern.endswith("/*"):
            prefix: str = pattern.split("/")[0]
            if filetype.startswith(prefix + "/"):
                return True

        elif filetype == pattern:
            return True

    return False


def parse_size(text: str) -> int:
    """
    Parse human-readable sizes: 100, 10M, 1G, 500k.

    Args:
        text (str): Size string to parse.

    Returns:
        int: Size in bytes as an integer.

    Raises:
        ValueError: If the size string is invalid.

    """
    s: str = text.strip().lower()
    if s[-1].isalpha():
        num = float(s[:-1])
        unit: str = s[-1]
        if unit not in MULTIPLIERS:
            msg = "Unknown size suffix; use K/M/G/T"
            raise ValueError(msg)

        return int(num * MULTIPLIERS[unit])

    return int(s)


def extract_video_metadata(ffprobe_data: dict | None) -> dict:
    """
    Extract video metadata (width, height, duration) from ffprobe JSON output.

    Args:
        ffprobe_data: ffprobe JSON output dictionary

    Returns:
        Dictionary with width, height, duration keys (values may be None)

    """
    result = {"width": None, "height": None, "duration": None}

    if not ffprobe_data:
        return result

    if duration_seconds := _get_media_duration_seconds(ffprobe_data):
        result["duration"] = int(duration_seconds)

    if "streams" in ffprobe_data:
        for stream in ffprobe_data["streams"]:
            if stream.get("codec_type") == "video":
                result["width"] = stream.get("width")
                result["height"] = stream.get("height")
                break

    return result


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in bytes to human-readable string.

    Args:
        size_bytes: File size in bytes

    Returns:
        Formatted string like "1.5 MB", "500 KB", etc.

    """
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to HH:MM:SS or MM:SS string.

    Args:
        seconds: Duration in seconds

    Returns:
        Formatted time string

    """
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{secs:02d}" if hours > 0 else f"{minutes:02d}:{secs:02d}"


async def _needs_faststart(path: str | Path, *, scan_bytes: int = 8 * 1024 * 1024) -> bool:
    """
    Check if an MP4 file needs 'faststart' (moov atom at the beginning).

    Args:
        path (str | Path): Path to the MP4 file to check
        scan_bytes (int): Number of bytes to scan for moov/mdat atoms

    Returns:
        bool: True if faststart is needed, False otherwise

    """
    p = Path(path)

    async with aiofiles.open(p, "rb") as f:
        data = await f.read(scan_bytes)

    moov = data.find(b"moov")
    mdat = data.find(b"mdat")

    if -1 == moov:
        return True

    if -1 == mdat:
        return False

    return moov > mdat


async def ensure_faststart_mp4(
    mp4_path: str | Path,
    mimetype: str,
    *,
    ffmpeg_bin: str = "ffmpeg",
    scan_bytes: int = 8 * 1024 * 1024,
) -> bool:
    """
    Ensure that an MP4 file has 'faststart' enabled (moov atom at the beginning).

    Args:
        mp4_path (str | Path): Path to the MP4 file to process
        mimetype (str): MIME type of the file
        ffmpeg_bin (str): Path to the ffmpeg binary
        scan_bytes (int): Number of bytes to scan for moov/mdat atoms

    Returns:
        bool: True if the file was modified to enable faststart, False otherwise

    Raises:
        FileNotFoundError: If the input file does not exist
        RuntimeError: If ffmpeg fails to process the file

    """
    src = Path(mp4_path)
    if not src.exists():
        raise FileNotFoundError(src)

    mime = mimetype.strip().lower()
    if mime not in ("video/mp4", "video/quicktime"):
        return False

    if not await _needs_faststart(src, scan_bytes=scan_bytes):
        return False

    tmp_dir = src.parent
    fd, tmp_out = tempfile.mkstemp(
        prefix=src.name + ".",
        suffix=".part",
        dir=tmp_dir,
    )
    os.close(fd)
    tmp_out_path = Path(tmp_out)

    proc: asyncio.subprocess.Process | None = None

    modified = False

    try:
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(tmp_out_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()

        if proc.returncode != 0:
            msg = (
                f"ffmpeg faststart failed (rc={proc.returncode}).\n"
                f"stdout:\n{out.decode(errors='replace')}\n"
                f"stderr:\n{err.decode(errors='replace')}"
            )
            raise RuntimeError(msg)

        if not tmp_out_path.exists() or tmp_out_path.stat().st_size == 0:
            msg = "ffmpeg produced an empty output file"
            raise RuntimeError(msg)

        tmp_out_path.replace(src)
        modified = True

    except asyncio.CancelledError:
        if proc is not None:
            await _terminate_subprocess(proc)
        raise

    finally:
        with contextlib.suppress(Exception):
            if tmp_out_path.exists():
                tmp_out_path.unlink()

    return modified


async def remux_to_mp4(
    source_path: str | Path,
    *,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    """Copy-remux a compatible media file into an MP4 container with faststart enabled."""
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(src)

    target_path = src.with_suffix(".mp4")
    fd, tmp_out = tempfile.mkstemp(
        prefix=target_path.name + ".",
        suffix=".part",
        dir=src.parent,
    )
    os.close(fd)
    tmp_out_path = Path(tmp_out)

    proc: asyncio.subprocess.Process | None = None
    remuxed_path = target_path

    try:
        cmd = [
            ffmpeg_bin,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-map",
            "0",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(tmp_out_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()

        if proc.returncode != 0:
            msg = (
                f"ffmpeg remux failed (rc={proc.returncode}).\n"
                f"stdout:\n{out.decode(errors='replace')}\n"
                f"stderr:\n{err.decode(errors='replace')}"
            )
            raise RuntimeError(msg)

        if not tmp_out_path.exists() or tmp_out_path.stat().st_size == 0:
            msg = "ffmpeg produced an empty remuxed output file"
            raise RuntimeError(msg)

        tmp_out_path.replace(target_path)
        if target_path != src:
            src.unlink(missing_ok=True)
        remuxed_path = target_path

    except asyncio.CancelledError:
        if proc is not None:
            await _terminate_subprocess(proc)
        raise

    finally:
        with contextlib.suppress(Exception):
            if tmp_out_path.exists():
                tmp_out_path.unlink()

    return remuxed_path
