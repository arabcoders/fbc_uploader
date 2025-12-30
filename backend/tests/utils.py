"""Test utility functions for common test operations."""

from typing import Any

from fastapi import status
from httpx import AsyncClient

from backend.app.config import settings
from backend.app.main import app


async def create_token(
    client: AsyncClient,
    max_uploads: int = 5,
    max_size_bytes: int = 10_000_000,
    allowed_mime: list[str] | None = None,
    **overrides: Any,
) -> dict:
    """
    Create a token and return the response JSON.

    Args:
        client: AsyncClient instance
        max_uploads: Maximum number of uploads allowed
        max_size_bytes: Maximum file size in bytes
        allowed_mime: List of allowed MIME types
        **overrides: Additional fields to override in the payload

    Returns:
        Token response JSON containing token, download_token, etc.

    """
    payload = {
        "max_uploads": max_uploads,
        "max_size_bytes": max_size_bytes,
    }
    if allowed_mime is not None:
        payload["allowed_mime"] = allowed_mime
    payload.update(overrides)

    resp = await client.post(
        app.url_path_for("create_token"),
        json=payload,
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp.status_code == status.HTTP_201_CREATED
    return resp.json()


async def initiate_upload(
    client: AsyncClient,
    token: str,
    filename: str = "test.txt",
    size_bytes: int = 100,
    filetype: str = "text/plain",
    meta_data: dict | None = None,
    **overrides: Any,
) -> dict:
    """
    Initiate an upload and return the response JSON.

    Args:
        client: AsyncClient instance
        token: Upload token
        filename: Name of the file to upload
        size_bytes: Size of the file in bytes
        filetype: MIME type of the file
        meta_data: Metadata dictionary
        **overrides: Additional fields to override in the payload

    Returns:
        Upload initiation response JSON containing upload_id, etc.

    """
    payload = {
        "filename": filename,
        "size_bytes": size_bytes,
        "filetype": filetype,
        "meta_data": meta_data or {},
    }
    payload.update(overrides)

    resp = await client.post(
        app.url_path_for("initiate_upload"),
        params={"token": token},
        json=payload,
    )
    return resp.json() if resp.status_code == status.HTTP_201_CREATED else {}


async def upload_file_via_tus(
    client: AsyncClient,
    upload_id: int,
    content: bytes,
    offset: int = 0,
) -> int:
    """
    Upload file content via TUS protocol.

    Args:
        client: AsyncClient instance
        upload_id: Upload record ID
        content: File content bytes
        offset: Upload offset (default 0)

    Returns:
        HTTP status code of the upload response

    """
    resp = await client.patch(
        app.url_path_for("tus_patch", upload_id=upload_id),
        content=content,
        headers={
            "Content-Type": "application/offset+octet-stream",
            "Upload-Offset": str(offset),
            "Content-Length": str(len(content)),
        },
    )
    return resp.status_code


async def get_token_info(
    client: AsyncClient,
    token: str,
) -> dict:
    """
    Get public token info.

    Args:
        client: AsyncClient instance
        token: Upload token

    Returns:
        Token info response JSON

    """
    resp = await client.get(app.url_path_for("get_token", token_value=token))
    return resp.json() if resp.status_code == status.HTTP_200_OK else {}


async def tus_head(
    client: AsyncClient,
    upload_id: int,
) -> tuple[int, dict[str, str]]:
    """
    Perform TUS HEAD request to check upload status.

    Args:
        client: AsyncClient instance
        upload_id: Upload record ID

    Returns:
        Tuple of (status_code, headers)

    """
    resp = await client.head(app.url_path_for("tus_head", upload_id=upload_id))
    return resp.status_code, dict(resp.headers)


async def cancel_upload(
    client: AsyncClient,
    upload_id: int,
    token: str,
) -> dict:
    """
    Cancel an upload.

    Args:
        client: AsyncClient instance
        upload_id: Upload record ID
        token: Upload token

    Returns:
        Cancel response JSON

    """
    resp = await client.delete(
        app.url_path_for("cancel_upload", upload_id=upload_id),
        params={"token": token},
    )
    return resp.json() if resp.status_code == status.HTTP_200_OK else {}


async def delete_upload_admin(
    client: AsyncClient,
    upload_id: int,
) -> int:
    """
    Delete an upload as admin.

    Args:
        client: AsyncClient instance
        upload_id: Upload record ID

    Returns:
        HTTP status code

    """
    resp = await client.delete(
        app.url_path_for("delete_upload", upload_id=upload_id),
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    return resp.status_code


async def validate_metadata(
    client: AsyncClient,
    metadata: dict,
) -> tuple[int, dict]:
    """
    Validate metadata against schema.

    Args:
        client: AsyncClient instance
        metadata: Metadata to validate

    Returns:
        Tuple of (status_code, response_json)

    """
    resp = await client.post(
        app.url_path_for("metadata_schema_validate"),
        json={"metadata": metadata},
    )
    return resp.status_code, resp.json()
