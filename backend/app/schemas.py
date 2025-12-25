from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TokenCreate(BaseModel):
    max_uploads: int = Field(1, ge=1)
    max_size_bytes: int = Field(..., gt=0)
    expiry_datetime: datetime | None = Field(default=None)
    allowed_mime: list[str] | None = Field(
        default=None,
        description="List of allowed MIME patterns, e.g. ['application/pdf', 'video/*']",
    )


class TokenUpdate(BaseModel):
    max_uploads: int | None = Field(default=None, ge=1)
    max_size_bytes: int | None = Field(default=None, gt=0)
    expiry_datetime: datetime | None = Field(default=None)
    extend_hours: int | None = Field(default=None, ge=1, description="Hours to add to the current expiry")
    allowed_mime: list[str] | None = Field(
        default=None,
        description="List of allowed MIME patterns, e.g. ['application/pdf', 'video/*']",
    )
    disabled: bool | None = None


class TokenResponse(BaseModel):
    token: str
    download_token: str
    upload_url: str
    expires_at: datetime
    max_uploads: int
    max_size_bytes: int
    allowed_mime: list[str] | None = None


class TokenInfo(BaseModel):
    token: str
    download_token: str
    expires_at: datetime
    uploads_used: int
    max_uploads: int
    remaining_uploads: int
    max_size_bytes: int
    allowed_mime: list[str] | None = None
    disabled: bool

    model_config = ConfigDict(from_attributes=True)


class UploadRecordResponse(BaseModel):
    id: int
    filename: str | None
    ext: str | None
    mimetype: str | None
    size_bytes: int | None
    meta_data: dict[str, Any] = Field(default_factory=dict)
    upload_length: int | None
    upload_offset: int
    status: str
    created_at: datetime
    completed_at: datetime | None
    download_url: str | None = None
    upload_url: str | None = None
    info_url: str | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TokenPublicInfo(BaseModel):
    token: str
    download_token: str
    remaining_uploads: int
    max_uploads: int
    max_size_bytes: int
    max_chunk_bytes: int
    allowed_mime: list[str] | None = None
    expires_at: datetime
    disabled: bool
    allow_public_downloads: bool
    uploads: list[UploadRecordResponse]


class TokenAdmin(TokenInfo):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UploadRequest(BaseModel):
    meta_data: dict[str, Any]
    filename: str | None = None
    filetype: str | None = None
    size_bytes: int | None = Field(None, gt=0)
