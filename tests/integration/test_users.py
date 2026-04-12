import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_LOGIN = "admin_user"
ADMIN_PASSWORD = "admin_password"
REGULAR_LOGIN = "regular_user"
REGULAR_PASSWORD = "regular_password"


async def _register(client, login: str, password: str):
    return await client.post(
        "/auth/register", json={"login": login, "password": password}
    )


async def _register_admin(client, session):
    """Register a user then promote them to admin directly in DB."""
    from app.core import UserRole
    from app.services.user_service import get_user_by_login

    res = await _register(client, ADMIN_LOGIN, ADMIN_PASSWORD)
    assert res.status_code == 200

    user = await get_user_by_login(session, ADMIN_LOGIN)
    user.role = UserRole.ADMIN
    await session.commit()
    await session.refresh(user)

    login_res = await client.post(
        "/auth/login", json={"login": ADMIN_LOGIN, "password": ADMIN_PASSWORD}
    )
    return login_res.json()["access_token"]


async def _register_user(client):
    res = await _register(client, REGULAR_LOGIN, REGULAR_PASSWORD)
    assert res.status_code == 200
    return res.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# GET /users/me
# ---------------------------------------------------------------------------


async def test_get_me_returns_own_profile(client):
    token = await _register_user(client)

    response = await client.get("/users/me", headers=_auth(token))
    assert response.status_code == 200
    data = response.json()
    assert data["login"] == REGULAR_LOGIN
    assert "id" in data
    assert "hashed_password" not in data


async def test_get_me_without_token(client):
    response = await client.get("/users/me")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /users  (admin only)
# ---------------------------------------------------------------------------


async def test_get_users_as_admin(client, session):
    admin_token = await _register_admin(client, session)
    await _register(client, REGULAR_LOGIN, REGULAR_PASSWORD)

    response = await client.get("/users", headers=_auth(admin_token))
    assert response.status_code == 200
    logins = [u["login"] for u in response.json()]
    assert ADMIN_LOGIN in logins
    assert REGULAR_LOGIN in logins


async def test_get_users_as_regular_user(client):
    token = await _register_user(client)

    response = await client.get("/users", headers=_auth(token))
    assert response.status_code == 403


async def test_get_users_without_token(client):
    response = await client.get("/users")
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# GET /users/{user_id}  (admin only)
# ---------------------------------------------------------------------------


async def test_get_user_by_id_as_admin(client, session):
    admin_token = await _register_admin(client, session)
    user_token = await _register(client, REGULAR_LOGIN, REGULAR_PASSWORD)

    me = await client.get(
        "/users/me", headers=_auth(user_token.json()["access_token"])
    )
    user_id = me.json()["id"]

    response = await client.get(f"/users/{user_id}", headers=_auth(admin_token))
    assert response.status_code == 200
    assert response.json()["login"] == REGULAR_LOGIN


async def test_get_user_by_id_not_found(client, session):
    admin_token = await _register_admin(client, session)
    fake_id = "00000000-0000-0000-0000-000000000000"

    response = await client.get(f"/users/{fake_id}", headers=_auth(admin_token))
    assert response.status_code == 404


async def test_get_user_by_id_as_regular_user(client, session):
    await _register_admin(client, session)
    user_token = await _register_user(client)

    response = await client.get(
        "/users/00000000-0000-0000-0000-000000000000", headers=_auth(user_token)
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# POST /users  (admin only)
# ---------------------------------------------------------------------------


async def test_create_user_as_admin(client, session):
    admin_token = await _register_admin(client, session)

    response = await client.post(
        "/users",
        json={"login": "new_user", "password": "new_password"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["login"] == "new_user"


async def test_create_user_as_regular_user(client):
    token = await _register_user(client)

    response = await client.post(
        "/users",
        json={"login": "new_user", "password": "new_password"},
        headers=_auth(token),
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}  (admin only)
# ---------------------------------------------------------------------------


async def test_update_user_login_as_admin(client, session):
    admin_token = await _register_admin(client, session)
    user_res = await _register(client, REGULAR_LOGIN, REGULAR_PASSWORD)
    user_id = (
        await client.get(
            "/users/me", headers=_auth(user_res.json()["access_token"])
        )
    ).json()["id"]

    response = await client.patch(
        f"/users/{user_id}",
        json={"login": "updated_login"},
        headers=_auth(admin_token),
    )
    assert response.status_code == 200
    assert response.json()["login"] == "updated_login"


async def test_update_user_as_regular_user(client):
    token = await _register_user(client)
    fake_id = "00000000-0000-0000-0000-000000000000"

    response = await client.patch(
        f"/users/{fake_id}",
        json={"login": "hacked"},
        headers=_auth(token),
    )
    assert response.status_code == 403
