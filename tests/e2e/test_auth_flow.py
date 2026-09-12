"""The auth flow end to end: real HTTP, real database, real bcrypt.

Rejections are asserted on the `code` of the error envelope, never on the
message: several of these endpoints answer with the same HTTP status on
purpose and only the code tells the cases apart.
"""

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from httpx import AsyncClient

from app.core import ErrorCode, settings
from app.core.security import create_access_token
from app.services.token_service import find_refresh_token
from tests.helpers import auth_headers, auto_test_login
from tests.test_data.users import DEFAULT_PASSWORD, USER_READ_FIELDS

pytestmark = pytest.mark.asyncio(loop_scope="session")

FOREIGN_SECRET = "auto_test_secret_that_is_not_ours_0123456789"


def _envelope(response) -> dict:
    """The error envelope minus `request_id`, which is unique by design."""
    return {k: v for k, v in response.json().items() if k != "request_id"}


async def _login(client: AsyncClient, login: str, password: str):
    return await client.post(
        "/auth/login", json={"login": login, "password": password}
    )


async def _refresh(client: AsyncClient, token: str):
    return await client.post("/auth/refresh", json={"refresh_token": token})


async def _expire_refresh_token(session, token: str) -> None:
    db_token = await find_refresh_token(session, token)
    assert db_token is not None
    db_token.expires_at = datetime.now(UTC) - timedelta(days=1)
    await session.flush()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_register_then_login_yields_a_working_access_token(
    client: AsyncClient, register_user
):
    """One pass over the wiring: register, log in, use the token.

    Registration and login must both hand out a pair of tokens, and the
    access token must resolve back to the caller's own profile.
    """
    user = await register_user()

    logged_in = await _login(client, user.login, DEFAULT_PASSWORD)
    assert logged_in.status_code == 200, logged_in.text
    tokens = logged_in.json()
    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"] and tokens["refresh_token"]
    # A fresh login must not reuse the token issued at registration.
    assert tokens["refresh_token"] != user.refresh_token

    me = await client.get(
        "/users/me", headers=auth_headers(tokens["access_token"])
    )
    assert me.status_code == 200, me.text
    assert me.json()["login"] == user.login
    assert set(me.json()) == USER_READ_FIELDS


async def test_register_rejects_a_duplicate_login(
    client: AsyncClient, register_user
):
    user = await register_user()

    again = await client.post(
        "/auth/register",
        json={"login": user.login, "password": "auto_test_other_password"},
    )

    assert again.status_code == 409
    assert again.json()["code"] == ErrorCode.LOGIN_ALREADY_TAKEN


# ---------------------------------------------------------------------------
# Login failures must not identify accounts
# ---------------------------------------------------------------------------


async def test_login_failures_are_indistinguishable_by_body_and_timing(
    client: AsyncClient, register_user
):
    """Both login failures must be identical, including how long they take.

    Identical bodies are not enough: returning early on an unknown login
    makes the two cases ~8 ms vs ~233 ms apart, which is a readable account
    enumeration oracle. The bound is far below the real bcrypt cost and far
    above a bare lookup miss, so it fails only if the hashing work is
    actually skipped.
    """
    user = await register_user()

    started = time.perf_counter()
    unknown = await _login(client, auto_test_login(), DEFAULT_PASSWORD)
    unknown_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    wrong_password = await _login(client, user.login, "auto_test_wrong")
    wrong_password_ms = (time.perf_counter() - started) * 1000

    assert unknown.status_code == wrong_password.status_code == 401
    assert unknown.json()["code"] == ErrorCode.INVALID_CREDENTIALS
    assert _envelope(unknown) == _envelope(wrong_password)
    # Nothing in the response may hint at which half was wrong.
    assert _envelope(unknown)["details"] is None
    assert unknown_ms > 100, (
        f"unknown login answered in {unknown_ms:.1f} ms vs "
        f"{wrong_password_ms:.1f} ms for a wrong password - the bcrypt work "
        "is being skipped, which leaks whether the account exists"
    )


# ---------------------------------------------------------------------------
# /auth/refresh
# ---------------------------------------------------------------------------


async def test_refresh_rotates_the_token_and_retires_the_presented_one(
    client: AsyncClient, register_user
):
    """Rotation: the presented token must die as the new one is issued.

    If the old token keeps working, a stolen refresh token stays valid for
    its whole lifetime no matter how often the real client refreshes.
    """
    user = await register_user()

    rotated = await _refresh(client, user.refresh_token)
    assert rotated.status_code == 200, rotated.text
    new_token = rotated.json()["refresh_token"]
    assert new_token != user.refresh_token

    reused = await _refresh(client, user.refresh_token)
    assert reused.status_code == 401
    assert reused.json()["code"] == ErrorCode.REFRESH_TOKEN_INVALID

    # The replacement is usable, so the rejection above is about the old
    # token and not about refresh being broken altogether.
    assert (await _refresh(client, new_token)).status_code == 200


@pytest.mark.parametrize("case", ["unknown", "expired"])
async def test_refresh_rejects_unknown_and_expired_tokens_with_distinct_codes(
    client: AsyncClient, register_user, session, case
):
    """An expired refresh token is not an invalid one.

    Both are 401, but the client has to tell "you have been logged out" from
    "this token was never yours"; the code is the only thing that carries it.
    """
    expected = {
        "unknown": ErrorCode.REFRESH_TOKEN_INVALID,
        "expired": ErrorCode.TOKEN_EXPIRED,
    }[case]

    if case == "unknown":
        token = "auto_test_never_issued_token"
    else:
        token = (await register_user()).refresh_token
        await _expire_refresh_token(session, token)

    response = await _refresh(client, token)

    assert response.status_code == 401
    assert response.json()["code"] == expected
    assert response.headers["WWW-Authenticate"] == "Bearer"


