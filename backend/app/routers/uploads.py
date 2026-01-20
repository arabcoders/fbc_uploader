import contextlib
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import aiofiles
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from backend.app import models, schemas
from backend.app.config import settings
from backend.app.db import get_db
from backend.app.metadata_schema import validate_metadata
from backend.app.postprocessing import ProcessingQueue
from backend.app.utils import detect_mimetype, is_multimedia, mime_allowed

if TYPE_CHECKING:
    from sqlalchemy.engine.result import Result
    from sqlalchemy.sql.selectable import Select

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


def get_processing_queue(request: Request) -> ProcessingQueue | None:
    """Get the processing queue from app state (returns None if not available in tests)."""
    return getattr(request.app.state, "processing_queue", None)


async def _ensure_token(
    db: AsyncSession,
    token_value: str | None = None,
    token_id: int | None = None,
    check_remaining: bool = True,
) -> models.UploadToken:
    """
    Ensure the upload token is valid, not expired or disabled, and optionally has remaining uploads.

    Args:
        db (AsyncSession): Database session.
        token_value (str | None): The upload token string.
        token_id (int | None): The upload token ID.
        check_remaining (bool): Whether to check remaining uploads. Defaults to True.

    Returns:
        UploadToken: The valid upload token object.

    """
    if token_value:
        stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(models.UploadToken.token == token_value)
    elif token_id:
        stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(models.UploadToken.id == token_id)
    else:
        msg = "Either token_value or token_id must be provided"
        raise ValueError(msg)

    res: Result[tuple[models.UploadToken]] = await db.execute(stmt)
    if not (token := res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    now: datetime = datetime.now(UTC)
    expires_at: datetime = token.expires_at

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at < now:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token expired")
    if token.disabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token disabled")

    if check_remaining and token.remaining_uploads <= 0:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload limit reached")

    return token


async def _get_upload_record(db: AsyncSession, upload_id: str) -> models.UploadRecord:
    """
    Retrieve the upload record by its public ID.

    Args:
        db (AsyncSession): Database session.
        upload_id (str): The public ID of the upload.

    Returns:
        UploadRecord: The upload record object.

    """
    stmt: Select[tuple[models.UploadRecord]] = select(models.UploadRecord).where(models.UploadRecord.public_id == upload_id)
    res: Result[tuple[models.UploadRecord]] = await db.execute(stmt)
    if not (record := res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    return record


@router.post("/initiate", response_model=schemas.InitiateUploadResponse, status_code=status.HTTP_201_CREATED, name="initiate_upload")
async def initiate_upload(
    request: Request,
    payload: schemas.UploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Query(description="Upload token")] = ...,
) -> schemas.InitiateUploadResponse:
    """
    Initiate a new upload record and prepare for TUS upload.

    Args:
        request (Request): The incoming HTTP request.
        payload (UploadRequest): The upload request payload.
        db (AsyncSession): Database session.
        token (str): The upload token string.

    Returns:
        InitiateUploadResponse: Details for the initiated upload.

    """
    token_row: models.UploadToken = await _ensure_token(db, token)
    cleaned_metadata: dict[str, Any] = validate_metadata(payload.meta_data or {})

    if payload.size_bytes and payload.size_bytes > token_row.max_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="File size exceeds token limit",
        )

    if not mime_allowed(payload.filetype, token_row.allowed_mime):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="File type not allowed for this token",
        )

    ext: str | None = None
    if payload.filename:
        ext: str = Path(payload.filename).suffix.lstrip(".")

    record = models.UploadRecord(
        public_id=secrets.token_urlsafe(18),
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

    return schemas.InitiateUploadResponse(
        upload_id=record.public_id,
        upload_url=str(request.app.url_path_for("tus_head", upload_id=record.public_id)),
        download_url=str(request.app.url_path_for("download_file", download_token=token_row.download_token, upload_id=record.public_id)),
        meta_data=cleaned_metadata,
        allowed_mime=token_row.allowed_mime,
        remaining_uploads=token_row.remaining_uploads,
    )


@router.head("/{upload_id}/tus", name="tus_head")
async def tus_head(upload_id: str, db: Annotated[AsyncSession, Depends(get_db)]):
    """
    Handle TUS protocol HEAD request to get upload status.

    Args:
        upload_id (str): The public ID of the upload.
        db (AsyncSession): Database session.

    Returns:
        Response: HTTP response with upload offset and length.

    """
    record: models.UploadRecord = await _get_upload_record(db, upload_id)
    await _ensure_token(db, token_id=record.token_id, check_remaining=False)

    if record.upload_length is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload length unknown")

    return Response(
        status_code=status.HTTP_200_OK,
        headers={
            "Upload-Offset": str(record.upload_offset or 0),
            "Upload-Length": str(record.upload_length),
            "Tus-Resumable": "1.0.0",
        },
    )


@router.patch("/{upload_id}/tus", name="tus_patch")
async def tus_patch(
    upload_id: str,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    queue: Annotated[ProcessingQueue | None, Depends(get_processing_queue)],
    upload_offset: Annotated[int, Header(convert_underscores=False, alias="Upload-Offset")] = ...,
    content_length: Annotated[int | None, Header()] = None,
    content_type: Annotated[str, Header(convert_underscores=False, alias="Content-Type")] = ...,
) -> Response:
    """
    Handle TUS protocol PATCH request to upload file chunks.

    Args:
        upload_id (str): The public ID of the upload.
        request (Request): The incoming HTTP request.
        db (AsyncSession): Database session.
        queue (ProcessingQueue | None): The processing queue for post-processing.
        upload_offset (int): The current upload offset from the client.
        content_length (int | None): The Content-Length header value.
        content_type (str): The Content-Type header value.

    Returns:
        Response: HTTP response with updated upload offset.

    """
    from starlette.requests import ClientDisconnect

    if content_type != "application/offset+octet-stream":
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Invalid Content-Type")

    if content_length and content_length > settings.max_chunk_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Chunk too large. Max {settings.max_chunk_bytes} bytes",
        )

    record: models.UploadRecord = await _get_upload_record(db, upload_id)
    await _ensure_token(db, token_id=record.token_id, check_remaining=False)

    if record.upload_length is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload length unknown")

    if record.upload_offset != upload_offset:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Mismatched Upload-Offset")

    if "completed" == record.status:
        return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Upload-Offset": str(record.upload_offset)})

    path = Path(record.storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bytes_written: int = 0

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
            raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail="Upload exceeds declared length")

        if record.upload_offset == record.upload_length:
            try:
                actual_mimetype: str = detect_mimetype(path)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to detect file type: {e}",
                )

            stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(models.UploadToken.id == record.token_id)
            res: Result[tuple[models.UploadToken]] = await db.execute(stmt)

            if not (token := res.scalar_one_or_none()):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

            if not mime_allowed(actual_mimetype, token.allowed_mime):
                path.unlink(missing_ok=True)
                await db.delete(record)
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                    detail=f"Actual file type '{actual_mimetype}' does not match allowed types",
                )

            record.mimetype = actual_mimetype

            if is_multimedia(actual_mimetype):
                record.status = "postprocessing"
                await db.commit()
                await db.refresh(record)
                if queue:
                    await queue.enqueue(record.public_id)
            else:
                record.status = "completed"
                record.completed_at = datetime.now(UTC)
                await db.commit()
                await db.refresh(record)
        else:
            record.status = "in_progress"

            try:
                await db.commit()
                await db.refresh(record)
            except Exception:
                await db.rollback()
                await db.refresh(record)

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "Upload-Offset": str(record.upload_offset),
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(record.upload_length),
        },
    )


