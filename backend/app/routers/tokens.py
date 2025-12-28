import contextlib
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import models, schemas
from backend.app.config import settings
from backend.app.db import get_db
from backend.app.security import verify_admin

router = APIRouter(prefix="/api/tokens", tags=["tokens"])


def optional_admin_check(
    authorization: Annotated[str | None, Header()] = None,
    api_key: Annotated[str | None, Query(description="API key")] = None,
) -> bool:
    """Check admin authentication only if public downloads are disabled."""
    if settings.allow_public_downloads:
        return True
    return verify_admin(authorization, api_key)


@router.get("/", name="list_tokens")
async def list_tokens(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
    skip: Annotated[int, Query(ge=0, description="Number of records to skip")] = 0,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum number of records to return")] = 10,
):
    count_stmt = select(models.UploadToken)
    count_res = await db.execute(count_stmt)
    total = len(count_res.scalars().all())

    stmt = select(models.UploadToken).order_by(models.UploadToken.created_at.desc()).offset(skip).limit(limit)
    res = await db.execute(stmt)
    tokens = res.scalars().all()

    return {"tokens": tokens, "total": total}


@router.post("/", response_model=schemas.TokenResponse, status_code=201, name="create_token")
async def create_token(
    request: Request,
    payload: schemas.TokenCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
):
    expires_at = payload.expiry_datetime or datetime.now(UTC) + timedelta(hours=settings.default_token_ttl_hours)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    upload_token: str = secrets.token_urlsafe(18)
    download_token: str = "fbc_" + secrets.token_urlsafe(16)

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

    upload_url = str(request.url_for("health"))
    if upload_token:
        upload_url = upload_url.replace("/api/health", f"/t/{upload_token}")

    return schemas.TokenResponse(
        token=upload_token,
        download_token=download_token,
        upload_url=upload_url,
        expires_at=record.expires_at,
        max_uploads=record.max_uploads,
        max_size_bytes=record.max_size_bytes,
        allowed_mime=record.allowed_mime,
    )


@router.get("/{token_value}", response_model=schemas.TokenInfo, name="get_token")
async def get_token(
    token_value: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(optional_admin_check)],
):
    stmt = select(models.UploadToken).where((models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value))
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")
    return record


@router.patch("/{token_value}", response_model=schemas.TokenInfo, name="update_token")
async def update_token(
    token_value: str,
    payload: schemas.TokenUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
):
    token_stmt = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res = await db.execute(token_stmt)
    token_row = token_res.scalar_one_or_none()
    if not token_row:
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
        expires_at = payload.expiry_datetime
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


@router.delete("/{token_value}", status_code=204, name="delete_token")
async def delete_token(
    token_value: str,
    *,
    delete_files: Annotated[bool, Query(..., description="Also delete uploaded files")] = False,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(verify_admin)],
):
    token_stmt = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res = await db.execute(token_stmt)
    token_row = token_res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if delete_files:
        uploads_stmt = select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id)
        uploads_res = await db.execute(uploads_stmt)
        uploads = uploads_res.scalars().all()
        for record in uploads:
            if record.storage_path:
                path = Path(record.storage_path)
                if path.exists():
                    with contextlib.suppress(OSError):
                        path.unlink()

        storage_dir: Path = Path(settings.storage_path).expanduser().resolve() / token_row.token
        if storage_dir.exists() and storage_dir.is_dir():
            with contextlib.suppress(OSError):
                storage_dir.rmdir()

    await db.delete(token_row)
    await db.commit()
    return Response(status_code=204)


@router.get("/{token_value}/uploads", response_model=list[schemas.UploadRecordResponse], name="list_token_uploads")
@router.get("/{token_value}/uploads/", response_model=list[schemas.UploadRecordResponse])
async def list_token_uploads(
    request: Request,
    token_value: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(optional_admin_check)],
):
    token_stmt = select(models.UploadToken).where(
        (models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value)
    )
    token_res = await db.execute(token_stmt)
    token_row = token_res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=404, detail="Token not found")

    stmt = select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id).order_by(models.UploadRecord.created_at.desc())
    res = await db.execute(stmt)
    uploads = res.scalars().all()
    enriched = []
    for u in uploads:
        item = schemas.UploadRecordResponse.model_validate(u, from_attributes=True)
        item.download_url = str(request.url_for("download_file", download_token=token_row.download_token, upload_id=u.id))
        if not settings.allow_public_downloads:
            item.download_url += f"?api_key={settings.admin_api_key}"
        item.upload_url = str(request.url_for("tus_head", upload_id=u.id))
        item.info_url = str(request.url_for("get_file_info", download_token=token_row.download_token, upload_id=u.id))
        enriched.append(item)
    return enriched


