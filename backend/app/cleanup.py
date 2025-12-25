import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from . import models
from .config import settings
from .db import SessionLocal

logger: logging.Logger = logging.getLogger(__name__)


async def _cleanup_once() -> None:
    async with SessionLocal() as session:
        await _disable_expired_tokens(session)
        if settings.incomplete_ttl_hours > 0:
            await _remove_stale_uploads(session)
        if settings.disabled_tokens_ttl_days > 0:
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
        logger.info("Disabled expired tokens", count=res.rowcount)
    await session.commit()


async def _remove_stale_uploads(session: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - timedelta(hours=settings.incomplete_ttl_hours)
    stmt = select(models.UploadRecord).where(models.UploadRecord.status != "completed", models.UploadRecord.created_at < cutoff)
    res = await session.execute(stmt)
    stale = res.scalars().all()
    for record in stale:
        if record.storage_path:
            path = Path(record.storage_path)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.warning("Failed to remove stale upload file", path=str(path))
        await session.delete(record)
    if stale:
        await session.commit()
        logger.info("Removed stale uploads", count=len(stale))


async def _remove_disabled_tokens(session: AsyncSession) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=settings.disabled_tokens_ttl_days)
    stmt = select(models.UploadToken).where(models.UploadToken.disabled.is_(True), models.UploadToken.expires_at < cutoff)
    res = await session.execute(stmt)
    disabled_tokens = res.scalars().all()

    for token in disabled_tokens:
        if settings.delete_files_on_token_cleanup:
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
                            logger.warning("Failed to remove upload file during token cleanup", path=str(path))
                await session.delete(upload)

        storage_dir: Path = Path(settings.storage_path).expanduser().resolve() / token.token
        if storage_dir.exists() and storage_dir.is_dir():
            with contextlib.suppress(OSError):
                storage_dir.rmdir()

        await session.delete(token)

    if disabled_tokens:
        await session.commit()
        logger.info("Removed disabled tokens", count=len(disabled_tokens), files_deleted=settings.delete_files_on_token_cleanup)


async def start_cleanup_loop() -> None:
    while True:
        try:
            await _cleanup_once()
        except Exception as exc:
            logger.exception("Cleanup loop error", exc_info=exc)

        await asyncio.sleep(settings.cleanup_interval_seconds)