@router.options("/tus", name="tus_options")
async def tus_options() -> Response:
    """Handle TUS protocol OPTIONS request."""
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={
            "Tus-Resumable": "1.0.0",
            "Tus-Version": "1.0.0",
            "Tus-Extension": "creation,termination",
        },
    )


@router.delete("/{upload_id}/tus", status_code=status.HTTP_204_NO_CONTENT, name="tus_delete")
async def tus_delete(upload_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> Response:
    """
    Delete an upload record and its associated file.

    Args:
        upload_id (str): The public ID of the upload.
        db (AsyncSession): Database session.

    Returns:
        Response: HTTP 204 No Content response.

    """
    record: models.UploadRecord = await _get_upload_record(db, upload_id)
    await _ensure_token(db, token_id=record.token_id, check_remaining=False)

    path = Path(record.storage_path or "")

    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()

    await db.delete(record)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{upload_id}/complete", response_model=schemas.UploadRecordResponse, name="mark_complete")
async def mark_complete(upload_id: str, db: Annotated[AsyncSession, Depends(get_db)]) -> models.UploadRecord:
    """
    Mark an upload as complete.

    Args:
        upload_id (str): The public ID of the upload.
        db (AsyncSession): Database session.

    Returns:
        UploadRecord: The updated upload record.

    """
    record: models.UploadRecord = await _get_upload_record(db, upload_id)
    await _ensure_token(db, token_id=record.token_id, check_remaining=False)

    record.status = "completed"
    record.completed_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(record)
    return record


@router.delete("/{upload_id}/cancel", response_model=dict, name="cancel_upload")
async def cancel_upload(
    upload_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    token: Annotated[str, Query(description="Upload token")] = ...,
) -> dict[str, Any]:
    """
    Cancel an incomplete upload, delete the record, and restore the upload slot.

    Args:
        upload_id (str): The public ID of the upload.
        db (AsyncSession): Database session.
        token (str): The upload token string.

    Returns:
        dict: Confirmation message and remaining uploads.

    """
    record: models.UploadRecord = await _get_upload_record(db, upload_id)
    token_row: models.UploadToken = await _ensure_token(db, token_value=token, check_remaining=False)

    if record.token_id != token_row.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Upload does not belong to this token")

    if "completed" == record.status:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot cancel completed upload")

    path = Path(record.storage_path or "")
    if path.exists():
        with contextlib.suppress(OSError):
            path.unlink()

    await db.delete(record)

    token_row.uploads_used -= 1

    await db.commit()
    await db.refresh(token_row)

    return {
        "message": "Upload cancelled successfully",
        "remaining_uploads": token_row.remaining_uploads,
    }
