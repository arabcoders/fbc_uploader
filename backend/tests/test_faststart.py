"""Tests for MP4 faststart post-processing."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.utils import (
    _needs_faststart,
    ensure_faststart_mp4,
    generate_video_preview,
    generate_video_thumbnail,
    get_thumbnail_path,
    is_directly_embeddable_video,
    is_web_safe_webm,
    should_generate_video_preview,
    should_remux_to_mp4,
)


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


@pytest.mark.asyncio
async def test_generate_video_thumbnail_uses_seeked_sampling_and_retries_without_seek():
    """Thumbnail generation should skip intros first, then fall back to a no-seek attempt if needed."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mp4", delete=False) as f:
        f.write(b"fake video bytes")
        f.flush()
        path = Path(f.name)

    commands: list[tuple[str, ...]] = []

    class DummyProcess:
        def __init__(self, output_path: Path, *, returncode: int, stderr: bytes = b"") -> None:
            self.returncode = returncode
            self._output_path = output_path
            self._stderr = stderr

        async def communicate(self) -> tuple[bytes, bytes]:
            if self.returncode == 0:
                self._output_path.write_bytes(b"jpeg-bytes")
            return b"", self._stderr

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        commands.append(tuple(str(arg) for arg in args))
        output_path = Path(args[-1])
        if 1 == len(commands):
            return DummyProcess(output_path, returncode=1, stderr=b"seek failed")
        return DummyProcess(output_path, returncode=0)

    try:
        create_subprocess_exec = AsyncMock(side_effect=fake_create_subprocess_exec)
        with (
            patch("backend.app.utils.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("backend.app.utils.extract_ffprobe_metadata", new=AsyncMock(return_value={"format": {"duration": "120.0"}})),
            patch("backend.app.utils.asyncio.create_subprocess_exec", new=create_subprocess_exec),
        ):
            thumbnail_path = await generate_video_thumbnail(path)

        assert thumbnail_path == get_thumbnail_path(path), "Generated thumbnail should use the deterministic sidecar path"
        assert thumbnail_path is not None and thumbnail_path.exists(), "Successful retry should leave a thumbnail sidecar on disk"
        assert len(commands) == 2, "Generator should retry without a seek offset after a failed seeked attempt"

        first_command = commands[0]
        assert "-ss" in first_command, "First attempt should seek past the intro before sampling frames"
        first_seek_index = first_command.index("-ss")
        assert first_command[first_seek_index + 1] == "12.000", "Seek offset should use about 10% of duration for longer videos"
        first_filter_index = first_command.index("-vf")
        assert first_command[first_filter_index + 1] == "thumbnail=200,scale=1280:-1:force_original_aspect_ratio=decrease", (
            "Thumbnail selection should sample a larger frame window"
        )

        second_command = commands[1]
        assert "-ss" not in second_command, "Fallback attempt should retry without seeking when the first seeked pass fails"
        second_filter_index = second_command.index("-vf")
        assert second_command[second_filter_index + 1] == "thumbnail=200,scale=1280:-1:force_original_aspect_ratio=decrease", (
            "Fallback attempt should keep the wider thumbnail sampling window"
        )
    finally:
        get_thumbnail_path(path).unlink(missing_ok=True)
        path.unlink(missing_ok=True)


def test_should_remux_mkv_with_h264_aac_to_mp4():
    """H.264/AAC in a non-MP4 container should be remuxed to MP4."""
    ffprobe_data = {
        "format": {"format_name": "matroska,webm"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    assert should_remux_to_mp4("video/x-matroska", ffprobe_data) is True, "MKV with H.264/AAC should be remuxed"


def test_should_not_remux_web_safe_webm():
    """Browser-safe WebM should stay in WebM instead of being remuxed."""
    ffprobe_data = {
        "format": {"format_name": "matroska,webm"},
        "streams": [
            {"codec_type": "video", "codec_name": "vp9"},
            {"codec_type": "audio", "codec_name": "opus"},
        ],
    }

    assert is_web_safe_webm(ffprobe_data) is True, "VP9/Opus WebM should be treated as web safe"
    assert should_remux_to_mp4("video/webm", ffprobe_data) is False, "Web-safe WebM should not be remuxed"


def test_should_not_remux_streams_with_non_web_tracks():
    """Files with subtitle or data streams should be left unchanged in v1."""
    ffprobe_data = {
        "format": {"format_name": "matroska,webm"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264"},
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "subtitle", "codec_name": "subrip"},
        ],
    }

    assert should_remux_to_mp4("video/x-matroska", ffprobe_data) is False, "Subtitle streams should prevent copy-remux to MP4"


def test_should_generate_video_preview_uses_file_size_threshold():
    """Preview generation should be gated by source file size, not media duration."""
    min_size_bytes = 195 * 1024 * 1024

    assert should_generate_video_preview(min_size_bytes - 1, min_size_bytes=min_size_bytes) is False, (
        "Files smaller than the configured size threshold should not get bot preview sidecars"
    )
    assert should_generate_video_preview(min_size_bytes, min_size_bytes=min_size_bytes) is True, (
        "Files at the configured size threshold should get bot preview sidecars"
    )


def test_should_generate_video_preview_can_be_disabled_with_zero_threshold():
    """A zero size threshold should disable generated bot preview clips."""
    assert should_generate_video_preview(195 * 1024 * 1024, min_size_bytes=0) is False, (
        "Zero preview size threshold should disable preview generation entirely"
    )


def test_is_directly_embeddable_video_accepts_mp4_and_web_safe_webm():
    """Embed helper should treat MP4 and browser-safe WebM as directly embeddable."""
    webm_ffprobe = {
        "format": {"format_name": "matroska,webm"},
        "streams": [
            {"codec_type": "video", "codec_name": "vp9"},
            {"codec_type": "audio", "codec_name": "opus"},
        ],
    }

    assert is_directly_embeddable_video("video/mp4", None) is True, "MP4 should embed directly"
    assert is_directly_embeddable_video("video/webm", webm_ffprobe) is True, "Browser-safe WebM should embed directly"
    assert is_directly_embeddable_video("video/x-matroska", webm_ffprobe) is False, "Other containers should not embed directly"


@pytest.mark.asyncio
async def test_generate_video_preview_can_bypass_size_threshold_for_incompatible_video():
    """Forced previews should bypass only the size threshold, not the rest of preview generation."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mkv", delete=False) as f:
        f.write(b"fake video bytes")
        f.flush()
        path = Path(f.name)

    class DummyProcess:
        def __init__(self, output_path: Path) -> None:
            self.returncode = 0
            self._output_path = output_path

        async def communicate(self) -> tuple[bytes, bytes]:
            self._output_path.write_bytes(b"preview-bytes")
            return b"", b""

    try:
        create_subprocess_exec = AsyncMock(side_effect=lambda *args, **kwargs: DummyProcess(Path(args[-1])))
        with (
            patch("backend.app.utils.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("backend.app.utils.extract_ffprobe_metadata", new=AsyncMock(return_value={"format": {"duration": "120.0"}})),
            patch("backend.app.utils.asyncio.create_subprocess_exec", new=create_subprocess_exec),
        ):
            preview_path = await generate_video_preview(
                path,
                min_size_bytes=10_000_000,
                ignore_size_threshold=True,
            )

        assert preview_path == path.with_name(f"{path.name}.preview.mp4"), "Forced preview should still use the normal sidecar path"
        assert preview_path is not None and preview_path.exists(), (
            "Forced preview should generate a sidecar below the normal size threshold"
        )
    finally:
        path.with_name(f"{path.name}.preview.mp4").unlink(missing_ok=True)
        path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_generate_video_preview_uses_even_dimension_scale_filter():
    """Preview generation should force even output dimensions for x264 compatibility."""
    with tempfile.NamedTemporaryFile(mode="wb", suffix=".mkv", delete=False) as f:
        f.write(b"fake video bytes")
        f.flush()
        path = Path(f.name)

    commands: list[tuple[str, ...]] = []

    class DummyProcess:
        def __init__(self, output_path: Path) -> None:
            self.returncode = 0
            self._output_path = output_path

        async def communicate(self) -> tuple[bytes, bytes]:
            self._output_path.write_bytes(b"preview-bytes")
            return b"", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        del kwargs
        commands.append(tuple(str(arg) for arg in args))
        return DummyProcess(Path(args[-1]))

    try:
        create_subprocess_exec = AsyncMock(side_effect=fake_create_subprocess_exec)
        with (
            patch("backend.app.utils.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch("backend.app.utils.extract_ffprobe_metadata", new=AsyncMock(return_value={"format": {"duration": "120.0"}})),
            patch("backend.app.utils.asyncio.create_subprocess_exec", new=create_subprocess_exec),
        ):
            preview_path = await generate_video_preview(
                path,
                min_size_bytes=1,
            )

        assert preview_path is not None and preview_path.exists(), "Preview generation should succeed with the even-dimension scale filter"
        assert len(commands) == 1, "Preview generation should only need one ffmpeg invocation on success"

        command = commands[0]
        filter_index = command.index("-vf")
        assert command[filter_index + 1] == (
            "scale='trunc(min(1280,iw*min(1280/iw,720/ih))/2)*2':'trunc(min(720,ih*min(1280/iw,720/ih))/2)*2'"
        ), "Preview generation should force even output dimensions after aspect-ratio-constrained scaling"
    finally:
        path.with_name(f"{path.name}.preview.mp4").unlink(missing_ok=True)
        path.unlink(missing_ok=True)
