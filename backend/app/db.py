from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.asyncio.engine import AsyncEngine
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import StaticPool

from .config import settings

url: URL = make_url(settings.database_url)
engine_kwargs: dict[str, Any] = {"future": True}
if url.drivername.startswith("sqlite"):
    if url.database and url.database != ":memory:":
        Path(url.database).expanduser().parent.mkdir(parents=True, exist_ok=True)
    else:
        engine_kwargs["poolclass"] = StaticPool

engine: AsyncEngine = create_async_engine(settings.database_url, **engine_kwargs)
SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

Base: Any = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
