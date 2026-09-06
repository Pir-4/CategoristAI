"""Fixtures and pytest hooks. Nothing here is meant to be imported.

Constants, helper functions and test data live in `tests/helpers.py` and
`tests/test_data/` - see the module docstring of `tests/helpers.py` for why.

Isolation strategy: every test runs inside a database transaction that is
rolled back when the test ends. Nothing is ever committed, so the suite writes
no permanent rows and needs no cleanup — there is not a single DELETE in it.

The application under test shares the test's session through FastAPI's
`dependency_overrides`, which is what lets its own `commit()` calls land on a
SAVEPOINT instead of the real transaction.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core import UserRole, settings
from app.core.database import get_session
from app.main import app
from app.services.user_service import get_user_by_login
from tests.helpers import RegisteredUser, auto_test_login, auto_test_name
from tests.test_data.users import DEFAULT_PASSWORD

engine = create_async_engine(str(settings.data_base.sql_url))


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
                "name": name or auto_test_name(6),
                "institution": "revolut",
                "institution_acc_name": institution_acc_name,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()

    return create


@pytest.fixture
def register_user(client: AsyncClient, session: AsyncSession):
    """Create a user through the real /auth/register endpoint.

    `role` is applied directly in the database because nothing in the API
    grants admin - it is a deliberate out-of-band operation. The change is
    flushed, not committed, so it dies with the test transaction, and the
    already-issued access token stays valid: the role is read from the
    database on every request.
    """

    async def create(
        login: str | None = None,
        password: str = DEFAULT_PASSWORD,
        role: UserRole | None = None,
    ) -> RegisteredUser:
        login = login or auto_test_login()
        response = await client.post(
            "/auth/register", json={"login": login, "password": password}
        )
        assert response.status_code == 200, response.text
        body = response.json()

        db_user = await get_user_by_login(session, login)
        assert db_user is not None
        if role is not None:
            db_user.role = role
            await session.flush()

        return RegisteredUser(
            login=login,
            password=password,
            user_id=db_user.id,
            access_token=body["access_token"],
            refresh_token=body["refresh_token"],
        )

    return create


@pytest.fixture
async def admin(register_user) -> RegisteredUser:
    return await register_user(role=UserRole.ADMIN)
