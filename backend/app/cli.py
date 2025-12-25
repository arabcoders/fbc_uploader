import asyncio
import json
import sys
from pathlib import Path

import httpx
import typer

if __package__ is None:
    sys.path.append(str(Path(__file__).resolve().parents[2]))
    __package__ = "backend.app"

from backend.app import version
from backend.app.config import settings

app = typer.Typer(help=f"FBC Uploader {version.APP_VERSION} CLI", no_args_is_help=True)


def _default_base_url() -> str:
    return settings.public_base_url or "http://127.0.0.1:8000"


MULTIPLIERS: dict[str, int] = {
    "k": 1024,
    "m": 1024**2,
    "g": 1024**3,
    "t": 1024**4,
}


def parse_size(text: str) -> int:
    """Parse human-readable sizes: 100, 10M, 1G, 500k."""
    s = text.strip().lower()
    if s[-1].isalpha():
        num = float(s[:-1])
        unit = s[-1]
        if unit not in MULTIPLIERS:
            msg = "Unknown size suffix; use K/M/G/T"
            raise typer.BadParameter(msg)
        return int(num * MULTIPLIERS[unit])
    return int(s)


@app.command("create-token")
def create_token(
    max_uploads: int = typer.Option(1, help="Max number of uploads"),
    max_size: str = typer.Option("1G", "--max-size", help="Max size per upload (e.g., 1G, 500M)"),
    allowed_mime: str = typer.Option(
        None,
        "--allowed-mime",
        help="Comma-separated MIME patterns (e.g., application/pdf,video/*). Omit to allow any.",
    ),
    admin_key: str | None = typer.Option(None, envvar="FBC_ADMIN_API_KEY", help="Admin API key"),
    base_url: str = typer.Option(None, envvar="FBC_PUBLIC_BASE_URL", help="API base URL"),
) -> None:
    """Create upload token."""
    key = admin_key or settings.admin_api_key
    url_base = base_url or _default_base_url()
    max_size_bytes = parse_size(max_size)
    mime_list = [m.strip() for m in allowed_mime.split(",")] if allowed_mime else None
    payload = {
        "max_uploads": max_uploads,
        "max_size_bytes": max_size_bytes,
        "allowed_mime": mime_list,
    }

    async def _run():
        async with httpx.AsyncClient(base_url=url_base) as client:
            r = await client.post(
                "/api/tokens/",
                json=payload,
                headers={"Authorization": f"Bearer {key}"},
                timeout=30,
            )
            r.raise_for_status()
            return r.json()

    typer.echo(json.dumps(asyncio.run(_run()), indent=2))


@app.command("view-token")
def view_token(
    token: str = typer.Argument(..., help="Token to inspect"),
    admin_key: str | None = typer.Option(None, envvar="FBC_ADMIN_API_KEY", help="Admin API key"),
    base_url: str = typer.Option(None, envvar="FBC_PUBLIC_BASE_URL", help="API base URL"),
) -> None:
    """View upload token."""
    key = admin_key or settings.admin_api_key
    url_base = base_url or _default_base_url()

    async def _run():
        try:
            async with httpx.AsyncClient(base_url=url_base) as client:
                r = await client.get(
                    f"/api/tokens/{token}/uploads",
                    headers={"Authorization": f"Bearer {key}"},
                    timeout=30,
                )
                r.raise_for_status()
                return r.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                typer.echo(f"Token '{token}' not found", err=True)
                raise typer.Exit(code=1) from e
            raise

    typer.echo(json.dumps(asyncio.run(_run()), indent=2))


@app.command("view-api-key")
def view_api_key() -> None:
    """View the current admin API key."""
    typer.echo(settings.admin_api_key)


if __name__ == "__main__":
    app()
