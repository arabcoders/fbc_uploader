import asyncio
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

import backend.app.main as app_main
from backend.app import config, migrate
from backend.main import main

INITIAL_REVISION = "5dc14b681055"


@pytest.fixture
def database(tmp_path, monkeypatch):
    path = tmp_path / "fbc.db"
    monkeypatch.setattr(config.settings, "database_url", f"sqlite+aiosqlite:///{path}")
    monkeypatch.setattr(migrate, "settings", config.settings)
    return path


@pytest.fixture
def alembic_config():
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    return config


@pytest.fixture
def initialized_database(database, alembic_config):
    command.upgrade(alembic_config, INITIAL_REVISION)
    return database


@pytest.mark.parametrize("exists", [False, True])
def test_initializes_empty_database(database, alembic_config, exists):
    if exists:
        database.touch()

    migrate.run_migrations(no_auto_migration=True)

    with closing(sqlite3.connect(database)) as conn:
        assert {row[0] for row in conn.execute("SELECT version_num FROM alembic_version")} == set(
            ScriptDirectory.from_config(alembic_config).get_heads()
        )
        assert "public_id" in {row[1] for row in conn.execute("PRAGMA table_info(uploads)")}


def test_accepts_current_revision(initialized_database, alembic_config):
    migrate.run_migrations()
    with closing(sqlite3.connect(initialized_database)) as conn:
        assert {row[0] for row in conn.execute("SELECT version_num FROM alembic_version")} == set(
            ScriptDirectory.from_config(alembic_config).get_heads()
        )
    original = initialized_database.read_bytes()

    migrate.run_migrations(no_auto_migration=True)

    assert initialized_database.read_bytes() == original


@pytest.mark.parametrize("revision", [INITIAL_REVISION, "ffffffffffff", None], ids=["old", "unknown", "unversioned"])
async def test_rejects_mismatched_revision(initialized_database, monkeypatch, revision):
    if revision != INITIAL_REVISION:
        with closing(sqlite3.connect(initialized_database)) as conn, conn:
            if revision is None:
                conn.execute("DROP TABLE alembic_version")
            else:
                conn.execute("UPDATE alembic_version SET version_num = ?", (revision,))
    original = initialized_database.read_bytes()
    monkeypatch.setattr(config.settings, "skip_migrations", False)
    monkeypatch.setattr(config.settings, "no_auto_migration", True)
    monkeypatch.setattr(app_main, "settings", config.settings)
    app = app_main.create_app()

    message = f"Database revision is {revision or 'unversioned'}; expected .*Start without --no-auto-migration"
    with pytest.raises(RuntimeError, match=message):
        async with asyncio.timeout(10), app.router.lifespan_context(app):
            pass

    assert initialized_database.read_bytes() == original


@pytest.mark.parametrize(("dev_env", "dev_args"), [("0", ["--dev"]), ("1", [])], ids=["flag", "environment"])
def test_cli_reloads_with_guard(monkeypatch, dev_env, dev_args):
    monkeypatch.setenv("FBC_DEV_MODE", dev_env)
    monkeypatch.setenv("FBC_NO_AUTO_MIGRATION", "0")

    def check_env(*args, reload, **kwargs):
        assert os.environ["FBC_DEV_MODE"] == "1"
        assert os.environ["FBC_NO_AUTO_MIGRATION"] == "1"
        assert reload is True

    with patch("backend.main.uvicorn.run", side_effect=check_env) as server:
        main([*dev_args, "--no-auto-migration"])

    server.assert_called_once()
