from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class UploadToken(Base):
    __tablename__: str = "upload_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    download_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    max_uploads: Mapped[int] = mapped_column(Integer, nullable=False)
    max_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    uploads_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allowed_mime: Mapped[list | None] = mapped_column("allowed_mime", JSON, nullable=True)
    disabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    uploads: Mapped[list["UploadRecord"]] = relationship("UploadRecord", back_populates="token", cascade="all, delete-orphan")

    @property
    def remaining_uploads(self) -> int:
        return max(0, self.max_uploads - self.uploads_used)


class UploadRecord(Base):
    __tablename__: str = "uploads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_id: Mapped[int] = mapped_column(Integer, ForeignKey("upload_tokens.id"), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(255))
    ext: Mapped[str | None] = mapped_column(String(32))
    mimetype: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    meta_data: Mapped[dict] = mapped_column("meta_data", JSON, nullable=False, default=dict)
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    upload_length: Mapped[int | None] = mapped_column(BigInteger)
    upload_offset: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    token: Mapped[UploadToken] = relationship("UploadToken", back_populates="uploads")
