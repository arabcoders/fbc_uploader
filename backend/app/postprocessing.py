"""
Post-processing worker for uploaded files.

Handles background tasks like:
- MP4 faststart optimization
- FFprobe metadata extraction
- Future: thumbnail generation, video transcoding, etc.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from . import models
from .config import settings
from .db import SessionLocal
from .utils import (
    detect_mimetype,
    ensure_faststart_mp4,
    ensure_video_preview,
    ensure_video_thumbnail,
    extract_ffprobe_metadata,
    get_mp4_remux_skip_reason,
    is_multimedia,
    preview_exists,
    remux_to_mp4,
    should_remux_to_mp4,
    thumbnail_exists,
)

logger = logging.getLogger(__name__)


def _build_remuxed_filename(filename: str | None) -> str | None:
    if not filename:
        return None

    path = Path(filename)
    return f"{path.stem}.mp4" if path.suffix else f"{filename}.mp4"


def _token_has_expired(expires_at: datetime) -> bool:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    return expires_at < datetime.now(UTC)


async def _apply_media_normalization(record: models.UploadRecord, path: Path) -> tuple[Path, dict | None]:
    ffprobe_data = await extract_ffprobe_metadata(path)

    if should_remux_to_mp4(record.mimetype, ffprobe_data):
        source_size = path.stat().st_size
        if source_size > settings.max_remux_bytes:
            logger.info(
                "Skipping remux for upload %s because %s bytes exceeds remux limit %s",
                record.public_id,
                source_size,
                settings.max_remux_bytes,
            )
        else:
            logger.info("Remuxing upload %s into MP4 container", record.public_id)
            path = await remux_to_mp4(path)
            record.storage_path = str(path)
            record.filename = _build_remuxed_filename(record.filename)
            record.ext = "mp4"
            record.mimetype = detect_mimetype(path)
            record.size_bytes = path.stat().st_size
            ffprobe_data = await extract_ffprobe_metadata(path)
    elif record.mimetype and record.mimetype.startswith("video/") and record.mimetype != "video/mp4":
        logger.info(
            "Skipping MP4 remux for upload %s because %s",
            record.public_id,
            get_mp4_remux_skip_reason(record.mimetype, ffprobe_data),
        )

    if record.mimetype == "video/mp4":
        try:
            modified = await ensure_faststart_mp4(path, record.mimetype)
            if modified:
                logger.info("Applied faststart to upload %s", record.public_id)
        except Exception:
            logger.exception("Failed to apply faststart to upload %s", record.public_id)

    await _ensure_thumbnail(record, path)
    await _ensure_preview(record, path, ffprobe_data)

    return path, ffprobe_data


async def _get_upload_record(session: AsyncSession, upload_id: str) -> models.UploadRecord | None:
    stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


def _build_processing_state(record: models.UploadRecord) -> SimpleNamespace:
    return SimpleNamespace(
        public_id=record.public_id,
        storage_path=record.storage_path,
        filename=record.filename,
        ext=record.ext,
        mimetype=record.mimetype,
        size_bytes=record.size_bytes,
    )


async def _ensure_thumbnail(record: models.UploadRecord | SimpleNamespace, path: Path) -> None:
    mimetype = getattr(record, "mimetype", None)
    if not mimetype or not mimetype.startswith("video/"):
        return

    try:
        thumbnail_path = await ensure_video_thumbnail(path)
    except Exception:
        logger.exception("Failed to generate thumbnail for upload %s", record.public_id)
        return

    if thumbnail_path is not None:
        logger.info("Thumbnail ready for upload %s", record.public_id)


async def _ensure_preview(record: models.UploadRecord | SimpleNamespace, path: Path, ffprobe_data: dict | None) -> None:
    mimetype = getattr(record, "mimetype", None)
    if not mimetype or not mimetype.startswith("video/"):
        return

    try:
        preview_path = await ensure_video_preview(
            path,
            ffprobe_data=ffprobe_data,
            clip_seconds=settings.embed_preview_clip_seconds,
            min_size_bytes=settings.embed_preview_min_size_bytes,
        )
    except Exception:
        logger.exception("Failed to generate embed preview for upload %s", record.public_id)
        return

    if preview_path is not None:
        logger.info("Embed preview ready for upload %s", record.public_id)


async def _mark_upload_failed(upload_id: str, error_message: str) -> bool:
    async with SessionLocal() as session:
        if not (record := await _get_upload_record(session, upload_id)):
            logger.warning("Upload %s not found for processing", upload_id)
            return False

        record.status = "failed"
        if record.meta_data is None:
            record.meta_data = {}
        record.meta_data["error"] = error_message
        attributes.flag_modified(record, "meta_data")
        await session.commit()
        return False


async def _mark_upload_completed(upload_id: str, processing_state: SimpleNamespace, path: Path, ffprobe_data: dict | None) -> bool:
    async with SessionLocal() as session:
        if not (record := await _get_upload_record(session, upload_id)):
            logger.warning("Upload %s not found for processing", upload_id)
            return False

        record.storage_path = processing_state.storage_path
        record.filename = processing_state.filename
        record.ext = processing_state.ext
        record.mimetype = processing_state.mimetype
        record.size_bytes = processing_state.size_bytes if processing_state.size_bytes is not None else path.stat().st_size

        if ffprobe_data is not None:
            if record.meta_data is None:
                record.meta_data = {}

            record.meta_data["ffprobe"] = ffprobe_data
            attributes.flag_modified(record, "meta_data")
            logger.info("Extracted ffprobe metadata for upload %s", upload_id)

        record.status = "completed"
        record.completed_at = datetime.now(UTC)
        await session.commit()
        logger.info("Completed processing upload %s", upload_id)
        return True


class ProcessingQueue:
    """Background processing queue for uploads."""

    def __init__(self, worker_count: int | None = None) -> None:
        """Initialize the processing queue."""
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_count = settings.postprocessing_workers if worker_count is None else worker_count
        if self._worker_count < 1:
            msg = "worker_count must be at least 1"
            raise ValueError(msg)

        self._worker_tasks: list[asyncio.Task[None]] = []

    async def enqueue(self, upload_id: str) -> None:
        """Add an upload to the processing queue."""
        await self._queue.put(upload_id)
        logger.info("Enqueued upload %s for post-processing", upload_id)

    def start_worker(self) -> None:
        """Start the background worker pool if not already running."""
        self._worker_tasks = [task for task in self._worker_tasks if not task.done()]

        while len(self._worker_tasks) < self._worker_count:
            worker_index = len(self._worker_tasks) + 1
            task = asyncio.create_task(self._run_worker(worker_index), name=f"postprocessing_worker_{worker_index}")
            self._worker_tasks.append(task)

        logger.info("Started %s post-processing worker(s)", len(self._worker_tasks))

    async def stop_worker(self) -> None:
        """Stop the background worker pool."""
        worker_tasks = [task for task in self._worker_tasks if not task.done()]
        if not worker_tasks:
            self._worker_tasks = []
            return

        for task in worker_tasks:
            task.cancel()

        for task in worker_tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

        self._worker_tasks = []
        logger.info("Stopped %s post-processing worker(s)", len(worker_tasks))

    async def join(self) -> None:
        """Wait until all queued uploads have been processed."""
        await self._queue.join()

    async def _run_worker(self, worker_index: int) -> None:
        """Background worker that processes uploads from the queue."""
        logger.info("Post-processing worker %s started", worker_index)

        while True:
            try:
                upload_id = await self._queue.get()
                try:
                    await self._process_upload_by_id(upload_id)
                except Exception:
                    logger.exception("Failed to process upload %s", upload_id)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                logger.info("Post-processing worker %s cancelled", worker_index)
                break
            except Exception:
                logger.exception("Error in post-processing worker loop")
                await asyncio.sleep(1)

    async def _process_upload_by_id(self, upload_id: str) -> None:
        """Process a single upload by ID."""
        await process_upload(upload_id)


async def process_upload(upload_id: str) -> bool:
    """
    Process a single upload record.

    Args:
        upload_id: Upload public ID to process

    Returns:
        True if processing succeeded, False otherwise

    """
    async with SessionLocal() as session:
        if not (record := await _get_upload_record(session, upload_id)):
            logger.warning("Upload %s not found for processing", upload_id)
            return False

        processing_state = _build_processing_state(record)

    if not processing_state.storage_path:
        logger.error("Upload %s has no storage path", upload_id)
        return await _mark_upload_failed(upload_id, "No storage path")

    path = Path(processing_state.storage_path)
    if not path.exists():
        logger.error("Upload %s file not found: %s", upload_id, path)
        return await _mark_upload_failed(upload_id, "File not found")

    try:
        ffprobe_data = None
        if processing_state.mimetype and is_multimedia(processing_state.mimetype):
            logger.info("Processing multimedia upload %s", upload_id)
            path, ffprobe_data = await _apply_media_normalization(processing_state, path)

        if processing_state.size_bytes is None and path.exists():
            processing_state.size_bytes = path.stat().st_size

    except Exception:
        logger.exception("Failed to process upload %s", upload_id)
        return await _mark_upload_failed(upload_id, "Post-processing failed")

    return await _mark_upload_completed(upload_id, processing_state, path, ffprobe_data)


async def backfill_missing_video_thumbnails() -> int:
    """Generate thumbnails and embed previews for completed video uploads missing sidecars."""
    async with SessionLocal() as session:
        stmt = (
            select(models.UploadRecord, models.UploadToken.expires_at)
            .join(models.UploadToken, models.UploadToken.id == models.UploadRecord.token_id)
            .where(models.UploadRecord.status == "completed")
        )
        result = await session.execute(stmt)
        upload_targets = [
            (record.public_id, not thumbnail_exists(record.storage_path), not preview_exists(record.storage_path))
            for record, expires_at in result.all()
            if record.storage_path
            and record.mimetype
            and record.mimetype.startswith("video/")
            and not _token_has_expired(expires_at)
            and (not thumbnail_exists(record.storage_path) or not preview_exists(record.storage_path))
        ]

    updated_count = 0
    for upload_id, needs_thumbnail, needs_preview in upload_targets:
        async with SessionLocal() as session:
            stmt = (
                select(models.UploadRecord, models.UploadToken.expires_at)
                .join(models.UploadToken, models.UploadToken.id == models.UploadRecord.token_id)
                .where(models.UploadRecord.public_id == upload_id)
            )
            result = await session.execute(stmt)
            row = result.one_or_none()
            if row is None:
                continue

            record, expires_at = row
            if _token_has_expired(expires_at):
                continue

            if not record.storage_path or not record.mimetype or not record.mimetype.startswith("video/"):
                continue

            path = Path(record.storage_path)
            ffprobe_data = record.meta_data.get("ffprobe") if isinstance(record.meta_data, dict) else None

        if not path.exists():
            logger.warning("Skipping sidecar backfill for upload %s because file is missing", upload_id)
            continue

        generated_any = False
        if needs_thumbnail:
            try:
                thumbnail_path = await ensure_video_thumbnail(path)
            except Exception:
                logger.exception("Failed to backfill thumbnail for upload %s", upload_id)
            else:
                if thumbnail_path is not None:
                    generated_any = True

        if needs_preview:
            try:
                preview_path = await ensure_video_preview(
                    path,
                    ffprobe_data=ffprobe_data,
                    clip_seconds=settings.embed_preview_clip_seconds,
                    min_size_bytes=settings.embed_preview_min_size_bytes,
                )
            except Exception:
                logger.exception("Failed to backfill embed preview for upload %s", upload_id)
            else:
                if preview_path is not None:
                    generated_any = True

        if generated_any:
            updated_count += 1

    if updated_count > 0:
        logger.info("Backfilled media sidecars for %s upload(s)", updated_count)

    return updated_count
