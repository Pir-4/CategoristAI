"""The /users endpoints end to end: admin-only writes and reads.

Admin is granted out of band (see the `admin` fixture) because no endpoint
grants it. Every failure is pinned by its `code`, not by its status alone -
403 and 404 here each have exactly one code that belongs to them.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core import ErrorCode
from tests.helpers import RegisteredUser
from tests.test_data.users import USER_READ_FIELDS

pytestmark = pytest.mark.asyncio(loop_scope="session")

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"

NEW_PASSWORD = "auto_test_new_password"


async def test_admin_crud_returns_only_public_user_fields(
    client: AsyncClient, admin: RegisteredUser, register_user
):
    """The admin surface works, and none of it leaks a credential.

    `UserRead` is the single filter in front of five responses, so they are
    all checked here rather than only on /users/me: a field added to the
    schema escapes through every one of them at once.
    """
    target = await register_user()
    created_login = f"{target.login}_new"

    listed = await client.get("/users", headers=admin.headers)
    fetched = await client.get(
        f"/users/{target.user_id}", headers=admin.headers
    )
    created = await client.post(
        "/users",
        json={"login": created_login, "password": NEW_PASSWORD},
        headers=admin.headers,
    )
    patched = await client.patch(
        f"/users/{target.user_id}",
        json={"login": f"{target.login}_upd"},
        headers=admin.headers,
    )
    me = await client.get("/users/me", headers=admin.headers)

    for label, response in [
        ("list", listed),
        ("by_id", fetched),
        ("create", created),
        ("patch", patched),
        ("me", me),
    ]:
        assert response.status_code == 200, f"{label}: {response.text}"

    # The requested changes actually happened.
    logins = {user["login"] for user in listed.json()}
    assert {admin.login, target.login} <= logins
    assert fetched.json()["id"] == str(target.user_id)
    assert created.json()["login"] == created_login
    assert patched.json()["login"] == f"{target.login}_upd"
    assert me.json()["login"] == admin.login

    bodies = {
        "list": listed.json()[0],
        "by_id": fetched.json(),
        "create": created.json(),
        "patch": patched.json(),
        "me": me.json(),
    }
    for label, body in bodies.items():
        assert set(body) == USER_READ_FIELDS, (
            f"{label} returned {sorted(set(body) - USER_READ_FIELDS)} "
            "on top of the public user fields"
        )


@pytest.mark.parametrize(
    ("label", "method", "path", "json_body"),
    [
        ("list", "GET", "/users", None),
        ("by_id", "GET", f"/users/{UNKNOWN_ID}", None),
        (
            "create",
            "POST",
            "/users",
            {"login": "auto_test_smuggled", "password": NEW_PASSWORD},
        ),
        (
            "patch",
            "PATCH",
            f"/users/{UNKNOWN_ID}",
            {"login": "auto_test_hacked"},
        ),
    ],
)
async def test_non_admin_is_denied_on_every_admin_endpoint(
    client: AsyncClient, register_user, label, method, path, json_body
):
    """Authenticated is not authorised.

    The check must fire before the endpoint does any work, so a plain user
    cannot read the user table or mint accounts. 403 with `permission_denied`
    is the contract; the unknown ids above prove the deny happens first,
    since a passing admin would get a 404 instead.
    """
    user = await register_user()

    response = await client.request(
        method, path, json=json_body, headers=user.headers
    )

    assert response.status_code == 403, f"{label}: {response.text}"
    assert response.json()["code"] == ErrorCode.PERMISSION_DENIED


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_unknown_user_id_is_reported_as_not_found(
    client: AsyncClient, admin: RegisteredUser, method: str
):
    path = f"/users/{uuid4()}"
    body = {"login": "auto_test_ghost"} if method == "PATCH" else None

    response = await client.request(
        method, path, json=body, headers=admin.headers
    )

    assert response.status_code == 404, response.text
    assert response.json()["code"] == ErrorCode.USER_NOT_FOUND


@pytest.mark.parametrize("operation", ["create", "update"])
async def test_a_taken_login_is_rejected_on_create_and_update(
    client: AsyncClient, admin: RegisteredUser, register_user, operation: str
):
    """Login uniqueness is decided by the database, on both write paths.

    The endpoint pre-check in /auth/register is only a fast path - two
    concurrent requests both pass it - so the IntegrityError has to surface
    as a 409, not as a 500 with a stacktrace.
    """
    taken = await register_user()

    if operation == "create":
        response = await client.post(
            "/users",
            json={"login": taken.login, "password": NEW_PASSWORD},
            headers=admin.headers,
        )
    else:
        response = await client.patch(
            f"/users/{admin.user_id}",
            json={"login": taken.login},
            headers=admin.headers,
        )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == ErrorCode.LOGIN_ALREADY_TAKEN
    assert "Traceback" not in response.json()["message"]


async def test_patched_password_replaces_the_old_one(
    client: AsyncClient, admin: RegisteredUser, register_user
):
    """A password change must take effect on the login endpoint.

    Only the login proves it: the response body cannot show the hash, so a
    patch that quietly failed to re-hash looks identical from the outside.

    An explicit `"login": null` rides along on purpose: the service drops
    None values (`exclude_none`), so a null must read as "leave it alone".
    Treating it as a value instead writes NULL into a NOT NULL column.
    """
    target = await register_user()

    patched = await client.patch(
        f"/users/{target.user_id}",
        json={"login": None, "password": NEW_PASSWORD},
        headers=admin.headers,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["login"] == target.login

    with_new = await client.post(
        "/auth/login",
        json={"login": target.login, "password": NEW_PASSWORD},
    )
    assert with_new.status_code == 200, with_new.text

    with_old = await client.post(
        "/auth/login",
        json={"login": target.login, "password": target.password},
    )
    assert with_old.status_code == 401
    assert with_old.json()["code"] == ErrorCode.INVALID_CREDENTIALS
