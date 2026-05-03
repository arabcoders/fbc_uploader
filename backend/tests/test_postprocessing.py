"""Tests for post-processing worker."""

import asyncio
import logging
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.db import SessionLocal
from backend.app.postprocessing import ProcessingQueue, backfill_missing_video_thumbnails, process_upload
from backend.app.utils import get_preview_path, get_thumbnail_path
from backend.tests.utils import create_token, initiate_upload, upload_file_via_tus


async def wait_for_processing(upload_ids: list[str], timeout: float = 5.0) -> bool:
    """
    Wait for uploads to complete processing.

    Args:
        upload_ids: List of upload public IDs to wait for
        timeout: Maximum time to wait in seconds

    Returns:
        True if all uploads completed, False if timeout

    """
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < timeout:
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.public_id.in_(upload_ids))
            result = await session.execute(stmt)
            records = result.scalars().all()

            if all(r.status in ("completed", "failed") for r in records):
                return True

        await asyncio.sleep(0.1)

    return False


@pytest.mark.asyncio
async def test_multimedia_upload_enters_postprocessing(client):
    """Test that multimedia uploads enter postprocessing status."""
    token_data = await create_token(client, max_uploads=1)
    token_value = token_data["token"]

    video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
    video_content = video_file.read_bytes()

    upload_data = await initiate_upload(
        client, token_value, filename="test.mp4", size_bytes=len(video_content), filetype="video/mp4", meta_data={"title": "Test Video"}
    )
    upload_id = upload_data["upload_id"]

    await upload_file_via_tus(client, upload_id, video_content, token_value)

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
        result = await session.execute(stmt)
        record = result.scalar_one()

        assert record.status == "postprocessing", "Multimedia upload should enter postprocessing status"
        assert record.completed_at is None, "Upload should not be marked complete yet"
        assert record.meta_data["upload_checksums"]["file"]["algorithm"] == "sha256", (
            "Multimedia uploads should retain the digest of the uploaded bytes before post-processing"
        )
        assert isinstance(record.meta_data["upload_checksums"]["file"]["digest"], str), (
            "Multimedia uploads should store the uploaded file digest before post-processing"
        )


@pytest.mark.asyncio
async def test_non_multimedia_upload_completes_immediately(client):
    """Test that non-multimedia uploads complete immediately without post-processing."""
    token_data = await create_token(client, max_uploads=1)
    token_value = token_data["token"]

    pdf_content = b"%PDF-1.4 fake pdf content"
    upload_data = await initiate_upload(
        client, token_value, filename="document.pdf", size_bytes=len(pdf_content), meta_data={"title": "Test Doc"}
    )
    upload_id = upload_data["upload_id"]

    await upload_file_via_tus(client, upload_id, pdf_content, token_value)

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
        result = await session.execute(stmt)
        record = result.scalar_one()

        assert record.status == "completed", "Non-multimedia upload should complete immediately"
        assert record.completed_at is not None, "Upload should be marked complete"


@pytest.mark.asyncio
async def test_postprocessing_handles_missing_file():
    """Test that post-processing handles missing files gracefully."""
    async with SessionLocal() as session:
        expires_at = datetime.now(UTC) + timedelta(days=1)

        token = models.UploadToken(
            token="test_token_missing",
            download_token="test_download_missing",
            max_uploads=1,
            max_size_bytes=1000000,
            expires_at=expires_at,
        )
        session.add(token)
        await session.flush()

        record = models.UploadRecord(
            public_id="missing_file_test",
            token_id=token.id,
            filename="nonexistent.mp4",
            mimetype="video/mp4",
            status="postprocessing",
            storage_path="/tmp/nonexistent_file_12345.mp4",
        )
        session.add(record)
        await session.commit()

        success = await process_upload(record.public_id)
        assert success is False, "Processing should fail for missing file"

        await session.refresh(record)
        assert record.status == "failed", "Upload should be marked as failed"
        assert "error" in record.meta_data, "Error should be recorded in metadata"


