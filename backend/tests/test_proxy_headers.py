from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from backend.app.proxy_headers import TrustedProxyHeadersMiddleware
from backend.main import main


def create_test_app(trusted_hosts: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(TrustedProxyHeadersMiddleware, trusted_hosts=trusted_hosts)

    @app.get("/inspect")
    async def inspect_request(request: Request) -> dict[str, object]:
        return {
            "client": list(request.client) if request.client else None,
            "base_url": str(request.base_url),
            "url": str(request.url),
            "host": request.headers.get("host"),
        }

    return app


@pytest.mark.asyncio
async def test_proxy_headers_trusts_only_configured_proxy():
    app = create_test_app("172.23.0.0/16")
    transport = ASGITransport(app=app, client=("172.23.0.1", 47548))

    async with AsyncClient(transport=transport, base_url="http://internal") as client:
        response = await client.get(
            "/inspect?download=1",
            headers={
                "X-Forwarded-For": "198.51.100.9",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "files.example.com",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "client": ["198.51.100.9", 0],
        "base_url": "https://files.example.com/",
        "url": "https://files.example.com/inspect?download=1",
        "host": "files.example.com",
    }


@pytest.mark.asyncio
async def test_proxy_headers_ignore_untrusted_client():
    app = create_test_app("172.23.0.0/16")
    transport = ASGITransport(app=app, client=("198.51.100.20", 47548))

    async with AsyncClient(transport=transport, base_url="http://internal") as client:
        response = await client.get(
            "/inspect",
            headers={
                "X-Forwarded-For": "203.0.113.50",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "files.example.com",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "client": ["198.51.100.20", 47548],
        "base_url": "http://internal/",
        "url": "http://internal/inspect",
        "host": "internal",
    }


@pytest.mark.asyncio
async def test_proxy_headers_preserve_forwarded_port():
    app = create_test_app("172.23.0.0/16")
    transport = ASGITransport(app=app, client=("172.23.0.1", 47548))

    async with AsyncClient(transport=transport, base_url="http://internal") as client:
        response = await client.get(
            "/inspect",
            headers={
                "X-Forwarded-For": "198.51.100.9",
                "X-Forwarded-Proto": "https",
                "X-Forwarded-Host": "files.example.com:8443",
            },
        )

    assert response.status_code == 200
    assert response.json()["base_url"] == "https://files.example.com:8443/"
    assert response.json()["host"] == "files.example.com:8443"


def test_server_entrypoint_disables_uvicorn_proxy_headers_by_default(monkeypatch):
    monkeypatch.setenv("FBC_DEV_MODE", "0")

    with patch("backend.main.uvicorn.run") as run_mock:
        main()

    run_mock.assert_called_once_with(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        proxy_headers=False,
    )
