import asyncio
import contextlib
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from . import config, models
from .db import SessionLocal

if TYPE_CHECKING:
    from sqlalchemy.engine.result import Result
    from sqlalchemy.sql.dml import Update
    from sqlalchemy.sql.selectable import Select

logger: logging.Logger = logging.getLogger(__name__)


async def _cleanup_once() -> None:
    """Perform a single cleanup operation."""
    async with SessionLocal() as session:
        await _disable_expired_tokens(session)
        if config.settings.incomplete_ttl_hours > 0:
            await _remove_stale_uploads(session)
        if config.settings.disabled_tokens_ttl_days > 0:
            await _remove_disabled_tokens(session)


async def _disable_expired_tokens(session: AsyncSession) -> int:
    """
    Disable tokens that have expired.

    Args:
        session (AsyncSession): The database session.

    Returns:
        int: The number of tokens disabled.

    """
    now: datetime = datetime.now(UTC)
    stmt: Update = (
        update(models.UploadToken)
        .where(models.UploadToken.expires_at < now)
        .where(models.UploadToken.disabled.is_(False))
        .values(disabled=True)
    )

    res: Result[Any] = await session.execute(stmt)

    if res.rowcount:
        logger.info("Disabled %d expired tokens", res.rowcount)

    await session.commit()
    return res.rowcount


async def _remove_stale_uploads(session: AsyncSession) -> int:
    """
    Remove stale uploads.

    Args:
        session (AsyncSession): The database session.

    Returns:
        int: The number of uploads removed.

    """
    cutoff: datetime = datetime.now(UTC) - timedelta(hours=config.settings.incomplete_ttl_hours)
    cutoff_naive: datetime = cutoff.replace(tzinfo=None)

    total_removed = 0

    stmt: Select[tuple[models.UploadRecord]] = (
        select(models.UploadRecord)
        .where(models.UploadRecord.status.in_(["pending", "in_progress"]))
        .where(models.UploadRecord.created_at < cutoff_naive)
    )
    res: Result[tuple[models.UploadRecord]] = await session.execute(stmt)

    for record in res.scalars().all():
        if record.storage_path:
            path = Path(record.storage_path)
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    logger.warning("Failed to remove stale upload file: %s", path)

        total_removed += 1
        await session.delete(record)

    await session.flush()
    await session.commit()

    if total_removed > 0:
        logger.info("Removed %d stale uploads", total_removed)

    return total_removed


async def _remove_disabled_tokens(session: AsyncSession) -> int:
    """
    Remove old disabled tokens.

    Args:
        session (AsyncSession): The database session.

    Returns:
        int: The number of tokens removed

    """
    cutoff: datetime = datetime.now(UTC) - timedelta(days=config.settings.disabled_tokens_ttl_days)

    total_removed = 0

    stmt: Select[tuple[models.UploadToken]] = (
        select(models.UploadToken).where(models.UploadToken.disabled.is_(True)).where(models.UploadToken.expires_at < cutoff)
    )
    res: Result[tuple[models.UploadToken]] = await session.execute(stmt)

    for token in res.scalars().all():
        if config.settings.delete_files_on_token_cleanup:
            uploads_stmt: Select[tuple[models.UploadRecord]] = select(models.UploadRecord).where(models.UploadRecord.token_id == token.id)
            uploads_res: Result[tuple[models.UploadRecord]] = await session.execute(uploads_stmt)

            for upload in uploads_res.scalars().all():
                if upload.storage_path:
                    path = Path(upload.storage_path)
                    if path.exists():
                        try:
                            path.unlink()
                        except OSError:
                            logger.warning("Failed to remove upload file during token cleanup: %s", path)

                total_removed += 1
                await session.delete(upload)

        storage_dir: Path = Path(config.settings.storage_path).expanduser().resolve() / token.token
        if storage_dir.exists() and storage_dir.is_dir():
            with contextlib.suppress(OSError):
                storage_dir.rmdir()

        await session.delete(token)

    await session.flush()
    await session.commit()

    if total_removed > 0:
        logger.info(
            "Removed %d disabled tokens (files_deleted=%s)",
            total_removed,
            config.settings.delete_files_on_token_cleanup,
        )

    return total_removed


async def start_cleanup_loop() -> None:
    while True:
        try:
            await _cleanup_once()
        except Exception as exc:
            logger.exception("Cleanup loop error", exc_info=exc)

        await asyncio.sleep(config.settings.cleanup_interval_seconds)
