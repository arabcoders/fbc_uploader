import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from backend.app import version

from . import routers
from .cleanup import start_cleanup_loop
from .config import settings
from .db import engine
from .migrate import run_migrations


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    Path(settings.config_path).mkdir(parents=True, exist_ok=True)

    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Application lifespan context manager.

        Args:
            app (FastAPI): The FastAPI application instance.

        """
        if not settings.skip_migrations:
            await run_in_threadpool(run_migrations)

        if not settings.skip_cleanup:
            app.state.cleanup_task = asyncio.create_task(start_cleanup_loop(), name="cleanup_loop")

        yield

        if not settings.skip_cleanup:
            task: asyncio.Task | None = getattr(app.state, "cleanup_task", None)
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

        await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        version=version.APP_VERSION,
        redirect_slashes=True,
        docs_url="/docs" if bool(os.getenv("FBC_DEV_MODE", "0") == "1") else None,
        redoc_url=None,
    )

    if settings.trust_proxy_headers:

        @app.middleware("http")
        async def proxy_headers_middleware(request: Request, call_next):
            """
            Middleware to trust proxy headers for scheme and host.

            Args:
                request (Request): The incoming HTTP request.
                call_next: Function to call the next middleware or route handler.

            Returns:
                Response: The HTTP response.

            """
            if forwarded_proto := request.headers.get("X-Forwarded-Proto"):
                request.scope["scheme"] = forwarded_proto

            if forwarded_host := request.headers.get("X-Forwarded-Host"):
                request.scope["server"] = (forwarded_host.split(":")[0], 443 if forwarded_proto == "https" else 80)

            return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "Upload-Offset",
            "Upload-Length",
            "Tus-Resumable",
            "Tus-Version",
            "Tus-Extension",
            "Upload-Metadata",
            "Upload-Defer-Length",
            "Upload-Concat",
            "Location",
        ],
    )

    @app.middleware("http")
    async def log_exceptions(request: Request, call_next):
        """
        Middleware to log unhandled exceptions.

        Args:
            request (Request): The incoming HTTP request.
            call_next: Function to call the next middleware or route handler.

        Returns:
            Response: The HTTP response.

        """
        try:
            return await call_next(request)
        except Exception as exc:
            logging.exception("Unhandled exception", exc_info=exc)
            return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal Server Error"})

    @app.get("/api/health", name="health")
    def health() -> dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    @app.get("/api/version", name="version")
    def app_version() -> dict[str, str]:
        """Get application version information."""
        return {
            "version": version.APP_VERSION,
            "commit_sha": version.APP_COMMIT_SHA,
            "build_date": version.APP_BUILD_DATE,
            "branch": version.APP_BRANCH,
        }

    for _route in routers.__all__:
        app.include_router(getattr(routers, _route).router)

    frontend_dir: Path = Path(settings.frontend_export_path).resolve()

    @app.get("/f/{token}", name="share_page")
    @app.get("/f/{token}/")
    async def share_page(token: str, request: Request, user_agent: Annotated[str | None, Header()] = None):
        """Handle /f/{token} with bot detection for embed preview."""
        from sqlalchemy import select

        from backend.app import models, utils
        from backend.app.db import get_db

        user_agent_lower: str = (user_agent or "").lower()
        is_bot = any(bot in user_agent_lower for bot in ["discordbot", "twitterbot", "slackbot", "facebookexternalhit", "whatsapp"])

        if is_bot and settings.allow_public_downloads:
            async for db in get_db():
                stmt = select(models.UploadToken).where((models.UploadToken.token == token) | (models.UploadToken.download_token == token))
                result = await db.execute(stmt)
                token_row = result.scalar_one_or_none()

                if token_row:
                    uploads_stmt = (
                        select(models.UploadRecord)
                        .where(models.UploadRecord.token_id == token_row.id, models.UploadRecord.status == "completed")
                        .order_by(models.UploadRecord.created_at.desc())
                    )
                    uploads_result = await db.execute(uploads_stmt)
                    uploads = uploads_result.scalars().all()

                    media_files = [u for u in uploads if u.mimetype and utils.is_multimedia(u.mimetype)]

                    if media_files:
                        first_media = media_files[0]

                        is_video = first_media.mimetype.startswith("video/")
                        ffprobe_data = None
                        if first_media.meta_data and isinstance(first_media.meta_data, dict):
                            ffprobe_data = first_media.meta_data.get("ffprobe")

                        video_metadata = utils.extract_video_metadata(ffprobe_data)

                        other_files = [
                            {
                                "name": u.filename or "Unknown",
                                "size": utils.format_file_size(u.size_bytes) if u.size_bytes else "Unknown",
                            }
                            for u in uploads
                            if u.public_id != first_media.public_id
                        ]

                        media_url = str(
                            request.url_for("download_file", download_token=token_row.download_token, upload_id=first_media.public_id)
                        )
                        share_url = str(request.url_for("share_page", token=token))

                        is_video = first_media.mimetype.startswith("video/")
                        is_audio = first_media.mimetype.startswith("audio/")

                        context = {
                            "request": request,
                            "title": first_media.filename or "Shared Media",
                            "description": f"{len(uploads)} file(s) shared" if len(uploads) > 1 else "Shared file",
                            "og_type": "video.other" if is_video else "music.song",
                            "share_url": share_url,
                            "media_url": media_url,
                            "mime_type": first_media.mimetype,
                            "is_video": is_video,
                            "is_audio": is_audio,
                            "width": video_metadata.get("width"),
                            "height": video_metadata.get("height"),
                            "duration": video_metadata.get("duration"),
                            "duration_formatted": utils.format_duration(video_metadata["duration"])
                            if video_metadata.get("duration")
                            else None,
                            "file_size": utils.format_file_size(first_media.size_bytes) if first_media.size_bytes else None,
                            "other_files": other_files,
                        }

                        return templates.TemplateResponse(
                            request=request,
                            name="share_preview.html",
                            context=context,
                            status_code=status.HTTP_200_OK,
                        )

        if frontend_dir.exists():
            index_file = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file, status_code=status.HTTP_200_OK)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @app.get("/{full_path:path}", name="static_frontend")
    async def frontend(full_path: str) -> FileResponse:
        """
        Serve static frontend files.

        Args:
            full_path (str): The requested file path.

        Returns:
            FileResponse: The response containing the requested file.

        """
        if full_path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if not frontend_dir.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        if not full_path or "/" == full_path:
            index_file: Path = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file, status_code=status.HTTP_200_OK)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        requested_file: Path = frontend_dir / full_path
        if requested_file.is_file():
            return FileResponse(requested_file, status_code=status.HTTP_200_OK)

        index_file: Path = frontend_dir / "index.html"
        if index_file.exists():
            return FileResponse(index_file, status_code=status.HTTP_200_OK)

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return app


app: FastAPI = create_app()
