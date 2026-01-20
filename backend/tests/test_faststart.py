"""Tests for MP4 faststart post-processing."""

import tempfile
from pathlib import Path

import pytest

from backend.app.utils import _needs_faststart, ensure_faststart_mp4


@pytest.mark.asyncio
async def test_not_mp4_returns_false():
    """Test that non-MP4 files return False without processing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("not a video file")
        f.flush()
        path = Path(f.name)

    try:
        modified = await ensure_faststart_mp4(path, "text/plain")
        assert modified is False, "Non-MP4 file should not be modified"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_needs_faststart_non_mp4():
    """Test faststart check on non-MP4 file doesn't crash."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".bin", delete=False) as f:
        f.write(b"some random binary data" * 1000)
        f.flush()
        path = Path(f.name)

    try:
        result = await _needs_faststart(path)
        assert isinstance(result, bool), "Function should return a boolean"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_needs_faststart_empty_file():
    """Test faststart check on empty file."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as f:
        path = Path(f.name)

    try:
        result = await _needs_faststart(path)
        assert result is True, "Empty file should need faststart (moov not found)"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_needs_faststart_moov_before_mdat():
    """Test that file with moov before mdat doesn't need faststart."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as f:
        f.write(b"ftyp" + b"\x00" * 100)
        f.write(b"moov" + b"\x00" * 1000)
        f.write(b"mdat" + b"\x00" * 5000)
        f.flush()
        path = Path(f.name)

    try:
        result = await _needs_faststart(path)
        assert result is False, "File with moov before mdat should not need faststart"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_needs_faststart_mdat_before_moov():
    """Test that file with mdat before moov needs faststart."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as f:
        f.write(b"ftyp" + b"\x00" * 100)
        f.write(b"mdat" + b"\x00" * 5000)
        f.write(b"moov" + b"\x00" * 1000)
        f.flush()
        path = Path(f.name)

    try:
        result = await _needs_faststart(path)
        assert result is True, "File with mdat before moov should need faststart"
    finally:
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_ensure_faststart_file_not_found():
    """Test that missing file raises FileNotFoundError."""
    nonexistent = Path("/tmp/does_not_exist_12345.mp4")
    with pytest.raises(FileNotFoundError):
        await ensure_faststart_mp4(nonexistent, "video/mp4")
