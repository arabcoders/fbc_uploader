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

from backend.app import version

from . import routers
from .cleanup import start_cleanup_loop
from .config import settings
from .db import engine
from .migrate import run_migrations
from .postprocessing import ProcessingQueue


def create_app() -> FastAPI:
    from .embed_preview import (
        get_token,
        is_embed_bot,
        render_embed_preview,
    )

    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    Path(settings.config_path).mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """
        Application lifespan context manager.

        Args:
            app (FastAPI): The FastAPI application instance.

        """
        if not settings.skip_migrations:
            await run_in_threadpool(run_migrations)

        queue = ProcessingQueue()
        queue.start_worker()
        app.state.processing_queue = queue

        if not settings.skip_cleanup:
            app.state.cleanup_task = asyncio.create_task(start_cleanup_loop(), name="cleanup_loop")

        yield

        await queue.stop_worker()

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

    def serve_static():
        if frontend_dir.exists():
            index_file = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file, status_code=status.HTTP_200_OK)

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    @app.get("/e/{token}", name="token_embed")
    @app.get("/e/{token}/")
    async def token_embed(request: Request, token: str):
        """Render a static embed preview page."""
        if not settings.allow_public_downloads:
            return serve_static()

        from backend.app.db import get_db

        async for db in get_db():
            if not (token_row := await get_token(db, token)):
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

        return await render_embed_preview(request, db, token_row, user=True)

    @app.get("/f/{token}", name="share_page")
    @app.get("/f/{token}/")
    async def share_page(token: str, request: Request, user_agent: Annotated[str | None, Header()] = None):
        """Handle /f/{token} with bot detection for embed preview."""
        from backend.app.db import get_db

        if is_embed_bot(user_agent) and settings.allow_public_downloads:
            async for db in get_db():
                if token_row := await get_token(db, token):
                    return await render_embed_preview(request, db, token_row)

        return serve_static()

    @app.get("/t/{token}", name="upload_page")
    @app.get("/t/{token}/")
    async def upload_page(token: str, request: Request, user_agent: Annotated[str | None, Header()] = None):
        """Handle /t/{token} with bot detection for embed preview."""
        if not frontend_dir.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        index_file = frontend_dir / "index.html"
        if not index_file.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

        return FileResponse(index_file, status_code=status.HTTP_200_OK)

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
