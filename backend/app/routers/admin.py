from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models import UploadRecord
from backend.app.security import verify_admin

if TYPE_CHECKING:
    from sqlalchemy.engine.result import Result
    from sqlalchemy.sql.selectable import Select

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/validate", name="validate_api_key")
async def validate_api_key(_: Annotated[bool, Depends(verify_admin)]) -> dict[str, bool]:
    """Validate the provided admin API key."""
    return {"status": True}


@router.delete("/uploads/{upload_id}", name="delete_upload")
async def delete_upload(
    upload_id: str,
    _: Annotated[bool, Depends(verify_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """
    Delete an upload record and its associated file.

    Args:
        upload_id (str): The public ID of the upload to delete.
        db (AsyncSession): The database session.

    Returns:
        dict[str, str]: A confirmation message with the deleted upload ID.

    """
    stmt: Select[tuple[UploadRecord]] = select(UploadRecord).where(UploadRecord.public_id == upload_id)
    res: Result[tuple[UploadRecord]] = await db.execute(stmt)

    if not (upload := res.scalar_one_or_none()):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")

    if upload.storage_path:
        file_path = Path(upload.storage_path)
        if file_path.exists():
            file_path.unlink()

    await db.delete(upload)
    await db.commit()

    return {"status": "deleted", "public_id": upload_id}
