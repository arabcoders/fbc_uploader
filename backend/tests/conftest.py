import json
import os
import sys
import tempfile
from importlib import reload
from pathlib import Path

# Create temp directories once and store them
TEST_CONFIG_DIR = tempfile.mkdtemp(prefix="fbc-test-config-")
TEST_STORAGE_DIR = tempfile.mkdtemp(prefix="fbc-test-storage-")

# Set test environment variables BEFORE any backend imports
os.environ["FBC_CONFIG_PATH"] = TEST_CONFIG_DIR
os.environ["FBC_STORAGE_PATH"] = TEST_STORAGE_DIR
os.environ["FBC_DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["FBC_ADMIN_API_KEY"] = "test-admin"
os.environ["FBC_SKIP_MIGRATIONS"] = "1"
os.environ["FBC_SKIP_CLEANUP"] = "1"

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.app.config as config_module
from backend.app import metadata_schema
from backend.app.config import Settings

# Force reload settings with test environment
config_module.settings = Settings()

# Reload metadata_schema to pick up new settings
reload(metadata_schema)


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
