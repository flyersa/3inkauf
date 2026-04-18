from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
from app.config import get_settings


settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    connect_args={"check_same_thread": False},
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with engine.begin() as conn:
        await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
    await migrate_db()


async def migrate_db():
    """Add columns that may not exist in older databases."""
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql("ALTER TABLE list_items ADD COLUMN image_path TEXT")
        except Exception:
            pass
        try:
            await conn.exec_driver_sql("ALTER TABLE sorting_hints ADD COLUMN list_id TEXT REFERENCES shopping_lists(id)")
        except Exception:
            pass
        # Clean up old global hints that have no list_id (from before per-list change)
        try:
            await conn.exec_driver_sql("DELETE FROM sorting_hints WHERE list_id IS NULL")
        except Exception:
            pass


async def get_session():
    async with async_session() as session:
        yield session
