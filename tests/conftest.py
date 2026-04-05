import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core import settings
from app.core.database import get_session
from app.main import app
from app.models import BaseModel

engine = create_async_engine(str(settings.data_base.test_sql_url))
TestSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(scope="session", autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(BaseModel.metadata.drop_all)


@pytest.fixture
async def session() -> AsyncSession:
    async with TestSessionFactory() as s:
        yield s
        await s.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()
