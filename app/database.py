from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

import os as _os
_db_url = _os.environ.get("DATABASE_URL") or settings.database_url
_connect_args = {"ssl": "require"} if "postgres.database.azure.com" in _db_url else {}
engine = create_async_engine(_db_url, echo=settings.environment == "development", connect_args=_connect_args)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