@pytest.mark.asyncio
async def test_postprocessing_preserves_uploaded_checksum():
    """Test that post-processing does not overwrite the original upload digest."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_file:
        temp_file.write(b"not a real mp4 but enough for this test")
        temp_path = Path(temp_file.name)

    try:
        async with SessionLocal() as session:
            expires_at = datetime.now(UTC) + timedelta(days=1)

            token = models.UploadToken(
                token="test_token_checksum",
                download_token="test_download_checksum",
                max_uploads=1,
                max_size_bytes=1000000,
                expires_at=expires_at,
            )
            session.add(token)
            await session.flush()

            record = models.UploadRecord(
                public_id="postprocess_checksum_test",
                token_id=token.id,
                filename="sample.mp4",
                mimetype="video/mp4",
                status="postprocessing",
                storage_path=str(temp_path),
                meta_data={
                    "upload_checksums": {
                        "patch_algorithm": "sha256",
                        "file": {"algorithm": "sha256", "digest": "original-upload-digest"},
                    }
                },
            )
            session.add(record)
            await session.commit()

            success = await process_upload(record.public_id)

            assert success is True, "Processing should complete even when ffprobe cannot extract metadata"

            await session.refresh(record)
            assert record.status == "completed", "Upload should be marked complete after post-processing"
            assert record.meta_data["upload_checksums"]["file"]["digest"] == "original-upload-digest", (
                "Post-processing should preserve the digest of the uploaded bytes"
            )
    finally:
        temp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_postprocessing_remux_updates_media_metadata():
    """Remuxed uploads should update filename, ext, mimetype, size, and ffprobe metadata."""
    with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as temp_file:
        temp_file.write(b"fake mkv bytes")
        temp_path = Path(temp_file.name)

    remuxed_path = temp_path.with_suffix(".mp4")
    remuxed_path.write_bytes(b"remuxed mp4 bytes")
    remuxed_ffprobe = {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "1.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    try:
        async with SessionLocal() as session:
            expires_at = datetime.now(UTC) + timedelta(days=1)

            token = models.UploadToken(
                token="test_token_remux",
                download_token="test_download_remux",
                max_uploads=1,
                max_size_bytes=1000000,
                expires_at=expires_at,
            )
            session.add(token)
            await session.flush()

            record = models.UploadRecord(
                public_id="postprocess_remux_test",
                token_id=token.id,
                filename="sample.mkv",
                ext="mkv",
                mimetype="video/x-matroska",
                size_bytes=temp_path.stat().st_size,
                status="postprocessing",
                storage_path=str(temp_path),
                meta_data={
                    "upload_checksums": {
                        "patch_algorithm": "sha256",
                        "file": {"algorithm": "sha256", "digest": "original-upload-digest"},
                    }
                },
            )
            session.add(record)
            await session.commit()

            with (
                patch(
                    "backend.app.postprocessing.extract_ffprobe_metadata",
                    new=AsyncMock(
                        side_effect=[
                            {
                                "format": {"format_name": "matroska,webm", "duration": "1.0"},
                                "streams": [
                                    {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
                                    {"codec_type": "audio", "codec_name": "aac"},
                                ],
                            },
                            remuxed_ffprobe,
                        ]
                    ),
                ),
                patch("backend.app.postprocessing.remux_to_mp4", new=AsyncMock(return_value=remuxed_path)),
                patch(
                    "backend.app.postprocessing.detect_mimetype",
                    return_value="video/mp4",
                ),
                patch("backend.app.postprocessing.ensure_faststart_mp4", new=AsyncMock(return_value=False)),
            ):
                success = await process_upload(record.public_id)

            assert success is True, "Processing should succeed for a remuxable upload"

            await session.refresh(record)
            assert record.status == "completed", "Upload should be completed after post-processing"
            assert record.filename == "sample.mp4", "Filename should be updated to the remuxed extension"
            assert record.ext == "mp4", "Extension should reflect the remuxed file"
            assert record.mimetype == "video/mp4", "MIME type should reflect the remuxed MP4"
            assert record.storage_path == str(remuxed_path), "Storage path should point at the remuxed file"
            assert record.size_bytes == remuxed_path.stat().st_size, "Size should reflect the remuxed file"
            assert record.meta_data["ffprobe"] == remuxed_ffprobe, "ffprobe metadata should describe the final file"
            assert record.meta_data["upload_checksums"]["file"]["digest"] == "original-upload-digest", (
                "Remuxing should preserve the original upload digest"
            )
    finally:
        temp_path.unlink(missing_ok=True)
        remuxed_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_postprocessing_skips_remux_when_file_exceeds_limit():
    """Oversized remux candidates should skip copy-remux and keep original metadata."""
    with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as temp_file:
        temp_file.write(b"fake mkv bytes")
        temp_path = Path(temp_file.name)

    original_ffprobe = {
        "format": {"format_name": "matroska,webm", "duration": "1.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
    }

    try:
        async with SessionLocal() as session:
            expires_at = datetime.now(UTC) + timedelta(days=1)

            token = models.UploadToken(
                token="test_token_remux_limit",
                download_token="test_download_remux_limit",
                max_uploads=1,
                max_size_bytes=1000000,
                expires_at=expires_at,
            )
            session.add(token)
            await session.flush()

            record = models.UploadRecord(
                public_id="postprocess_remux_limit_test",
                token_id=token.id,
                filename="sample.mkv",
                ext="mkv",
                mimetype="video/x-matroska",
                size_bytes=temp_path.stat().st_size,
                status="postprocessing",
                storage_path=str(temp_path),
                meta_data={
                    "upload_checksums": {
                        "patch_algorithm": "sha256",
                        "file": {"algorithm": "sha256", "digest": "original-upload-digest"},
                    }
                },
            )
            session.add(record)
            await session.commit()

            with (
                patch("backend.app.postprocessing.extract_ffprobe_metadata", new=AsyncMock(return_value=original_ffprobe)),
                patch(
                    "backend.app.postprocessing.remux_to_mp4",
                    new=AsyncMock(side_effect=AssertionError("remux_to_mp4 should not be called")),
                ),
                patch("backend.app.postprocessing.ensure_faststart_mp4", new=AsyncMock(return_value=False)),
                patch(
                    "backend.app.postprocessing.settings.max_remux_bytes",
                    1,
                ),
            ):
                success = await process_upload(record.public_id)

            assert success is True, "Processing should still complete when remux is skipped"

            await session.refresh(record)
            assert record.status == "completed", "Upload should still complete after skipping remux"
            assert record.filename == "sample.mkv", "Filename should remain unchanged when remux is skipped"
            assert record.ext == "mkv", "Extension should remain unchanged when remux is skipped"
            assert record.mimetype == "video/x-matroska", "MIME type should remain unchanged when remux is skipped"
            assert record.storage_path == str(temp_path), "Storage path should remain on the original file when remux is skipped"
            assert record.meta_data["ffprobe"] == original_ffprobe, "ffprobe metadata should still be stored for the original file"
    finally:
        temp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_postprocessing_logs_reason_when_remux_is_rejected(caplog):
    """Non-remuxable video uploads should log why they were left unchanged."""
    with tempfile.NamedTemporaryFile(suffix=".mkv", delete=False) as temp_file:
        temp_file.write(b"fake mkv bytes")
        temp_path = Path(temp_file.name)

    ffprobe_with_subtitles = {
        "format": {"format_name": "matroska,webm", "duration": "1.0"},
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "subtitle", "codec_name": "ass"},
        ],
    }

    try:
        async with SessionLocal() as session:
            expires_at = datetime.now(UTC) + timedelta(days=1)

            token = models.UploadToken(
                token="test_token_remux_skip_reason",
                download_token="test_download_remux_skip_reason",
                max_uploads=1,
                max_size_bytes=1000000,
                expires_at=expires_at,
            )
            session.add(token)
            await session.flush()

            record = models.UploadRecord(
                public_id="postprocess_remux_skip_reason_test",
                token_id=token.id,
                filename="sample.mkv",
                ext="mkv",
                mimetype="video/x-matroska",
                size_bytes=temp_path.stat().st_size,
                status="postprocessing",
                storage_path=str(temp_path),
            )
            session.add(record)
            await session.commit()

            with (
                patch("backend.app.postprocessing.extract_ffprobe_metadata", new=AsyncMock(return_value=ffprobe_with_subtitles)),
                patch(
                    "backend.app.postprocessing.remux_to_mp4",
                    new=AsyncMock(side_effect=AssertionError("remux_to_mp4 should not be called")),
                ),
                caplog.at_level(logging.INFO, logger="backend.app.postprocessing"),
            ):
                success = await process_upload(record.public_id)

            assert success is True, "Processing should still complete when remux is rejected"

            await session.refresh(record)
            assert record.status == "completed", "Upload should complete even when remux is skipped"
            assert record.filename == "sample.mkv", "Filename should remain unchanged when remux is rejected"
            assert record.ext == "mkv", "Extension should remain unchanged when remux is rejected"
            assert record.meta_data["ffprobe"] == ffprobe_with_subtitles, "Original ffprobe metadata should still be stored"

            log_messages = [record.message for record in caplog.records if record.name == "backend.app.postprocessing"]
            assert any(
                "Skipping MP4 remux because it contains unsupported non-audio/video streams: subtitle (ass) [upload=postprocess_remux_skip_reason_test dir="
                in message
                for message in log_messages
            ), "Rejected remuxes should log the unsupported subtitle stream reason"
    finally:
        temp_path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_postprocessing_logs_directory_name_for_success_and_refusal(caplog):
    """Post-processing logs should include the upload directory name for successful operations and refusals."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        token_dir = Path(tmp_dir) / "token-dir-abc"
        token_dir.mkdir(parents=True, exist_ok=True)
        temp_path = token_dir / "sample.mkv"
        temp_path.write_bytes(b"fake mkv bytes")

        ffprobe_with_subtitles = {
            "format": {"format_name": "matroska,webm", "duration": "1.0"},
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1280, "height": 720},
                {"codec_type": "audio", "codec_name": "aac"},
                {"codec_type": "subtitle", "codec_name": "ass"},
            ],
        }

        async with SessionLocal() as session:
            expires_at = datetime.now(UTC) + timedelta(days=1)
            token = models.UploadToken(
                token="test_token_log_dir",
                download_token="test_download_log_dir",
                max_uploads=1,
                max_size_bytes=1000000,
                expires_at=expires_at,
            )
            session.add(token)
            await session.flush()

            record = models.UploadRecord(
                public_id="postprocess_log_dir_test",
                token_id=token.id,
                filename="sample.mkv",
                ext="mkv",
                mimetype="video/x-matroska",
                size_bytes=temp_path.stat().st_size,
                status="postprocessing",
                storage_path=str(temp_path),
            )
            session.add(record)
            await session.commit()

            with (
                patch("backend.app.postprocessing.extract_ffprobe_metadata", new=AsyncMock(return_value=ffprobe_with_subtitles)),
                patch("backend.app.postprocessing.ensure_video_thumbnail", new=AsyncMock(return_value=None)),
                patch("backend.app.postprocessing.ensure_video_preview", new=AsyncMock(return_value=None)),
                caplog.at_level(logging.INFO, logger="backend.app.postprocessing"),
            ):
                success = await process_upload(record.public_id)

            assert success is True, "Processing should still complete when remux is refused"

        log_messages = [record.message for record in caplog.records if record.name == "backend.app.postprocessing"]
        assert any(
            "Processing multimedia upload [upload=postprocess_log_dir_test dir=token-dir-abc]" in message for message in log_messages
        ), "Processing start logs should include the directory name"
        assert any(
            "Skipping MP4 remux because it contains unsupported non-audio/video streams: subtitle (ass) [upload=postprocess_log_dir_test dir=token-dir-abc]"
            in message
            for message in log_messages
        ), "Refusal logs should include the directory name"
        assert any(
            "Completed processing upload [upload=postprocess_log_dir_test dir=token-dir-abc]" in message for message in log_messages
        ), "Success logs should include the directory name"


