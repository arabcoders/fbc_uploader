from datetime import UTC, datetime, timedelta
from pathlib import Path
import secrets

import pytest
from sqlalchemy import select

from backend.app import cleanup, models, utils
from backend.app.config import settings
from backend.app.db import SessionLocal


def _ensure_storage() -> Path:
    storage_root = Path(settings.storage_path)
    storage_root.mkdir(parents=True, exist_ok=True)
    return storage_root


@pytest.mark.asyncio
async def test_disable_expired_tokens_marks_disabled():
    now = datetime.now(UTC)
    expired = models.UploadToken(
        token="expired",
        download_token="expired_dl",
        max_uploads=1,
        max_size_bytes=1,
        expires_at=now - timedelta(hours=1),
    )
    active = models.UploadToken(
        token="active",
        download_token="active_dl",
        max_uploads=1,
        max_size_bytes=1,
        expires_at=now + timedelta(hours=1),
    )

    async with SessionLocal() as session:
        session.add_all([expired, active])
        await session.commit()

    async with SessionLocal() as session:
        await cleanup._disable_expired_tokens(session)

    async with SessionLocal() as session:
        res = await session.execute(select(models.UploadToken))
        tokens = {token.token: token for token in res.scalars().all()}

    assert tokens["expired"].disabled is True, "Expired token should be marked as disabled"
    assert tokens["active"].disabled is False, "Active token should remain enabled"


@pytest.mark.asyncio
async def test_remove_stale_uploads_deletes_files(monkeypatch):
    monkeypatch.setattr(settings, "incomplete_ttl_hours", 1)
    stale_token_value = f"stale-token-{secrets.token_urlsafe(8)}"
    stale_download_value = f"stale-dl-{secrets.token_urlsafe(8)}"
    storage_root = _ensure_storage()
    file_path = storage_root / "stale.bin"
    file_path.write_text("stale")
    thumbnail_path = utils.get_thumbnail_path(file_path)
    thumbnail_path.write_bytes(b"thumbnail")

    token = models.UploadToken(
        token=stale_token_value,
        download_token=stale_download_value,
        max_uploads=1,
        max_size_bytes=10,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    async with SessionLocal() as session:
        session.add(token)
        await session.commit()
        await session.refresh(token)

        stale_upload = models.UploadRecord(
            public_id=secrets.token_urlsafe(18),
            token_id=token.id,
            filename="stale.bin",
            size_bytes=5,
            storage_path=str(file_path),
            status="pending",
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )
        session.add(stale_upload)
        await session.commit()

    async with SessionLocal() as session:
        await cleanup._remove_stale_uploads(session)

    async with SessionLocal() as session:
        res = await session.execute(select(models.UploadRecord).where(models.UploadRecord.public_id == stale_upload.public_id))
        remaining = res.scalars().all()

    assert not remaining, "Stale upload record should be removed"
    assert not file_path.exists(), "Stale upload file should be deleted"
    assert not thumbnail_path.exists(), "Stale upload thumbnail should be deleted"


@pytest.mark.asyncio
async def test_remove_disabled_tokens_cleans_records_and_storage(monkeypatch):
    monkeypatch.setattr(settings, "disabled_tokens_ttl_days", 1)
    monkeypatch.setattr(settings, "delete_files_on_token_cleanup", True)
    old_token_value = f"old-token-{secrets.token_urlsafe(8)}"
    old_download_value = f"old-dl-{secrets.token_urlsafe(8)}"
    recent_token_value = f"recent-token-{secrets.token_urlsafe(8)}"
    recent_download_value = f"recent-dl-{secrets.token_urlsafe(8)}"
    storage_root = _ensure_storage()

    old_token_dir = storage_root / old_token_value
    old_token_dir.mkdir(parents=True, exist_ok=True)
    old_file = old_token_dir / "old.txt"
    old_file.write_text("old-data")
    old_thumbnail = utils.get_thumbnail_path(old_file)
    old_thumbnail.write_bytes(b"thumbnail")

    recent_token_dir = storage_root / recent_token_value
    recent_token_dir.mkdir(parents=True, exist_ok=True)
    recent_file = recent_token_dir / "recent.txt"
    recent_file.write_text("recent-data")

    now = datetime.now(UTC)
    old_token = models.UploadToken(
        token=old_token_value,
        download_token=old_download_value,
        max_uploads=1,
        max_size_bytes=10,
        expires_at=now - timedelta(days=2),
        disabled=True,
    )
    recent_token = models.UploadToken(
        token=recent_token_value,
        download_token=recent_download_value,
        max_uploads=1,
        max_size_bytes=10,
        expires_at=now - timedelta(hours=12),
        disabled=True,
    )

    async with SessionLocal() as session:
        session.add_all([old_token, recent_token])
        await session.commit()
        await session.refresh(old_token)
        await session.refresh(recent_token)

        old_upload = models.UploadRecord(
            public_id=secrets.token_urlsafe(18),
            token_id=old_token.id,
            filename="old.txt",
            size_bytes=9,
            storage_path=str(old_file),
            status="completed",
            created_at=now - timedelta(days=2),
            completed_at=now - timedelta(days=2),
        )
        recent_upload = models.UploadRecord(
            public_id=secrets.token_urlsafe(18),
            token_id=recent_token.id,
            filename="recent.txt",
            size_bytes=11,
            storage_path=str(recent_file),
            status="completed",
            created_at=now - timedelta(hours=12),
            completed_at=now - timedelta(hours=12),
        )
        session.add_all([old_upload, recent_upload])
        await session.commit()

    async with SessionLocal() as session:
        await cleanup._remove_disabled_tokens(session)

    async with SessionLocal() as session:
        res = await session.execute(select(models.UploadToken).where(models.UploadToken.token.in_([old_token_value, recent_token_value])))
        tokens = {token.token: token for token in res.scalars().all()}
        uploads_res = await session.execute(
            select(models.UploadRecord).where(models.UploadRecord.public_id.in_([old_upload.public_id, recent_upload.public_id]))
        )
        uploads = uploads_res.scalars().all()

    assert old_token_value not in tokens, "Old disabled token should be removed"
    assert recent_token_value in tokens, "Recent disabled token should be retained"
    assert all(upload.token_id == tokens[recent_token_value].id for upload in uploads), "Only recent token uploads should remain"
    assert not old_file.exists(), "Old token file should be deleted"
    assert not old_thumbnail.exists(), "Old token thumbnail should be deleted"
    assert not old_token_dir.exists(), "Old token directory should be deleted"
    assert recent_file.exists(), "Recent token file should be retained"
    assert recent_token_dir.exists(), "Recent token directory should be retained"
