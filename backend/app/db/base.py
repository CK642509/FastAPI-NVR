"""SQLAlchemy async engine / session 與宣告式 Base。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from ..config import settings


class Base(DeclarativeBase):
    """所有 ORM model 的宣告式基底；Alembic 以 Base.metadata 產生 schema。"""


engine = create_async_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """FastAPI 依賴注入用的 session 產生器。"""
    async with SessionLocal() as session:
        yield session
