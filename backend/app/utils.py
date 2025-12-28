"""Utility functions for file handling and validation."""

import asyncio
import json
from pathlib import Path

import magic


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
    path = Path(file_path)
    if not path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    mime = magic.Magic(mime=True)
    return mime.from_file(str(path))


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
        file_path: Path to the multimedia file

    Returns:
        Dictionary containing ffprobe output in JSON format, or None if extraction fails

    Raises:
        FileNotFoundError: If the file does not exist

    """
    path = Path(file_path)
    if not path.exists():
        msg = f"File not found: {file_path}"
        raise FileNotFoundError(msg)

    try:
        # Run ffprobe to extract metadata in JSON format
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
            # ffprobe failed, return None
            return None

        # Parse and return JSON output
        return json.loads(stdout.decode())
    except FileNotFoundError:
        # ffprobe not installed
        return None
    except json.JSONDecodeError:
        # Invalid JSON output
        return None
    except Exception:
        # Any other error
        return None