@pytest.mark.asyncio
async def test_processing_queue_can_run_multiple_uploads_concurrently():
    """Worker pool should process more than one queued upload at the same time."""
    started_uploads: set[str] = set()
    both_started = asyncio.Event()
    release_processing = asyncio.Event()
    started_lock = asyncio.Lock()
    queue = ProcessingQueue(worker_count=2)

    async def fake_process_upload(upload_id: str) -> bool:
        async with started_lock:
            started_uploads.add(upload_id)
            if len(started_uploads) == 2:
                both_started.set()

        await release_processing.wait()
        return True

    with patch("backend.app.postprocessing.process_upload", new=AsyncMock(side_effect=fake_process_upload)):
        queue.start_worker()
        try:
            await queue.enqueue("big-upload")
            await queue.enqueue("small-upload")

            await asyncio.wait_for(both_started.wait(), timeout=1.0)
            assert started_uploads == {"big-upload", "small-upload"}, "Both uploads should start processing before either one finishes"

            release_processing.set()
            await asyncio.wait_for(queue.join(), timeout=1.0)
        finally:
            release_processing.set()
            await queue.stop_worker()


@pytest.mark.asyncio
async def test_backfill_missing_video_thumbnails_generates_missing_sidecars(tmp_path):
    """Startup sidecar backfill should skip expired videos and only process eligible missing sidecars."""
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"video-bytes")
    existing_path = tmp_path / "existing.mp4"
    existing_path.write_bytes(b"existing-video-bytes")
    existing_thumbnail = get_thumbnail_path(existing_path)
    existing_thumbnail.write_bytes(b"thumb")
    existing_preview = get_preview_path(existing_path)
    existing_preview.write_bytes(b"preview")
    expired_path = tmp_path / "expired.mp4"
    expired_path.write_bytes(b"expired-video-bytes")
    text_path = tmp_path / "doc.txt"
    text_path.write_text("hello")

    async with SessionLocal() as session:
        active_expires_at = datetime.now(UTC) + timedelta(days=1)
        expired_expires_at = datetime.now(UTC) - timedelta(days=1)
        token = models.UploadToken(
            token="backfill-token",
            download_token="backfill-download",
            max_uploads=3,
            max_size_bytes=1000000,
            expires_at=active_expires_at,
        )
        expired_token = models.UploadToken(
            token="expired-backfill-token",
            download_token="expired-backfill-download",
            max_uploads=1,
            max_size_bytes=1000000,
            expires_at=expired_expires_at,
        )
        session.add(token)
        session.add(expired_token)
        await session.flush()

        session.add_all(
            [
                models.UploadRecord(
                    public_id="needs-thumb",
                    token_id=token.id,
                    filename="video.mp4",
                    mimetype="video/mp4",
                    status="completed",
                    storage_path=str(video_path),
                    meta_data={"ffprobe": {"format": {"duration": "600.0"}}},
                ),
                models.UploadRecord(
                    public_id="has-thumb",
                    token_id=token.id,
                    filename="existing.mp4",
                    mimetype="video/mp4",
                    status="completed",
                    storage_path=str(existing_path),
                    meta_data={"ffprobe": {"format": {"duration": "600.0"}}},
                ),
                models.UploadRecord(
                    public_id="expired-video",
                    token_id=expired_token.id,
                    filename="expired.mp4",
                    mimetype="video/mp4",
                    status="completed",
                    storage_path=str(expired_path),
                    meta_data={"ffprobe": {"format": {"duration": "600.0"}}},
                ),
                models.UploadRecord(
                    public_id="not-video",
                    token_id=token.id,
                    filename="doc.txt",
                    mimetype="text/plain",
                    status="completed",
                    storage_path=str(text_path),
                ),
            ]
        )
        await session.commit()

    generated_thumbnail = get_thumbnail_path(video_path)
    generated_preview = get_preview_path(video_path)
    with (
        patch("backend.app.postprocessing.settings.embed_preview_clip_seconds", 10),
        patch("backend.app.postprocessing.settings.embed_preview_min_size_bytes", 195 * 1024 * 1024),
        patch("backend.app.postprocessing.ensure_video_thumbnail", new=AsyncMock(return_value=generated_thumbnail)) as ensure_thumb,
        patch("backend.app.postprocessing.ensure_video_preview", new=AsyncMock(return_value=generated_preview)) as ensure_preview,
    ):
        generated_count = await backfill_missing_video_thumbnails()

    assert generated_count == 1, "Backfill should only generate sidecars for eligible completed videos"
    ensure_thumb.assert_awaited_once_with(video_path)
    ensure_preview.assert_awaited_once_with(
        video_path,
        ffprobe_data={"format": {"duration": "600.0"}},
        clip_seconds=10,
        min_size_bytes=195 * 1024 * 1024,
    )
