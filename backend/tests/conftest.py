import atexit
import json
import os
import shutil
import sys
import tempfile
from importlib import reload
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

TESTS_TMP_ROOT = Path("/tmp/fbc-tests")  # noqa: S108
TESTS_TMP_ROOT.mkdir(parents=True, exist_ok=True)

TEST_RUN_DIR = Path(tempfile.mkdtemp(prefix="run-", dir=str(TESTS_TMP_ROOT)))
TEST_CONFIG_DIR = TEST_RUN_DIR / "config"
TEST_STORAGE_DIR = TEST_RUN_DIR / "storage"
TEST_FRONTEND_DIR = TEST_RUN_DIR / "frontend"
TEST_TEMP_DIR = TEST_RUN_DIR / "tmp"
TEST_FALLBACK_THUMBNAIL_BYTES = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"

for path in (TEST_CONFIG_DIR, TEST_STORAGE_DIR, TEST_FRONTEND_DIR, TEST_TEMP_DIR):
    path.mkdir(parents=True, exist_ok=True)


def _cleanup_test_run_dir() -> None:
    shutil.rmtree(TEST_RUN_DIR, ignore_errors=True)


atexit.register(_cleanup_test_run_dir)

os.environ["TMPDIR"] = str(TEST_TEMP_DIR)
os.environ["TMP"] = str(TEST_TEMP_DIR)
os.environ["TEMP"] = str(TEST_TEMP_DIR)
tempfile.tempdir = str(TEST_TEMP_DIR)

os.environ["FBC_CONFIG_PATH"] = str(TEST_CONFIG_DIR)
os.environ["FBC_STORAGE_PATH"] = str(TEST_STORAGE_DIR)
os.environ["FBC_FRONTEND_EXPORT_PATH"] = str(TEST_FRONTEND_DIR)
os.environ["FBC_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["FBC_ADMIN_API_KEY"] = "test-admin"
os.environ["FBC_SKIP_MIGRATIONS"] = "1"
os.environ["FBC_SKIP_CLEANUP"] = "1"
os.environ["FBC_ALLOW_PUBLIC_DOWNLOADS"] = "0"

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.app.config as config_module
from backend.app import metadata_schema
from backend.app.config import Settings
from backend.app.postprocessing import ProcessingQueue

config_module.settings = Settings()


reload(metadata_schema)


@pytest.fixture(scope="session")
def test_run_dir():
    return TEST_RUN_DIR


@pytest.fixture(autouse=True)
async def reset_database():
    """Clean database before and after each test by dropping and recreating all tables."""
    from backend.app.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
def reset_metadata_schema():
    """Reset metadata cache and remove any existing schema between tests."""
    cfg_dir = Path(os.environ["FBC_CONFIG_PATH"])
    cfg_dir.mkdir(parents=True, exist_ok=True)
    metadata_schema._cache = {"mtime": None, "schema": []}
    schema_path = cfg_dir / "metadata.json"
    if schema_path.exists():
        schema_path.unlink()
    yield
    metadata_schema._cache = {"mtime": None, "schema": []}


@pytest.fixture(scope="session", autouse=True)
async def setup_db(test_run_dir):
    from backend.app.db import engine, init_db

    await init_db()
    yield
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_frontend(test_run_dir):
    """Create minimal frontend structure for tests."""
    index_html = TEST_FRONTEND_DIR / "index.html"
    index_html.write_text("<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>")

    fallback_image = TEST_FRONTEND_DIR / "assets" / "images" / "thumbnail-fallback.jpg"
    fallback_image.parent.mkdir(parents=True, exist_ok=True)
    fallback_image.write_bytes(TEST_FALLBACK_THUMBNAIL_BYTES)


@pytest.fixture
async def processing_queue():
    """Create a fresh processing queue for each test."""
    queue = ProcessingQueue()
    queue.start_worker()
    yield queue
    await queue.stop_worker()


@pytest.fixture
async def client(processing_queue):
    """Create an HTTP client with overridden dependencies."""
    from backend.app.main import app

    app.state.processing_queue = processing_queue

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


def seed_schema(fields: list[dict] | None = None) -> Path:
    """Seed test metadata schema with provided or default fields."""
    if fields is None:
        fields = [
            {"key": "broadcast_date", "label": "Broadcast Date", "type": "date", "required": True},
            {"key": "title", "label": "Title", "type": "string", "required": True},
            {
                "key": "source",
                "label": "Source",
                "type": "select",
                "required": True,
                "options": ["youtube", "tv"],
                "allowCustom": True,
            },
        ]

    config_dir = Path(os.environ["FBC_CONFIG_PATH"])
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "metadata.json"
    path.write_text(json.dumps(fields))
    metadata_schema._cache = {"mtime": None, "schema": []}
    return path
