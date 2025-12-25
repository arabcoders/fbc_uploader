"""Utility functions for file handling and validation."""

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
