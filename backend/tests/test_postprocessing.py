"""Tests for post-processing worker."""

import asyncio
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.db import SessionLocal
from backend.app.postprocessing import process_upload
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

    await upload_file_via_tus(client, upload_id, video_content)

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
        result = await session.execute(stmt)
        record = result.scalar_one()

        assert record.status == "postprocessing", "Multimedia upload should enter postprocessing status"
        assert record.completed_at is None, "Upload should not be marked complete yet"


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

    await upload_file_via_tus(client, upload_id, pdf_content)

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
        result = await session.execute(stmt)
        record = result.scalar_one()

        assert record.status == "completed", "Non-multimedia upload should complete immediately"
        assert record.completed_at is not None, "Upload should be marked complete"


@pytest.mark.asyncio
async def test_postprocessing_worker_processes_queue(client):
    """Test that the post-processing worker processes pending uploads."""
    token_data = await create_token(client, max_uploads=2)
    token_value = token_data["token"]

    video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
    video_content = video_file.read_bytes()

    upload1_data = await initiate_upload(
        client, token_value, filename="video1.mp4", size_bytes=len(video_content), filetype="video/mp4", meta_data={"title": "Video 1"}
    )
    upload1_id = upload1_data["upload_id"]

    upload2_data = await initiate_upload(
        client, token_value, filename="video2.mp4", size_bytes=len(video_content), filetype="video/mp4", meta_data={"title": "Video 2"}
    )
    upload2_id = upload2_data["upload_id"]

    await upload_file_via_tus(client, upload1_id, video_content)
    await upload_file_via_tus(client, upload2_id, video_content)

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id.in_([upload1_id, upload2_id]))
        result = await session.execute(stmt)
        records = result.scalars().all()

        for record in records:
            assert record.status in ("postprocessing", "completed"), "Upload should be in postprocessing or already completed"

    completed = await wait_for_processing([upload1_id, upload2_id])
    assert completed, "Processing should complete within timeout"

    async with SessionLocal() as session:
        stmt = select(models.UploadRecord).where(models.UploadRecord.public_id.in_([upload1_id, upload2_id]))
        result = await session.execute(stmt)
        records = result.scalars().all()

        for record in records:
            assert record.status == "completed", "Both uploads should be completed after processing"
            assert record.completed_at is not None, "Both uploads should have completion time"


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

        success = await process_upload(session, record)
        assert success is False, "Processing should fail for missing file"

        await session.refresh(record)
        assert record.status == "failed", "Upload should be marked as failed"
        assert "error" in record.meta_data, "Error should be recorded in metadata"
