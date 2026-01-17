"""Utility functions for file handling and validation."""

import asyncio
import contextlib
import json
from pathlib import Path

import magic

MIME = magic.Magic(mime=True)

MULTIPLIERS: dict[str, int] = {
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3,
    "t": 1024**4,
}


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
    except Exception:
        return None
    else:
        return dct


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

    if "format" in ffprobe_data and "duration" in ffprobe_data["format"]:
        with contextlib.suppress(ValueError, TypeError):
            result["duration"] = int(float(ffprobe_data["format"]["duration"]))

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