# ---------------------------------------------------------------------------
# /auth/logout
# ---------------------------------------------------------------------------


async def test_logout_revokes_the_callers_refresh_token(
    client: AsyncClient, register_user
):
    user = await register_user()

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": user.refresh_token},
        headers=user.headers,
    )
    assert response.status_code == 200, response.text

    after = await _refresh(client, user.refresh_token)
    assert after.status_code == 401
    assert after.json()["code"] == ErrorCode.REFRESH_TOKEN_INVALID


async def test_logout_revokes_an_expired_token(
    client: AsyncClient, register_user, session
):
    """Expiry must not block logout.

    The expiry check belongs on /auth/refresh. Refusing to delete an expired
    token here strands the row in the table with no way to clean it up.
    """
    user = await register_user()
    await _expire_refresh_token(session, user.refresh_token)

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": user.refresh_token},
        headers=user.headers,
    )

    assert response.status_code == 200, response.text


async def test_logout_cannot_revoke_another_users_token(
    client: AsyncClient, register_user
):
    """A refresh token may only be revoked by the user it belongs to.

    Presenting someone else's token must be rejected *and* leave that token
    usable - otherwise any authenticated caller can end anyone's session.
    """
    victim = await register_user()
    attacker = await register_user()

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": victim.refresh_token},
        headers=attacker.headers,
    )
    assert response.status_code == 401
    # Same answer as an unknown token: the endpoint must not double as a
    # probe for which tokens exist.
    assert response.json()["code"] == ErrorCode.REFRESH_TOKEN_INVALID

    survived = await _refresh(client, victim.refresh_token)
    assert survived.status_code == 200, survived.text


# ---------------------------------------------------------------------------
# Bearer token rejections (app/api/dependencies.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "expected_status", "expected_code"),
    [
        ("no_header", 401, ErrorCode.HTTP_ERROR),
        ("wrong_scheme", 401, ErrorCode.HTTP_ERROR),
        ("forged_signature", 401, ErrorCode.INVALID_TOKEN),
        ("expired", 401, ErrorCode.TOKEN_EXPIRED),
        ("no_subject", 401, ErrorCode.INVALID_TOKEN),
        ("subject_not_a_uuid", 401, ErrorCode.INVALID_TOKEN),
        ("user_gone", 401, ErrorCode.INVALID_TOKEN),
    ],
)
async def test_bearer_rejections_carry_distinct_codes(
    client: AsyncClient,
    register_user,
    monkeypatch,
    case: str,
    expected_status: int,
    expected_code: ErrorCode,
):
    """Every way of failing authentication answers 401 with a stable code.

    `expired` versus `invalid_token` is the split the client acts on: refresh
    the session, or send the user back to the login screen. The others must
    never become a 500 - a token with no `sub` once reached `UUID(None)`.

    `forged_signature` and `expired` both name a user who really exists, so
    the rejection can only come from the signature or the expiry - not from
    the account being missing. A malformed token is not a separate case here:
    it lands in the same `except jwt.PyJWTError`, and the two are told apart
    at the unit layer instead.
    """
    headers: dict[str, str] = {}
    if case == "wrong_scheme":
        headers = {"Authorization": "Basic auto_test_not_a_bearer"}
    elif case == "forged_signature":
        real_user = await register_user()
        headers = auth_headers(
            jwt.encode(
                {"sub": str(real_user.user_id)},
                FOREIGN_SECRET,
                algorithm=settings.security.algorithm,
            )
        )
    elif case == "expired":
        real_user = await register_user()
        monkeypatch.setattr(
            settings.security, "access_token_expire_minutes", -1
        )
        headers = auth_headers(
            create_access_token({"sub": str(real_user.user_id)})
        )
        monkeypatch.undo()
    elif case == "no_subject":
        headers = auth_headers(create_access_token({}))
    elif case == "subject_not_a_uuid":
        headers = auth_headers(create_access_token({"sub": "not-a-uuid"}))
    elif case == "user_gone":
        headers = auth_headers(create_access_token({"sub": str(uuid4())}))

    response = await client.get("/users/me", headers=headers)

    assert response.status_code == expected_status
    body = response.json()
    assert body["code"] == expected_code
    # An error envelope, not a bare FastAPI `detail`, and no stacktrace.
    assert body["request_id"]
    assert "Traceback" not in body["message"]


# ---------------------------------------------------------------------------
# Validation errors must not echo credentials
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        # `login` missing: pydantic reports loc=("body","login") and puts the
        # *whole body* in `input`, password included.
        ("/auth/register", {"password": "sup3rs3cret"}),
        # The password itself is what failed: the rejected value is the secret.
        ("/auth/register", {"login": "auto_test_x", "password": "sup3"}),
        ("/auth/login", {"login": "auto_test_x", "password": "sup3"}),
    ],
)
async def test_validation_error_never_echoes_the_password(
    client: AsyncClient, path: str, payload: dict
):
    response = await client.post(path, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == ErrorCode.REQUEST_VALIDATION_FAILED
    # A short non-hex secret: it cannot collide with the hex request_id.
    assert payload["password"] not in response.text
    # The report still names the offending field, so it stays actionable.
    assert response.json()["details"]["errors"]
