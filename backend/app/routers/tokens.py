import contextlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import Sequence, select
from sqlalchemy.engine.result import Result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.selectable import Select

from backend.app import models, schemas, utils
from backend.app.config import settings
from backend.app.db import SessionLocal, get_db
from backend.app.security import optional_admin_check, verify_admin

if TYPE_CHECKING:
    from sqlalchemy.engine.result import Result
    from sqlalchemy.sql.selectable import Select

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


def _generate_token_value(num_bytes: int, prefix: str = "") -> str:
    while True:
        token = secrets.token_urlsafe(num_bytes)
        if token.startswith("-") or token.endswith("-"):
            continue

        return f"{prefix}{token}"


def _get_thumbnail_fallback_path() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    candidates = (
        repo_root / "frontend" / "public" / "images" / "thumbnail-fallback.jpg",
        repo_root / "frontend" / "app" / "assets" / "images" / "thumbnail-fallback.jpg",
        Path(settings.frontend_export_path).resolve() / "images" / "thumbnail-fallback.jpg",
        Path(settings.frontend_export_path).resolve() / "assets" / "images" / "thumbnail-fallback.jpg",
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return candidates[0]


async def _get_accessible_upload(
    download_token: str,
    upload_id: str,
    db: AsyncSession,
    is_admin: bool,
) -> tuple[models.UploadToken, models.UploadRecord, Path]:
    token_stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(models.UploadToken.download_token == download_token)
    token_res: Result[tuple[models.UploadToken]] = await db.execute(token_stmt)
    if not (token_row := token_res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Download token not found")

    if not is_admin:
        now: datetime = datetime.now(UTC)
        expires_at: datetime = token_row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        if expires_at < now:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token has expired")

        if token_row.disabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token is disabled")

    upload_stmt: Select[tuple[models.UploadRecord]] = select(models.UploadRecord).where(
        models.UploadRecord.public_id == upload_id, models.UploadRecord.token_id == token_row.id
    )
    upload_res: Result[tuple[models.UploadRecord]] = await db.execute(upload_stmt)

    if not (record := upload_res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    if record.status != "completed":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Upload not yet completed")

    path = Path(record.storage_path or "")
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File missing")

    return token_row, record, path


def _set_upload_urls(request: Request, item: schemas.UploadRecordResponse, download_token: str, upload_id: str) -> None:
    item.download_url = str(request.app.url_path_for("download_file", download_token=download_token, upload_id=upload_id))
    item.stream_url = str(request.app.url_path_for("stream_file", download_token=download_token, upload_id=upload_id))
    item.thumbnail_url = str(request.app.url_path_for("get_file_thumbnail", download_token=download_token, upload_id=upload_id))
    item.upload_url = str(request.app.url_path_for("tus_head", upload_id=upload_id))
    item.info_url = str(request.app.url_path_for("get_file_info", download_token=download_token, upload_id=upload_id))


@router.get("/", response_model=schemas.TokenListResponse, name="list_tokens")
async def list_tokens(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 10,
) -> schemas.TokenListResponse:
    """
    List all created upload tokens.

    Args:
        db (AsyncSession): The database session.
        skip (int): Number of records to skip.
        limit (int): Maximum number of records to return.

    Returns:
        TokenListResponse: A list of upload tokens with total count.

    """
    count_stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken)
    count_res: Result[tuple[models.UploadToken]] = await db.execute(count_stmt)

    stmt: Select[tuple[models.UploadToken]] = (
        select(models.UploadToken).order_by(models.UploadToken.created_at.desc()).offset(skip).limit(limit)
    )
    res: Result[tuple[models.UploadToken]] = await db.execute(stmt)

    return schemas.TokenListResponse(
        tokens=res.scalars().all(),
        total=len(count_res.scalars().all()),
    )


@router.post("/", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED, name="create_token")
async def create_token(
    request: Request,
    payload: schemas.TokenCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
) -> schemas.TokenResponse:
    """
    Create a new upload token.

    Args:
        request (Request): The FastAPI request object.
        payload (TokenCreate): The token creation payload.
        db (AsyncSession): The database session.

    Returns:
        TokenResponse: The created upload token details.

    """
    expires_at: datetime = payload.expiry_datetime or datetime.now(UTC) + timedelta(hours=settings.default_token_ttl_hours)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    upload_token: str = _generate_token_value(18)
    download_token: str = _generate_token_value(16, prefix="fbc_")

    record = models.UploadToken(
        token=upload_token,
        download_token=download_token,
        max_uploads=payload.max_uploads,
        max_size_bytes=payload.max_size_bytes,
        expires_at=expires_at,
        allowed_mime=payload.allowed_mime,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return schemas.TokenResponse(
        token=upload_token,
        download_token=download_token,
        upload_url=str(request.app.url_path_for("upload_page", token=upload_token)),
        expires_at=record.expires_at,
        max_uploads=record.max_uploads,
        max_size_bytes=record.max_size_bytes,
        allowed_mime=record.allowed_mime,
    )


@router.get("/{token_value}", response_model=schemas.TokenPublicInfo, name="get_token")
async def get_token(
    request: Request,
    token_value: str,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> schemas.TokenPublicInfo:
    """
    Get information about an token.

    Args:
        request (Request): The FastAPI request object.
        token_value (str): The upload or download token value.
        db (AsyncSession): The database session.

    Returns:
        TokenPublicInfo: The upload token information

    """
    stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    res: Result[tuple[models.UploadToken]] = await db.execute(stmt)

    if not (token_row := res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    uploads_stmt: Select[tuple[models.UploadRecord]] = (
        select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id).order_by(models.UploadRecord.created_at.desc())
    )
    uploads_res: Result[tuple[models.UploadRecord]] = await db.execute(uploads_stmt)
    uploads: Sequence[models.UploadRecord] = uploads_res.scalars().all()

    uploads_list: list[schemas.UploadRecordResponse] = []
    for u in uploads:
        item: schemas.UploadRecordResponse = schemas.UploadRecordResponse.model_validate(u, from_attributes=True)
        _set_upload_urls(request, item, token_row.download_token, u.public_id)
        uploads_list.append(item)

    return schemas.TokenPublicInfo(
        token=token_row.token if token_value == token_row.token else None,
        download_token=token_row.download_token,
        remaining_uploads=token_row.remaining_uploads,
        max_uploads=token_row.max_uploads,
        max_size_bytes=token_row.max_size_bytes,
        max_chunk_bytes=settings.max_chunk_bytes,
        allowed_mime=token_row.allowed_mime,
        expires_at=token_row.expires_at,
        disabled=token_row.disabled,
        allow_public_downloads=settings.allow_public_downloads,
        uploads=uploads_list,
    )


@router.patch("/{token_value}", response_model=schemas.TokenInfo, name="update_token")
async def update_token(
    token_value: str,
    payload: schemas.TokenUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
) -> models.UploadToken:
    """
    Update an existing upload token.

    Args:
        token_value (str): The upload or download token value.
        payload (TokenUpdate): The token update payload.
        db (AsyncSession): The database session.

    Returns:
        UploadToken: The updated upload token.

    """
    token_stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res: Result[tuple[models.UploadToken]] = await db.execute(token_stmt)

    if not (token_row := token_res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if payload.max_uploads is not None:
        if payload.max_uploads < token_row.uploads_used:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="max_uploads cannot be less than uploads already used",
            )
        token_row.max_uploads = payload.max_uploads

    if payload.max_size_bytes is not None:
        token_row.max_size_bytes = payload.max_size_bytes

    if payload.allowed_mime is not None:
        token_row.allowed_mime = payload.allowed_mime

    if payload.expiry_datetime:
        expires_at: datetime = payload.expiry_datetime

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        token_row.expires_at = expires_at

    if payload.extend_hours:
        expires_at = token_row.expires_at

        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)

        token_row.expires_at = expires_at + timedelta(hours=payload.extend_hours)

    if payload.disabled is not None:
        token_row.disabled = payload.disabled

    await db.commit()
    await db.refresh(token_row)
    return token_row


@router.delete("/{token_value}", status_code=status.HTTP_204_NO_CONTENT, name="delete_token")
async def delete_token(
    token_value: str,
    *,
    delete_files: Annotated[bool, Query(..., description="Also delete uploaded files")] = False,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
) -> Response:
    """
    Delete an upload token and optionally its associated files.

    Args:
        token_value (str): The upload or download token value.
        delete_files (bool): Whether to delete associated uploaded files.
        db (AsyncSession): The database session.

    Returns:
        Response: A response with status code 204 No Content.

    """
    token_stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res: Result[tuple[models.UploadToken]] = await db.execute(token_stmt)

    if not (token_row := token_res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if delete_files:
        uploads_stmt: Select[tuple[models.UploadRecord]] = select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id)
        uploads_res: Result[tuple[models.UploadRecord]] = await db.execute(uploads_stmt)
        uploads: Sequence[models.UploadRecord] = uploads_res.scalars().all()
        for record in uploads:
            utils.delete_upload_artifacts(record.storage_path)

        storage_dir: Path = Path(settings.storage_path).expanduser().resolve() / token_row.token
        if storage_dir.exists() and storage_dir.is_dir():
            with contextlib.suppress(OSError):
                storage_dir.rmdir()

    await db.delete(token_row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{token_value}/uploads", response_model=list[schemas.UploadRecordResponse], name="list_token_uploads")
@router.get("/{token_value}/uploads/", response_model=list[schemas.UploadRecordResponse])
async def list_token_uploads(
    request: Request,
    token_value: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(optional_admin_check)],
) -> list[schemas.UploadRecordResponse]:
    """
    List all uploads associated with a given token.

    Args:
        request (Request): The FastAPI request object.
        token_value (str): The upload or download token value.
        db (AsyncSession): The database session.

    Returns:
        list[UploadRecordResponse]: A list of upload records with URLs.

    """
    token_stmt: Select[tuple[models.UploadToken]] = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res: Result[tuple[models.UploadToken]] = await db.execute(token_stmt)

    if not (token_row := token_res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    stmt: Select[tuple[models.UploadRecord]] = (
        select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id).order_by(models.UploadRecord.created_at.desc())
    )
    res: Result[tuple[models.UploadRecord]] = await db.execute(stmt)
    uploads: Sequence[models.UploadRecord] = res.scalars().all()
    uploads_list: list[schemas.UploadRecordResponse] = []
    for u in uploads:
        item: schemas.UploadRecordResponse = schemas.UploadRecordResponse.model_validate(u, from_attributes=True)
        _set_upload_urls(request, item, token_row.download_token, u.public_id)
        uploads_list.append(item)

    return uploads_list


@router.get("/{download_token}/uploads/{upload_id}", name="get_file_info", summary="Get upload file info")
@router.get("/{download_token}/uploads/{upload_id}/")
async def get_file_info(
    request: Request,
    download_token: str,
    upload_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    is_admin: Annotated[bool, Depends(optional_admin_check)],
) -> schemas.UploadRecordResponse:
    """
    Retrieve metadata about a specific uploaded file.

    Args:
        request (Request): The FastAPI request object.
        download_token (str): The download token associated with the upload.
        upload_id (str): The public ID of the upload.
        db (AsyncSession): The database session.
        is_admin (bool): Whether the request is authenticated as admin.

    Returns:
        UploadRecordResponse: Metadata about the uploaded file.

    """
    _, record, _ = await _get_accessible_upload(download_token, upload_id, db, is_admin)

    item: schemas.UploadRecordResponse = schemas.UploadRecordResponse.model_validate(record, from_attributes=True)
    _set_upload_urls(request, item, download_token, upload_id)
    return item


@router.get("/{download_token}/uploads/{upload_id}/thumbnail", name="get_file_thumbnail", response_model=None)
@router.head("/{download_token}/uploads/{upload_id}/thumbnail", response_model=None)
@router.get("/{download_token}/uploads/{upload_id}/thumbnail/", response_model=None)
@router.head("/{download_token}/uploads/{upload_id}/thumbnail/", response_model=None)
async def get_file_thumbnail(
    download_token: str,
    upload_id: str,
    is_admin: Annotated[bool, Depends(optional_admin_check)],
) -> Response:
    """Return a generated video thumbnail or the shared fallback image."""
    async with SessionLocal() as db:
        _, _, path = await _get_accessible_upload(download_token, upload_id, db, is_admin)
        thumbnail_path = utils.get_thumbnail_path(path)

    if thumbnail_path.exists() and thumbnail_path.stat().st_size > 0:
        return FileResponse(
            thumbnail_path,
            filename=thumbnail_path.name,
            media_type=utils.THUMBNAIL_MEDIA_TYPE,
            content_disposition_type="inline",
        )

    fallback_path = _get_thumbnail_fallback_path()
    if not fallback_path.is_file():
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Thumbnail fallback missing")

    return FileResponse(
        fallback_path,
        filename=fallback_path.name,
        media_type=utils.THUMBNAIL_MEDIA_TYPE,
        content_disposition_type="inline",
    )


@router.get("/{download_token}/uploads/{upload_id}/preview.mp4", name="get_file_preview")
@router.head("/{download_token}/uploads/{upload_id}/preview.mp4", response_model=None)
@router.get("/{download_token}/uploads/{upload_id}/preview.mp4/", response_model=None)
@router.head("/{download_token}/uploads/{upload_id}/preview.mp4/", response_model=None)
async def get_file_preview(
    download_token: str,
    upload_id: str,
    is_admin: Annotated[bool, Depends(optional_admin_check)],
) -> FileResponse:
    """Return a generated short MP4 preview for bot embeds when available."""
    async with SessionLocal() as db:
        _, _, path = await _get_accessible_upload(download_token, upload_id, db, is_admin)
        preview_path = utils.get_preview_path(path)

    if not preview_path.exists() or preview_path.stat().st_size == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preview missing")

    return FileResponse(
        preview_path,
        filename=preview_path.name,
        media_type=utils.PREVIEW_MEDIA_TYPE,
        content_disposition_type="inline",
    )


@router.get("/{download_token}/uploads/{upload_id}/stream", name="stream_file")
@router.head("/{download_token}/uploads/{upload_id}/stream", response_model=None)
@router.get("/{download_token}/uploads/{upload_id}/stream/", response_model=None)
@router.head("/{download_token}/uploads/{upload_id}/stream/", response_model=None)
async def stream_file(
    download_token: str,
    upload_id: str,
    is_admin: Annotated[bool, Depends(optional_admin_check)],
) -> FileResponse:
    """Stream a completed file inline for media playback."""
    async with SessionLocal() as db:
        _, record, path = await _get_accessible_upload(download_token, upload_id, db, is_admin)
        filename = record.filename or path.name
        media_type = record.mimetype or "application/octet-stream"

    return FileResponse(
        path,
        filename=filename,
        media_type=media_type,
        content_disposition_type="inline",
    )


@router.get("/{download_token}/uploads/{upload_id}/download", name="download_file")
@router.head("/{download_token}/uploads/{upload_id}/download", response_model=None)
@router.get("/{download_token}/uploads/{upload_id}/download/", response_model=None)
@router.head("/{download_token}/uploads/{upload_id}/download/", response_model=None)
async def download_file(
    download_token: str,
    upload_id: str,
    is_admin: Annotated[bool, Depends(optional_admin_check)],
) -> FileResponse:
    """
    Download the file associated with a specific upload.

    Args:
        download_token (str): The download token associated with the upload.
        upload_id (str): The public ID of the upload.
        db (AsyncSession): The database session.
        is_admin (bool): Whether the request is authenticated as admin.

    Returns:
        FileResponse: The file response for downloading the file.

    """
    async with SessionLocal() as db:
        _, record, path = await _get_accessible_upload(download_token, upload_id, db, is_admin)
        filename = record.filename or path.name
        media_type = record.mimetype or "application/octet-stream"

    return FileResponse(path, filename=filename, media_type=media_type)
