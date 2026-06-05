from collections.abc import AsyncGenerator
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import get_settings

settings = get_settings()


def build_engine():
    if settings.sync_database_url.startswith("sqlite"):
        return create_engine(
            settings.sync_database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )

    connect_args = {
        "connect_timeout": settings.db_connect_timeout,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

    if settings.db_use_null_pool:
        return create_engine(
            settings.sync_database_url,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    return create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_use_lifo=True,
        connect_args=connect_args,
    )


def build_async_engine():
    if settings.async_database_url.startswith("sqlite"):
        return create_async_engine(
            settings.async_database_url,
            pool_pre_ping=True,
            connect_args={"check_same_thread": False},
        )

    connect_args = {
        "connect_timeout": settings.db_connect_timeout,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

    if settings.db_use_null_pool:
        return create_async_engine(
            settings.async_database_url,
            pool_pre_ping=True,
            poolclass=NullPool,
            connect_args=connect_args,
        )

    return create_async_engine(
        settings.async_database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
        pool_use_lifo=True,
        connect_args=connect_args,
    )


engine = build_engine()
async_engine = build_async_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AsyncSessionLocal = sessionmaker(async_engine, class_=AsyncSession, autocommit=False, autoflush=False)
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as db:
        yield db
