import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import models, schemas
from backend.app.config import settings
from backend.app.db import get_db
from backend.app.metadata_schema import validate_metadata
from backend.app.utils import detect_mimetype

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


async def _ensure_token(db: AsyncSession, token_value: str) -> models.UploadToken:
    stmt = select(models.UploadToken).where(models.UploadToken.token == token_value)
    res = await db.execute(stmt)
    token = res.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    now = datetime.now(UTC)
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if token.disabled or expires_at < now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token expired or disabled")
    if token.remaining_uploads <= 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload limit reached")
    return token


def _mime_allowed(filetype: str | None, allowed: list[str] | None) -> bool:
    if not allowed or not filetype:
        return True
    for pattern in allowed:
        if pattern.endswith("/*"):
            prefix = pattern.split("/")[0]
            if filetype.startswith(prefix + "/"):
                return True
        elif filetype == pattern:
            return True
    return False


@router.post("/initiate", response_model=dict, status_code=201, name="initiate_upload")
async def initiate_upload(
    request: Request,
    payload: schemas.UploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Query(description="Upload token")] = ...,
):
    token_row = await _ensure_token(db, token)
    cleaned_metadata = validate_metadata(payload.meta_data or {})
    if payload.size_bytes and payload.size_bytes > token_row.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File size exceeds token limit",
        )
    if not _mime_allowed(payload.filetype, token_row.allowed_mime):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File type not allowed for this token",
        )

    ext = None
    if payload.filename:
        ext = Path(payload.filename).suffix.lstrip(".")

    record = models.UploadRecord(
        token_id=token_row.id,
        filename=payload.filename,
        ext=ext,
        mimetype=payload.filetype,
        size_bytes=payload.size_bytes,
        meta_data=cleaned_metadata,
        storage_path="",
        upload_length=payload.size_bytes,
        status="initiated",
    )
    db.add(record)
    await db.flush()

    storage_dir: Path = Path(settings.storage_path).expanduser().resolve() / token_row.token
    storage_dir.mkdir(parents=True, exist_ok=True)
    filename_on_disk: str = f"{record.id}.{ext}" if ext else str(record.id)
    storage_path: Path = storage_dir / filename_on_disk
    record.storage_path = str(storage_path)
    token_row.uploads_used += 1

    await db.commit()
    await db.refresh(record)
    await db.refresh(token_row)

    upload_url = str(request.url_for("tus_head", upload_id=record.id))
    download_url = str(request.url_for("download_file", download_token=token_row.download_token, upload_id=record.id))

    return {
        "upload_id": record.id,
        "upload_url": upload_url,
        "download_url": download_url,
        "meta_data": cleaned_metadata,
        "allowed_mime": token_row.allowed_mime,
        "remaining_uploads": token_row.remaining_uploads,
    }


async def _get_upload_record(db: AsyncSession, upload_id: int) -> models.UploadRecord:
    stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    return record


@router.head("/{upload_id}/tus", name="tus_head")
async def tus_head(upload_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    record = await _get_upload_record(db, upload_id)
    if record.upload_length is None:
        raise HTTPException(status_code=409, detail="Upload length unknown")
    return Response(
        status_code=200,
        headers={
            "Upload-Offset": str(record.upload_offset or 0),
            "Upload-Length": str(record.upload_length),
            "Tus-Resumable": "1.0.0",
        },
    )


@router.patch("/{upload_id}/tus")
async def tus_patch(
    upload_id: int,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    upload_offset: Annotated[int, Header(convert_underscores=False, alias="Upload-Offset")] = ...,
    content_length: Annotated[int | None, Header()] = None,
    content_type: Annotated[str, Header(convert_underscores=False, alias="Content-Type")] = ...,
):
    from starlette.requests import ClientDisconnect

    if content_type != "application/offset+octet-stream":
        raise HTTPException(status_code=415, detail="Invalid Content-Type")
    if content_length and content_length > settings.max_chunk_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Chunk too large. Max {settings.max_chunk_bytes} bytes",
        )
    record = await _get_upload_record(db, upload_id)
    if record.upload_length is None:
        raise HTTPException(status_code=409, detail="Upload length unknown")
    if record.upload_offset != upload_offset:
        raise HTTPException(status_code=409, detail="Mismatched Upload-Offset")

    if record.status == "completed":
        return Response(status_code=204, headers={"Upload-Offset": str(record.upload_offset)})

    path = Path(record.storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written = 0

    try:
        async with aiofiles.open(path, "ab") as f:
            async for chunk in request.stream():
                await f.write(chunk)
                bytes_written += len(chunk)
    except ClientDisconnect:
        pass

    if bytes_written > 0:
        record.upload_offset += bytes_written
        if record.upload_offset > record.upload_length:
            raise HTTPException(status_code=413, detail="Upload exceeds declared length")

        if record.upload_offset == record.upload_length:
            try:
                actual_mimetype: str = detect_mimetype(path)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to detect file type: {e}",
                )

            stmt = select(models.UploadToken).where(models.UploadToken.id == record.token_id)
            res = await db.execute(stmt)
            token = res.scalar_one_or_none()
            if not token:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

            if not _mime_allowed(actual_mimetype, token.allowed_mime):
                path.unlink(missing_ok=True)
                await db.delete(record)
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Actual file type '{actual_mimetype}' does not match allowed types",
                )

            record.mimetype = actual_mimetype
            record.status = "completed"
            record.completed_at = datetime.now(UTC)
        else:
            record.status = "in_progress"

        try:
            await db.commit()
            await db.refresh(record)
        except Exception:
            # On concurrent update conflict, refresh and try again
            await db.rollback()
            await db.refresh(record)

    return Response(
        status_code=204,
        headers={
            "Upload-Offset": str(record.upload_offset),
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(record.upload_length),
        },
    )


@router.options("/tus")
async def tus_options():
    return Response(
        status_code=204,
        headers={
            "Tus-Resumable": "1.0.0",
            "Tus-Version": "1.0.0",
            "Tus-Extension": "creation,termination",
        },
    )


@router.delete("/{upload_id}/tus", status_code=204)
async def tus_delete(upload_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    record = await _get_upload_record(db, upload_id)
    path = Path(record.storage_path or "")
    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()
    await db.delete(record)
    await db.commit()
    return Response(status_code=204)


@router.post("/{upload_id}/complete", response_model=schemas.UploadRecordResponse)
async def mark_complete(upload_id: int, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    record.status = "completed"
    record.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{upload_id}/cancel", response_model=dict, name="cancel_upload")
async def cancel_upload(
    upload_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Query(description="Upload token")] = ...,
):
    """Cancel an incomplete upload, delete the record, and restore the upload slot."""
    record = await _get_upload_record(db, upload_id)

    stmt = select(models.UploadToken).where(models.UploadToken.token == token)
    res = await db.execute(stmt)
    token_row = res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if record.token_id != token_row.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload does not belong to this token")

    if record.status == "completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel completed upload")

    path = Path(record.storage_path or "")
    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()

    await db.delete(record)

    await db.execute(
        update(models.UploadToken).where(models.UploadToken.id == token_row.id).values(uploads_used=models.UploadToken.uploads_used - 1)
    )

    await db.commit()
    await db.refresh(token_row)

    return {
        "message": "Upload cancelled successfully",
        "remaining_uploads": token_row.remaining_uploads,
    }
