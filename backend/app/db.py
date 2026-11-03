from collections.abc import AsyncIterator

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

# JSONB в PostgreSQL, JSON в SQLite (тесты)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    type_annotation_map = {dict: JsonType, list: JsonType}
    # серверные значения (created_at/updated_at) читаются сразу через RETURNING, без ленивой загрузки в async
    __mapper_args__ = {"eager_defaults": True}


def _make_engine():
    s = get_settings()
    kwargs = {}
    if s.database_url.startswith("postgresql"):
        kwargs = {"pool_size": s.db_pool_size, "max_overflow": s.db_max_overflow, "pool_pre_ping": True}
    return create_async_engine(s.database_url, **kwargs)


engine = _make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
