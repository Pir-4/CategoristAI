"""The /accounts endpoints end to end: ownership, uniqueness, partial edits.

Every failure is pinned by its `code`, not by its status alone - a 404 that
started meaning something else would otherwise pass unnoticed. The second user
is registered through the real endpoint and creates their own account, so
"another user's account" is genuinely another user's, not a hand-written row.
"""

import pytest
from httpx import AsyncClient

from app.core import ErrorCode
from tests.helpers import RegisteredUser, auto_test_name
from tests.test_data.ledger import SEED_INSTITUTION_ACC_NAME

pytestmark = pytest.mark.asyncio(loop_scope="session")

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"

RENAMED = "auto_test_renamed"

# Every field of AccountUpdate, explicitly null. The service drops None
# values, so this must read as "change nothing" - exactly like `{}`.
ALL_FIELDS_NULL = {
    "name": None,
    "institution": None,
    "institution_acc_name": None,
    "is_active": None,
}


def account_payload(name: str) -> dict:
    return {
        "name": name,
        "institution": "revolut",
        "institution_acc_name": SEED_INSTITUTION_ACC_NAME,
    }


@pytest.mark.parametrize("operation", ["create", "rename"])
async def test_a_taken_account_name_is_rejected_on_create_and_rename(
    auth_client: AsyncClient, account_factory, operation: str
):
    """Name uniqueness is decided by the database, on both write paths.

    There is no pre-check to rely on - two concurrent requests would both pass
    one - so the IntegrityError from (user_id, name) has to come back as a 409
    with a code, never as a 500 with a stacktrace.
    """
    taken = await account_factory()

    if operation == "create":
        response = await auth_client.post(
            "/accounts", json=account_payload(taken["name"])
        )
    else:
        other = await account_factory()
        response = await auth_client.patch(
            f"/accounts/{other['id']}", json={"name": taken["name"]}
        )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == ErrorCode.ACCOUNT_NAME_ALREADY_TAKEN
    assert "Traceback" not in response.json()["message"]


@pytest.mark.parametrize(
    ("label", "target", "body"),
    [
        ("unknown_id", "unknown", {"name": RENAMED}),
        # The lookup must happen even when there is nothing to apply: an
        # empty body is not a licence to skip the ownership check.
        ("unknown_id_with_empty_body", "unknown", {}),
        # Somebody else's account answers exactly like a missing one. A 403
        # would confirm the id exists and make accounts enumerable.
        ("another_users_account", "foreign", {"name": RENAMED}),
    ],
)
async def test_patching_an_account_that_is_not_yours_is_not_found(
    auth_client: AsyncClient,
    register_user,
    label: str,
    target: str,
    body: dict,
):
    other: RegisteredUser = await register_user()
    created = await auth_client.post(
        "/accounts",
        json=account_payload(auto_test_name(6)),
        headers=other.headers,
    )
    assert created.status_code == 200, created.text
    account_id = created.json()["id"] if target == "foreign" else UNKNOWN_ID

    response = await auth_client.patch(f"/accounts/{account_id}", json=body)

    assert response.status_code == 404, f"{label}: {response.text}"
    assert response.json()["code"] == ErrorCode.ACCOUNT_NOT_FOUND


@pytest.mark.parametrize(
    ("label", "body"),
    [("empty_object", {}), ("every_field_null", ALL_FIELDS_NULL)],
)
async def test_an_empty_account_patch_returns_the_account_unchanged(
    auth_client: AsyncClient, account_factory, label: str, body: dict
):
    """Nothing to apply is a 200, not a write of NULLs.

    Dropping `exclude_none` would push `name=None` into a NOT NULL column, so
    the whole response body is compared, not just the status.
    """
    account = await account_factory()

    response = await auth_client.patch(f"/accounts/{account['id']}", json=body)

    assert response.status_code == 200, f"{label}: {response.text}"
    assert response.json() == account


async def test_listing_accounts_returns_only_the_callers_own(
    auth_client: AsyncClient, account_factory, register_user
):
    mine = await account_factory()
    other: RegisteredUser = await register_user()
    theirs = await auth_client.post(
        "/accounts",
        json=account_payload(auto_test_name(6)),
        headers=other.headers,
    )
    assert theirs.status_code == 200, theirs.text

    response = await auth_client.get("/accounts")

    assert response.status_code == 200, response.text
    listed = {account["id"] for account in response.json()}
    assert mine["id"] in listed
    assert theirs.json()["id"] not in listed
