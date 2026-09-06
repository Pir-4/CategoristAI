import time
from datetime import UTC, datetime, timedelta

import pytest

from app.services.token_service import find_refresh_token

from app.schemas import (
    UserCreate,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

USER_LOGIN = "auto_test_user"
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


async def test_validation_error_never_echoes_the_password(client):
    """A rejected body must not carry the password back out.

    Pydantic reports the *whole request body* in `input` when a different
    field is the one that failed - here a missing `login` - so scrubbing only
    the errors whose `loc` names a credential leaves the password in both the
    response and the log line.
    """
    response = await client.post(
        "/auth/register", json={"password": "sup3rs3cret"}
    )

    assert response.status_code == 422
    assert "sup3rs3cret" not in response.text


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
    response = await _login(client, login="auto_test_ghost")
    assert response.status_code == 401


async def test_login_failures_are_indistinguishable_by_timing(client):
    """Both login failures must cost the same bcrypt time.

    Identical responses are not enough: returning early on an unknown login
    makes the two cases ~8 ms vs ~233 ms apart, which is a readable account
    enumeration oracle. The bound is deliberately far below the real bcrypt
    cost (~233 ms) and far above a bare lookup miss, so it fails only if the
    hashing work is actually skipped.
    """
    await _register(client)

    started = time.perf_counter()
    unknown = await _login(client, login="auto_test_ghost")
    unknown_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    wrong_password = await _login(client, password="wrong_password")
    wrong_password_ms = (time.perf_counter() - started) * 1000

    assert unknown.status_code == wrong_password.status_code == 401

    # Everything but request_id, which is unique per request by design.
    def _envelope(response):
        return {k: v for k, v in response.json().items() if k != "request_id"}

    assert _envelope(unknown) == _envelope(wrong_password)
    assert unknown_ms > 100, (
        f"unknown login answered in {unknown_ms:.1f} ms vs "
        f"{wrong_password_ms:.1f} ms for a wrong password - the bcrypt work "
        "is being skipped, which leaks whether the account exists"
    )


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


async def test_logout_revokes_an_expired_token(client, session):
    """Expiry must not block logout.

    The expiry check belongs on /auth/refresh. Refusing to delete an expired
    token here strands the row in the table with no way to clean it up.
    """
    reg = await _register(client)
    refresh_token = reg.json()["refresh_token"]

    db_token = await find_refresh_token(session, refresh_token)
    db_token.expires_at = datetime.now(UTC) - timedelta(days=1)
    await session.flush()

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {reg.json()['access_token']}"},
    )
    assert response.status_code == 200


async def test_logout_cannot_revoke_another_users_token(client):
    """A refresh token may only be revoked by the user it belongs to.

    Presenting someone else's token must be rejected *and* leave that token
    usable - otherwise any authenticated caller can end anyone's session.
    """
    victim = await _register(client, login="auto_test_victim")
    attacker = await _register(client, login="auto_test_attacker")
    victim_refresh = victim.json()["refresh_token"]

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": victim_refresh},
        headers={"Authorization": f"Bearer {attacker.json()['access_token']}"},
    )
    assert response.status_code == 401

    survived = await client.post(
        "/auth/refresh", json={"refresh_token": victim_refresh}
    )
    assert survived.status_code == 200


async def test_logout_requires_auth(client):
    """Без Bearer-токена /logout должен вернуть 401/403."""
    reg = await _register(client)
    refresh_token = reg.json()["refresh_token"]

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code in (401, 403)
