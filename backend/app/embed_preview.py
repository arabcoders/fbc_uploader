from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import models, utils

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

EMBED_BOT_SIGNATURES: tuple[str, ...] = (
    "discordbot",
    "twitterbot",
    "slackbot",
    "facebookexternalhit",
    "whatsapp",
)


def is_embed_bot(user_agent: str | None) -> bool:
    user_agent_lower = (user_agent or "").lower()
    return any(bot in user_agent_lower for bot in EMBED_BOT_SIGNATURES)


async def get_token(db: AsyncSession, token_value: str) -> models.UploadToken | None:
    stmt = select(models.UploadToken).where((models.UploadToken.token == token_value) | (models.UploadToken.download_token == token_value))
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def render_embed_preview(request: Request, db: AsyncSession, token_row: models.UploadToken, user: bool = False):
    uploads_stmt = (
        select(models.UploadRecord)
        .where(models.UploadRecord.token_id == token_row.id, models.UploadRecord.status == "completed")
        .order_by(models.UploadRecord.created_at.desc())
    )
    uploads_result = await db.execute(uploads_stmt)
    uploads: list[models.UploadRecord] = list(uploads_result.scalars().all())

    media_files = [upload for upload in uploads if upload.mimetype and utils.is_multimedia(upload.mimetype)]
    if not media_files:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No multimedia uploads found")

    first_media = media_files[0]
    ffprobe_data = first_media.meta_data.get("ffprobe") if isinstance(first_media.meta_data, dict) else None
    video_metadata = utils.extract_video_metadata(ffprobe_data)
    mime_type = first_media.mimetype or "application/octet-stream"
    is_video = mime_type.startswith("video/")
    is_audio = mime_type.startswith("audio/")

    return templates.TemplateResponse(
        request=request,
        name="share_preview.html",
        context={
            "request": request,
            "title": first_media.filename or "Shared Media",
            "description": f"{len(uploads)} file(s) shared" if len(uploads) > 1 else "Shared file",
            "og_type": "video.other" if is_video else "music.song",
            "share_url": str(request.url_for("share_page", token=token_row.download_token)),
            "media_url": str(request.url_for("download_file", download_token=token_row.download_token, upload_id=first_media.public_id)),
            "mime_type": mime_type,
            "is_video": is_video,
            "is_audio": is_audio,
            "width": video_metadata.get("width"),
            "height": video_metadata.get("height"),
            "duration": video_metadata.get("duration"),
            "duration_formatted": utils.format_duration(video_metadata["duration"]) if video_metadata.get("duration") else None,
            "file_size": utils.format_file_size(first_media.size_bytes) if first_media.size_bytes else None,
            "other_files": [
                {
                    "name": upload.filename or "Unknown",
                    "size": utils.format_file_size(upload.size_bytes) if upload.size_bytes else "Unknown",
                }
                for upload in uploads
                if upload.public_id != first_media.public_id
            ],
            "is_user": user,
        },
        status_code=status.HTTP_200_OK,
    )
