import pytest

from app.schemas import (
    UserCreate,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_LOGIN = "test_user"
USER_PASSWORD = "test_password"


async def _register(
    client, login: str = USER_LOGIN, password: str = USER_PASSWORD
):
    return await client.post(
        "/auth/register",
        json={"login": login, "password": password},
    )


async def _login(
    client, login: str = USER_LOGIN, password: str = USER_PASSWORD
):
    return await client.post(
        "/auth/login",
        json={"login": login, "password": password},
    )


# ---------------------------------------------------------------------------
# /register
# ---------------------------------------------------------------------------


async def test_register_returns_tokens(client):
    user = UserCreate(login=USER_LOGIN, password=USER_PASSWORD)

    response = await client.post("/auth/register", json=user.model_dump())
    assert response.status_code == 200
    data = response.json()
    assert data.get("access_token")
    assert data.get("refresh_token")


async def test_duble_register(client):
    await _register(client)

    response = await _register(client, password="other_password")
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------


async def test_login_returns_tokens(client):
    await _register(client)

    response = await _login(client)
    assert response.status_code == 200
    data = response.json()
    assert data.get("access_token")
    assert data.get("refresh_token")


async def test_login_wrong_password(client):
    await _register(client)

    response = await _login(client, password="wrong_password")
    assert response.status_code == 401


async def test_login_unknown_user(client):
    response = await _login(client, login="ghost_user")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------


async def test_refresh_returns_new_tokens(client):
    reg = await _register(client)
    old_refresh = reg.json()["refresh_token"]

    response = await client.post(
        "/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("access_token")
    assert data.get("refresh_token")
    assert data["refresh_token"] != old_refresh


async def test_refresh_invalid_token(client):
    response = await client.post(
        "/auth/refresh", json={"refresh_token": "not-a-real-token"}
    )
    assert response.status_code == 401


async def test_refresh_token_rotation(client):
    """После первого /refresh старый refresh-токен должен быть инвалидирован."""
    reg = await _register(client)
    old_refresh = reg.json()["refresh_token"]

    await client.post("/auth/refresh", json={"refresh_token": old_refresh})

    response = await client.post(
        "/auth/refresh", json={"refresh_token": old_refresh}
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------


async def test_logout_success(client):
    reg = await _register(client)
    access_token = reg.json()["access_token"]
    refresh_token = reg.json()["refresh_token"]

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


async def test_logout_invalidates_refresh_token(client):
    """После logout refresh-токен не должен работать."""
    reg = await _register(client)
    access_token = reg.json()["access_token"]
    refresh_token = reg.json()["refresh_token"]

    await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response = await client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert response.status_code == 401


async def test_logout_requires_auth(client):
    """Без Bearer-токена /logout должен вернуть 401/403."""
    reg = await _register(client)
    refresh_token = reg.json()["refresh_token"]

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code in (401, 403)
