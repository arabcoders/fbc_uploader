from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app import models, utils
from backend.app.config import settings

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
    is_directly_embeddable = utils.is_directly_embeddable_video(first_media.mimetype, ffprobe_data) if is_video else False
    media_url = str(request.url_for("stream_file", download_token=token_row.download_token, upload_id=first_media.public_id))
    preview_url = None
    used_generated_preview = False
    allow_direct_video_embed = True
    if is_video and settings.embed_preview_clip_seconds > 0 and settings.embed_preview_min_size_bytes > 0:
        candidate_preview_url = str(
            request.url_for("get_file_preview", download_token=token_row.download_token, upload_id=first_media.public_id)
        )
        preview_path = utils.get_preview_path(first_media.storage_path or "") if first_media.storage_path else None
        should_use_preview = not is_directly_embeddable or utils.should_generate_video_preview(
            first_media.size_bytes,
            min_size_bytes=settings.embed_preview_min_size_bytes,
        )
        if should_use_preview and preview_path and preview_path.is_file() and preview_path.stat().st_size > 0:
            preview_url = candidate_preview_url

    embed_media_url = preview_url if preview_url and not user else media_url
    if preview_url and embed_media_url == preview_url:
        used_generated_preview = True
        mime_type = utils.PREVIEW_MEDIA_TYPE
    elif is_video and not user and not is_directly_embeddable:
        allow_direct_video_embed = False

    description: str = f"{len(uploads)} file(s) shared" if len(uploads) > 1 else "Shared file"
    if used_generated_preview:
        description: str = "A video preview. Click to watch the full-length video."

    return templates.TemplateResponse(
        request=request,
        name="share_preview.html",
        context={
            "request": request,
            "title": first_media.filename or "Shared Media",
            "description": description,
            "uses_preview_clip": used_generated_preview,
            "og_type": "video.other" if is_video else "music.song",
            "share_url": str(request.url_for("share_page", token=token_row.download_token)),
            "media_url": media_url,
            "embed_media_url": embed_media_url,
            "download_url": str(request.url_for("download_file", download_token=token_row.download_token, upload_id=first_media.public_id)),
            "thumbnail_url": str(
                request.url_for("get_file_thumbnail", download_token=token_row.download_token, upload_id=first_media.public_id)
            ),
            "mime_type": mime_type,
            "is_video": is_video and (user or allow_direct_video_embed),
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
