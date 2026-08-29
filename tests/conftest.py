"""Test fixtures.

Isolation strategy: every test runs inside a database transaction that is
rolled back when the test ends. Nothing is ever committed, so the suite writes
no permanent rows and needs no cleanup — there is not a single DELETE in it.

The application under test shares the test's session through FastAPI's
`dependency_overrides`, which is what lets its own `commit()` calls land on a
SAVEPOINT instead of the real transaction.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core import settings
from app.core.database import get_session
from app.main import app

engine = create_async_engine(str(settings.data_base.sql_url))

# Everything the suite creates carries this prefix, so any row that ever
# escapes the rollback is obvious and findable with one query.
AUTO_TEST_PREFIX = "auto_test_"

DEFAULT_PASSWORD = "auto_test_password"


def auto_test_login() -> str:
    """A unique login that fits users.login (String(30))."""
    return f"{AUTO_TEST_PREFIX}{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def session():
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # create_savepoint: the app calls commit() inside save_transactions;
        # without this it would commit our outer transaction for real.
        db_session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield db_session
        finally:
            await db_session.close()
            await transaction.rollback()


@pytest.fixture
async def client(session: AsyncSession):
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
async def auth_client(client: AsyncClient):
    """A client already registered and authenticated as a throwaway user."""
    login = auto_test_login()
    response = await client.post(
        "/auth/register", json={"login": login, "password": DEFAULT_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client


@pytest.fixture
def account_factory(auth_client: AsyncClient):
    async def create(
        institution_acc_name: str = "GBP General",
        name: str | None = None,
    ) -> dict:
        response = await auth_client.post(
            "/accounts",
            json={
                "name": name or f"{AUTO_TEST_PREFIX}{uuid.uuid4().hex[:6]}",
                "institution": "revolut",
                "institution_acc_name": institution_acc_name,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    return create
