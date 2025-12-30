import contextlib
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "fbc_uploader"
    config_path: str = Field("./data/config", validation_alias="FBC_CONFIG_PATH")
    database_url: str | None = Field(None, validation_alias="FBC_DATABASE_URL")
    admin_api_key: str = Field("change-me", validation_alias="FBC_ADMIN_API_KEY")
    storage_path: str = Field("./data/uploads", validation_alias="FBC_STORAGE_PATH")
    frontend_export_path: str = Field("./frontend/exported", validation_alias="FBC_FRONTEND_EXPORT_PATH")
    public_base_url: str | None = Field(default=None, validation_alias="FBC_PUBLIC_BASE_URL")
    default_token_ttl_hours: int = Field(24, ge=1, le=24 * 30)
    allowed_origins: list[str] = Field(default_factory=lambda: ["*"])
    cleanup_interval_seconds: int = Field(3600, validation_alias="FBC_CLEANUP_INTERVAL_SECONDS")
    incomplete_ttl_hours: int = Field(24, validation_alias="FBC_INCOMPLETE_TTL_HOURS")
    disabled_tokens_ttl_days: int = Field(30, validation_alias="FBC_DISABLED_TOKENS_TTL_DAYS")
    delete_files_on_token_cleanup: bool = Field(True, validation_alias="FBC_DELETE_FILES_ON_TOKEN_CLEANUP")
    skip_migrations: bool = Field(False, validation_alias="FBC_SKIP_MIGRATIONS")
    skip_cleanup: bool = Field(False, validation_alias="FBC_SKIP_CLEANUP")
    max_chunk_bytes: int = Field(90 * 1024 * 1024, validation_alias="FBC_MAX_CHUNK_BYTES")
    allow_public_downloads: bool = Field(False, validation_alias="FBC_ALLOW_PUBLIC_DOWNLOADS")
    trust_proxy_headers: bool = Field(False, validation_alias="FBC_TRUST_PROXY_HEADERS")

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FBC_", extra="ignore")

    def model_post_init(self, _) -> None:
        cfg_dir: Path = Path(self.config_path).expanduser().resolve()
        cfg_dir.mkdir(parents=True, exist_ok=True)

        if not self.database_url:
            default_db_path: Path = cfg_dir / "fbc.db"
            self.database_url = f"sqlite+aiosqlite:///{default_db_path!s}"

        if self.admin_api_key == "change-me":
            api_path: Path = cfg_dir / "secret.key"
            if not api_path.exists():
                from secrets import token_urlsafe

                key: str = token_urlsafe(32)
                api_path.write_text(key)

                with contextlib.suppress(OSError):
                    api_path.chmod(0o600)

                self.admin_api_key = key
            else:
                self.admin_api_key = api_path.read_text().strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings: Settings = get_settings()
