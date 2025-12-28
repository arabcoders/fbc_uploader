import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import config, models
from .db import SessionLocal

logger: logging.Logger = logging.getLogger(__name__)


async def _cleanup_once() -> None:
    async with SessionLocal() as session:
        await _disable_expired_tokens(session)
        if config.settings.incomplete_ttl_hours > 0:
            await _remove_stale_uploads(session)
        if config.settings.disabled_tokens_ttl_days > 0:
            await _remove_disabled_tokens(session)


async def _disable_expired_tokens(session: AsyncSession) -> None:
    now = datetime.now(UTC)
    stmt = (
        update(models.UploadToken)
        .where(models.UploadToken.expires_at < now)
        .where(models.UploadToken.disabled.is_(False))
        .values(disabled=True)
    )
    res = await session.execute(stmt)
    if res.rowcount:
        logger.info("Disabled %d expired tokens", res.rowcount)
    await session.commit()


async def _remove_stale_uploads(session: AsyncSession) -> None:
    """Remove stale uploads in batches to avoid loading millions of records into memory."""
    cutoff = datetime.now(UTC) - timedelta(hours=config.settings.incomplete_ttl_hours)
    cutoff_naive = cutoff.replace(tzinfo=None)

    total_removed = 0
    batch_size = 100

    while True:
        stmt = (
            select(models.UploadRecord)
            .where(models.UploadRecord.status != "completed")
            .where(models.UploadRecord.created_at < cutoff_naive)
            .limit(batch_size)
        )
        res = await session.execute(stmt)
        batch = res.scalars().all()

        if not batch:
            break

        for record in batch:
            if record.storage_path:
                path = Path(record.storage_path)
                if path.exists():
                    try:
                        path.unlink()
                    except OSError:
                        logger.warning("Failed to remove stale upload file: %s", path)
            await session.delete(record)

        await session.flush()
        await session.commit()
        total_removed += len(batch)

        if len(batch) < batch_size:
            break

    if total_removed > 0:
        logger.info("Removed %d stale uploads", total_removed)


async def _remove_disabled_tokens(session: AsyncSession) -> None:
    """Remove old disabled tokens in batches to avoid loading millions of records into memory."""
    cutoff = datetime.now(UTC) - timedelta(days=config.settings.disabled_tokens_ttl_days)

    total_removed = 0
    batch_size = 50

    while True:
        stmt = (
            select(models.UploadToken)
            .where(models.UploadToken.disabled.is_(True))
            .where(models.UploadToken.expires_at < cutoff)
            .limit(batch_size)
        )
        res = await session.execute(stmt)
        batch = res.scalars().all()

        if not batch:
            break

        for token in batch:
            if config.settings.delete_files_on_token_cleanup:
                uploads_stmt = select(models.UploadRecord).where(models.UploadRecord.token_id == token.id)
                uploads_res = await session.execute(uploads_stmt)
                uploads = uploads_res.scalars().all()

                for upload in uploads:
                    if upload.storage_path:
                        path = Path(upload.storage_path)
                        if path.exists():
                            try:
                                path.unlink()
                            except OSError:
                                logger.warning(
                                    "Failed to remove upload file during token cleanup: %s",
                                    path,
                                )
                    await session.delete(upload)

            storage_dir = Path(config.settings.storage_path).expanduser().resolve() / token.token
            if storage_dir.exists() and storage_dir.is_dir():
                with contextlib.suppress(OSError):
                    storage_dir.rmdir()

            await session.delete(token)

        await session.flush()
        await session.commit()
        total_removed += len(batch)

        if len(batch) < batch_size:
            break

    if total_removed > 0:
        logger.info(
            "Removed %d disabled tokens (files_deleted=%s)",
            total_removed,
            config.settings.delete_files_on_token_cleanup,
        )


async def start_cleanup_loop() -> None:
    while True:
        try:
            await _cleanup_once()
        except Exception as exc:
            logger.exception("Cleanup loop error", exc_info=exc)

        await asyncio.sleep(config.settings.cleanup_interval_seconds)
