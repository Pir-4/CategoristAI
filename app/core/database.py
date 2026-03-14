from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

_engine = create_async_engine(str(settings.data_base.sql_url))
_session_factory = async_sessionmaker(
    _engine, class_=AsyncSession, expire_on_commit=False
)


async def get_session():
    async with _session_factory() as session:
        yield session
