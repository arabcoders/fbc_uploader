from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import settings


def run_migrations(*, no_auto_migration: bool = False) -> None:
    """Bring the database to the Alembic heads, optionally only initializing an empty database."""
    root_cfg: Path = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(root_cfg))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    if settings.database_url is None:
        msg = "Database URL is not configured"
        raise RuntimeError(msg)
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    cfg.attributes["no_auto_migration"] = no_auto_migration
    command.upgrade(cfg, "heads")
