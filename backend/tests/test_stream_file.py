from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import status

from backend.app.main import app
from backend.tests.test_postprocessing import wait_for_processing
from backend.tests.utils import complete_upload, create_token


@pytest.mark.asyncio
async def test_stream_file_returns_inline_content_disposition(client):
    """Streaming endpoint should return completed media inline for playback."""
    with patch("backend.app.security.settings.allow_public_downloads", True):
        token_data = await create_token(client, max_uploads=1)
        token_value = token_data["token"]
        download_token = token_data["download_token"]

        video_file = Path(__file__).parent / "fixtures" / "sample.mp4"
        file_size = video_file.stat().st_size

        init_resp = await client.post(
            app.url_path_for("initiate_upload"),
            json={
                "filename": "sample.mp4",
                "filetype": "video/mp4",
                "size_bytes": file_size,
                "meta_data": {},
            },
            params={"token": token_value},
        )
        assert init_resp.status_code == status.HTTP_201_CREATED, "Upload initiation should succeed"
        upload_id = init_resp.json()["upload_id"]

        patch_resp = await client.patch(
            app.url_path_for("tus_patch", upload_id=upload_id),
            content=video_file.read_bytes(),
            headers={
                "Content-Type": "application/offset+octet-stream",
                "Upload-Offset": "0",
                "Content-Length": str(file_size),
            },
        )
        assert patch_resp.status_code == status.HTTP_204_NO_CONTENT, "Video upload should complete"

        complete_status, complete_data = await complete_upload(client, upload_id, token_value)
        assert complete_status == status.HTTP_200_OK, "Completion endpoint should accept uploaded video files"
        assert complete_data["status"] == "postprocessing", "Video should enter postprocessing after explicit completion"

        completed = await wait_for_processing([upload_id], timeout=10.0)
        assert completed, "Video processing should complete within timeout"

        response = await client.get(app.url_path_for("stream_file", download_token=download_token, upload_id=upload_id))

        assert response.status_code == status.HTTP_200_OK, "Streaming endpoint should return completed media"
        assert response.headers["content-type"].startswith("video/mp4"), "Streaming endpoint should preserve media type"
        assert response.headers["content-disposition"].startswith("inline;"), "Streaming endpoint should use inline disposition"
