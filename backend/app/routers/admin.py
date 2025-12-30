from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models import UploadRecord
from backend.app.security import verify_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/validate", name="validate_api_key")
async def validate_api_key(_: Annotated[bool, Depends(verify_admin)]):
    """Validate the provided admin API key."""
    return {"status": True}


@router.delete("/uploads/{upload_id}", name="delete_upload")
async def delete_upload(
    upload_id: str,
    _: Annotated[bool, Depends(verify_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete an upload record and its associated file."""
    from pathlib import Path

    stmt = select(UploadRecord).where(UploadRecord.public_id == upload_id)
    res = await db.execute(stmt)
    upload = res.scalar_one_or_none()

    if not upload:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    if upload.storage_path:
        file_path = Path(upload.storage_path)
        if file_path.exists():
            file_path.unlink()

    await db.delete(upload)
    await db.commit()

    return {"status": "deleted", "public_id": upload_id}
