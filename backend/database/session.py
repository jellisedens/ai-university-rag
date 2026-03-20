from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.config import settings

# Create the async database engine
# This manages the actual connection pool to PostgreSQL
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

# Create a session factory
# Each request to the API gets its own session
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# Base class for all ORM models
# Every table we define will inherit from this
class Base(DeclarativeBase):
    pass