@router.get("/{token_value}/info", response_model=schemas.TokenPublicInfo, name="get_public_token_info")
@router.get("/{token_value}/info/", response_model=schemas.TokenPublicInfo, name="token_info_trailing_slash")
async def token_info(request: Request, token_value: str, db: Annotated[AsyncSession, Depends(get_db)]):
    stmt = select(models.UploadToken).where(models.UploadToken.token == token_value)
    res = await db.execute(stmt)
    token_row = res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=404, detail="Token not found")

    now = datetime.now(UTC)
    expires_at = token_row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if token_row.disabled:
        raise HTTPException(status_code=403, detail="Token is disabled")
    if expires_at < now:
        raise HTTPException(status_code=403, detail="Token has expired")
    uploads_stmt = (
        select(models.UploadRecord).where(models.UploadRecord.token_id == token_row.id).order_by(models.UploadRecord.created_at.desc())
    )
    uploads_res = await db.execute(uploads_stmt)
    uploads = uploads_res.scalars().all()

    enriched_uploads = []
    for u in uploads:
        item = schemas.UploadRecordResponse.model_validate(u, from_attributes=True)
        item.upload_url = str(request.url_for("tus_head", upload_id=u.id))
        item.download_url = str(request.url_for("download_file", download_token=token_row.download_token, upload_id=u.id))
        item.info_url = str(request.url_for("get_file_info", download_token=token_row.download_token, upload_id=u.id))
        enriched_uploads.append(item)

    return schemas.TokenPublicInfo(
        token=token_row.token,
        download_token=token_row.download_token,
        remaining_uploads=token_row.remaining_uploads,
        max_uploads=token_row.max_uploads,
        max_size_bytes=token_row.max_size_bytes,
        max_chunk_bytes=settings.max_chunk_bytes,
        allowed_mime=token_row.allowed_mime,
        expires_at=token_row.expires_at,
        disabled=token_row.disabled,
        allow_public_downloads=settings.allow_public_downloads,
        uploads=enriched_uploads,
    )


@router.get("/{download_token}/uploads/{upload_id}", name="get_file_info", summary="Get upload file info")
@router.get("/{download_token}/uploads/{upload_id}/", name="get_file_info_trailing_slash")
async def get_file_info(
    request: Request,
    download_token: str,
    upload_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(optional_admin_check)],
):
    token_stmt = select(models.UploadToken).where(models.UploadToken.download_token == download_token)
    token_res = await db.execute(token_stmt)
    token_row = token_res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=404, detail="Download token not found")

    upload_stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id, models.UploadRecord.token_id == token_row.id)
    upload_res = await db.execute(upload_stmt)
    record = upload_res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    if record.status != "completed":
        raise HTTPException(status_code=409, detail="Upload not yet completed")

    path = Path(record.storage_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")

    # Return JSON metadata about the file
    item = schemas.UploadRecordResponse.model_validate(record, from_attributes=True)
    item.download_url = str(request.url_for("download_file", download_token=download_token, upload_id=upload_id))
    if not settings.allow_public_downloads:
        item.download_url += f"?api_key={settings.admin_api_key}"

    item.upload_url = str(request.url_for("tus_head", upload_id=upload_id))
    item.info_url = str(request.url_for("get_file_info", download_token=download_token, upload_id=upload_id))
    return item


@router.get("/{download_token}/uploads/{upload_id}/download", name="download_file")
@router.get("/{download_token}/uploads/{upload_id}/download/", name="download_file_trailing_slash")
async def download_file(
    download_token: str,
    upload_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[bool, Depends(optional_admin_check)],
):
    token_stmt = select(models.UploadToken).where(models.UploadToken.download_token == download_token)
    token_res = await db.execute(token_stmt)
    token_row = token_res.scalar_one_or_none()
    if not token_row:
        raise HTTPException(status_code=404, detail="Download token not found")

    upload_stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id, models.UploadRecord.token_id == token_row.id)
    upload_res = await db.execute(upload_stmt)
    record = upload_res.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Upload not found")
    if record.status != "completed":
        raise HTTPException(status_code=409, detail="Upload not yet completed")

    path = Path(record.storage_path or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing")

    return FileResponse(path, filename=record.filename or path.name, media_type=record.mimetype or "application/octet-stream")
