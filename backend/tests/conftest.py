import json
import os
import sys
import tempfile
from importlib import reload
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="fbc-test-config-")
TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="fbc-test-storage-")
TEST_FRONTEND_DIR = tempfile.mkdtemp(prefix="fbc-test-frontend-")

os.environ["FBC_CONFIG_PATH"] = TEST_CONFIG_DIR
os.environ["FBC_STORAGE_PATH"] = TEST_STORAGE_DIR
os.environ["FBC_FRONTEND_EXPORT_PATH"] = TEST_FRONTEND_DIR
os.environ["FBC_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["FBC_ADMIN_API_KEY"] = "test-admin"
os.environ["FBC_SKIP_MIGRATIONS"] = "1"
os.environ["FBC_SKIP_CLEANUP"] = "1"

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.app.config as config_module
from backend.app import metadata_schema
from backend.app.config import Settings
from backend.app.postprocessing import ProcessingQueue

config_module.settings = Settings()


reload(metadata_schema)


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
async def setup_db():
    from backend.app.db import engine, init_db

    await init_db()
    yield
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def setup_frontend():
    """Create minimal frontend structure for tests."""
    frontend_dir = Path(TEST_FRONTEND_DIR)
    frontend_dir.mkdir(parents=True, exist_ok=True)
    index_html = frontend_dir / "index.html"
    index_html.write_text("<!DOCTYPE html><html><head><title>Test</title></head><body></body></html>")
    yield
    import shutil

    shutil.rmtree(TEST_FRONTEND_DIR, ignore_errors=True)


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
