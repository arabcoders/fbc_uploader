from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import settings


def run_migrations() -> None:
    """Run Alembic migrations to head. Uses project root alembic.ini and overrides DB URL from settings."""
    root_cfg = Path(__file__).resolve().parents[2] / "alembic.ini"
    cfg = Config(str(root_cfg))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "heads")
