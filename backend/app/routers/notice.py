from pathlib import Path

from fastapi import APIRouter

from backend.app.config import settings

router = APIRouter(prefix="/api/notice", tags=["notice"])


@router.get("/", name="get_notice")
async def get_notice() -> dict[str, str | None]:
    """
    Retrieve the site notice content from the notice.md file.

    Returns:
        dict: A dictionary with the notice content, or None if no notice is set.

    """
    notice_file: Path = Path(settings.config_path) / "notice.md"
    if not notice_file.exists():
        return {"notice": None}
    content: str = notice_file.read_text(encoding="utf-8")
    return {"notice": content}
