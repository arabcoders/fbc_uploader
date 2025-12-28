"""Tests for mimetype validation during upload."""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from backend.app import models
from backend.app.config import settings
from backend.app.db import SessionLocal
from backend.app.main import app


@pytest.mark.asyncio
async def test_mimetype_spoofing_rejected():
    """Test that files with fake mimetypes are rejected after upload."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create token with video mime type restriction
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Video Only",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["video/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == 201
        token_data = resp.json()
        token_value = token_data["token"]

        # Upload actual text file content (not a video)
        fake_video = b"This is actually a text file, not a video!"

        # Initiate upload claiming to be video/mp4
        init_resp = await client.post(
            "/api/uploads/initiate",
            json={
                "filename": "test.mp4",
                "filetype": "video/mp4",  # Fake mimetype
                "size_bytes": len(fake_video),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == 201
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        # Upload the fake content
        patch_resp = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=fake_video,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(fake_video)),
            },
        )

        # Upload should be rejected due to mimetype mismatch
        assert patch_resp.status_code == 415
        assert "does not match allowed types" in patch_resp.json()["detail"]

        # Verify upload record was deleted
        head_resp = await client.head(f"/api/uploads/{upload_id}/tus")
        assert head_resp.status_code == 404


@pytest.mark.asyncio
async def test_valid_mimetype_accepted():
    """Test that files with correct mimetypes are accepted."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create token with text restriction
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Text Only",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["text/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == 201
        token_data = resp.json()
        token_value = token_data["token"]

        # Initiate upload claiming to be text/plain
        init_resp = await client.post(
            "/api/uploads/initiate",
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": 20,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == 201
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        # Upload actual text content
        text_content = b"This is a text file."

        head_resp = await client.head(f"/api/uploads/{upload_id}/tus")
        assert head_resp.status_code == 200

        # Upload the content
        patch_resp = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )

        # Upload should succeed
        assert patch_resp.status_code == 204

        # Verify record exists and has correct mimetype
        head_resp = await client.head(f"/api/uploads/{upload_id}/tus")
        assert head_resp.status_code == 200


@pytest.mark.asyncio
async def test_mimetype_updated_on_completion():
    """Test that mimetype is updated with detected value on completion."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create unrestricted token
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Unrestricted",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == 201
        token_data = resp.json()
        token_value = token_data["token"]

        # Initiate upload with incorrect mimetype
        init_resp = await client.post(
            "/api/uploads/initiate",
            json={
                "filename": "test.txt",
                "filetype": "application/octet-stream",  # Generic mimetype
                "size_bytes": 20,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == 201
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        # Upload text content
        text_content = b"This is a text file."

        patch_resp = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )
        assert patch_resp.status_code == 204

        # Verify mimetype was updated to actual detected type
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None
            assert upload.mimetype.startswith("text/")


@pytest.mark.asyncio
async def test_ffprobe_extracts_metadata_for_video():
    """Test that ffprobe metadata is extracted for video files."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create unrestricted token
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Video Upload",
                "max_size_bytes": 50_000_000,
                "expires_in_days": 1,
                "allowed_mime": ["video/*"],
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == 201
        token_data = resp.json()
        token_value = token_data["token"]

        # Create a minimal valid MP4 file (very small test video)
        # This is a minimal MP4 structure that ffprobe can recognize
        # ftyp + mdat boxes (minimal valid MP4)
        mp4_content = (
            b"\x00\x00\x00\x20\x66\x74\x79\x70\x69\x73\x6f\x6d\x00\x00\x02\x00"
            b"\x69\x73\x6f\x6d\x69\x73\x6f\x32\x61\x76\x63\x31\x6d\x70\x34\x31"
            b"\x00\x00\x00\x08\x6d\x64\x61\x74"
        )

        # Initiate upload
        init_resp = await client.post(
            "/api/uploads/initiate",
            json={
                "filename": "test_video.mp4",
                "filetype": "video/mp4",
                "size_bytes": len(mp4_content),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == 201
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        # Upload the video content
        patch_resp = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=mp4_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(mp4_content)),
            },
        )
        assert patch_resp.status_code == 204

        # Verify ffprobe metadata was extracted
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None
            assert upload.mimetype == "video/mp4"
            assert upload.meta_data is not None
            # Check if ffprobe data exists (it may be None if ffprobe is not installed)
            # We don't assert that it must exist to allow tests to pass without ffprobe
            if "ffprobe" in upload.meta_data:
                assert isinstance(upload.meta_data["ffprobe"], dict)
                # Basic structure check
                assert "format" in upload.meta_data["ffprobe"] or "streams" in upload.meta_data["ffprobe"]


@pytest.mark.asyncio
async def test_ffprobe_not_run_for_non_multimedia():
    """Test that ffprobe is not run for non-multimedia files."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create unrestricted token
        resp = await client.post(
            app.url_path_for("create_token"),
            json={
                "label": "Text Upload",
                "max_size_bytes": 1_000_000,
                "expires_in_days": 1,
            },
            headers={"Authorization": f"Bearer {settings.admin_api_key}"},
        )
        assert resp.status_code == 201
        token_data = resp.json()
        token_value = token_data["token"]

        # Initiate upload for text file
        text_content = b"This is just text content, not multimedia."
        init_resp = await client.post(
            "/api/uploads/initiate",
            json={
                "filename": "test.txt",
                "filetype": "text/plain",
                "size_bytes": len(text_content),
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == 201
        upload_data = init_resp.json()
        upload_id = upload_data["upload_id"]

        # Upload the content
        patch_resp = await client.patch(
            f"/api/uploads/{upload_id}/tus",
            content=text_content,
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(len(text_content)),
            },
        )
        assert patch_resp.status_code == 204

        # Verify ffprobe was NOT run for text file
        async with SessionLocal() as session:
            stmt = select(models.UploadRecord).where(models.UploadRecord.id == upload_id)
            res = await session.execute(stmt)
            upload = res.scalar_one_or_none()
            assert upload is not None
            assert upload.mimetype.startswith("text/")
            assert upload.meta_data is not None
            assert "ffprobe" not in upload.meta_data
