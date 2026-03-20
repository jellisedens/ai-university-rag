from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from backend.database.session import async_session


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a database session for each request."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise