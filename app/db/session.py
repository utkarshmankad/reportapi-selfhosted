"""SQLAlchemy async session management."""

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
