import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from backend.app import version

from . import routers
from .cleanup import start_cleanup_loop
from .config import settings
from .db import engine
from .migrate import run_migrations


def _ensure_storage() -> None:
    Path(settings.storage_path).mkdir(parents=True, exist_ok=True)
    Path(settings.config_path).mkdir(parents=True, exist_ok=True)


def create_app() -> FastAPI:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s [%(name)s] %(message)s")

    _ensure_storage()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if not settings.skip_migrations:
            await run_in_threadpool(run_migrations)
        if not settings.skip_cleanup:
            app.state.cleanup_task = asyncio.create_task(start_cleanup_loop(), name="cleanup_loop")
        yield
        if not settings.skip_cleanup:
            task = getattr(app.state, "cleanup_task", None)
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
        docs_url=None,
        redoc_url=None,
    )

    if settings.trust_proxy_headers:

        @app.middleware("http")
        async def proxy_headers_middleware(request: Request, call_next):
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
        try:
            return await call_next(request)
        except Exception as exc:
            logging.exception("Unhandled exception", exc_info=exc)
            return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    for _route in routers.__all__:
        app.include_router(getattr(routers, _route).router)

    frontend_dir: Path = Path(settings.frontend_export_path).resolve()
    if frontend_dir.exists():

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            if full_path.startswith("api/"):
                raise HTTPException(status_code=404)

            if not full_path or full_path == "/":
                index_file = frontend_dir / "index.html"
                if index_file.exists():
                    return FileResponse(index_file, status_code=200)
                raise HTTPException(status_code=404)

            requested_file = frontend_dir / full_path
            if requested_file.is_file():
                return FileResponse(requested_file, status_code=200)

            index_file = frontend_dir / "index.html"
            if index_file.exists():
                return FileResponse(index_file, status_code=200)
            raise HTTPException(status_code=404)

    return app


app = create_app()
