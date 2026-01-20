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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from . import models
from .db import SessionLocal
from .utils import ensure_faststart_mp4, extract_ffprobe_metadata, is_multimedia

logger = logging.getLogger(__name__)


class ProcessingQueue:
    """Background processing queue for uploads."""

    def __init__(self) -> None:
        """Initialize the processing queue."""
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def enqueue(self, upload_id: str) -> None:
        """Add an upload to the processing queue."""
        await self._queue.put(upload_id)
        logger.info("Enqueued upload %s for post-processing", upload_id)

    def start_worker(self) -> None:
        """Start the background worker if not already running."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._run_worker(), name="postprocessing_worker")
            logger.info("Started post-processing worker")

    async def stop_worker(self) -> None:
        """Stop the background worker."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker_task
            logger.info("Stopped post-processing worker")

    async def _run_worker(self) -> None:
        """Background worker that processes uploads from the queue."""
        logger.info("Post-processing worker started")

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
                logger.info("Post-processing worker cancelled")
                break
            except Exception:
                logger.exception("Error in post-processing worker loop")
                await asyncio.sleep(1)

    async def _process_upload_by_id(self, upload_id: str) -> None:
        """Process a single upload by ID."""
        async with SessionLocal() as session:
            try:
                stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
                result = await session.execute(stmt)
                record = result.scalar_one_or_none()

                if record is None:
                    logger.warning("Upload %s not found for processing", upload_id)
                    return

                await process_upload(session, record)
            finally:
                await session.close()


async def process_upload(session: AsyncSession, record: models.UploadRecord) -> bool:
    """
    Process a single upload record.

    Args:
        session: Database session
        record: Upload record to process

    Returns:
        True if processing succeeded, False otherwise

    """
    if not record.storage_path:
        logger.error("Upload %s has no storage path", record.public_id)
        record.status = "failed"
        record.meta_data["error"] = "No storage path"
        attributes.flag_modified(record, "meta_data")
        await session.commit()
        return False

    path = Path(record.storage_path)
    if not path.exists():
        logger.error("Upload %s file not found: %s", record.public_id, path)
        record.status = "failed"
        record.meta_data["error"] = "File not found"
        attributes.flag_modified(record, "meta_data")
        await session.commit()
        return False

    try:
        if record.mimetype and is_multimedia(record.mimetype):
            logger.info("Processing multimedia upload %s", record.public_id)

            try:
                modified = await ensure_faststart_mp4(path, record.mimetype)
                if modified:
                    logger.info("Applied faststart to upload %s", record.public_id)
            except Exception:
                logger.exception("Failed to apply faststart to upload %s", record.public_id)

            ffprobe_data = await extract_ffprobe_metadata(path)
            if ffprobe_data is not None:
                if record.meta_data is None:
                    record.meta_data = {}

                record.meta_data["ffprobe"] = ffprobe_data
                attributes.flag_modified(record, "meta_data")
                logger.info("Extracted ffprobe metadata for upload %s", record.public_id)

        record.status = "completed"
        record.completed_at = datetime.now(UTC)
        await session.commit()
        logger.info("Completed processing upload %s", record.public_id)

    except Exception:
        logger.exception("Failed to process upload %s", record.public_id)
        record.status = "failed"
        if record.meta_data is None:
            record.meta_data = {}
        record.meta_data["error"] = "Post-processing failed"
        attributes.flag_modified(record, "meta_data")
        await session.commit()
        return False
    else:
        return True
