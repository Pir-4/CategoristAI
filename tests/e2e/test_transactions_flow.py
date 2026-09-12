"""The /transactions endpoints end to end: ownership, category authorisation,
partial edits and the identity constraint.

Transactions and categories are seeded through the models (see the factories
in conftest): no endpoint creates either for a user other than the caller, and
"a row that is not yours" is the whole point of most of these cases. Failures
are pinned by their `code`, never by status alone.
"""

import pytest
from httpx import AsyncClient

from app.core import ErrorCode
from tests.helpers import RegisteredUser

pytestmark = pytest.mark.asyncio(loop_scope="session")

UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"

EDITED_MERCHANT = "auto_test_merchant"

# Every field of TransactionUpdate, explicitly null.
ALL_FIELDS_NULL = {"category_id": None, "status": None, "merchant": None}


async def test_a_category_owned_by_someone_else_cannot_be_attached(
    client: AsyncClient, register_user, category_factory, transaction_factory
):
    """The authorisation hole: a foreign category_id must not be attachable.

    A foreign key only proves the category exists *somewhere*, so without the
    `user_id` predicate in `get_category_by_id` this 422 becomes a 200 and one
    user's transaction ends up filed under another user's category.

    The answer must also be identical to the one for a category that exists
    nowhere - a different code, status or message would turn the endpoint into
    an oracle for probing other people's category ids.
    """
    victim: RegisteredUser = await register_user()
    attacker: RegisteredUser = await register_user()
    victim_category = await category_factory(victim.user_id)
    own_category = await category_factory(attacker.user_id)
    transaction = await transaction_factory(attacker.user_id)
    url = f"/transactions/{transaction.id}"

    stolen = await client.patch(
        url,
        json={"category_id": str(victim_category.id)},
        headers=attacker.headers,
    )
    ghost = await client.patch(
        url, json={"category_id": UNKNOWN_ID}, headers=attacker.headers
    )
    owned = await client.patch(
        url,
        json={"category_id": str(own_category.id)},
        headers=attacker.headers,
    )

    assert stolen.status_code == 422, stolen.text
    assert stolen.json()["code"] == ErrorCode.TRANSACTION_CATEGORY_NOT_FOUND
    assert (stolen.status_code, stolen.json()["code"]) == (
        ghost.status_code,
        ghost.json()["code"],
    )
    assert stolen.json()["message"] == ghost.json()["message"]

    # The caller's own category still works - the fix must not lock everyone
    # out - and it is what the stored row ends up carrying.
    assert owned.status_code == 200, owned.text
    assert owned.json()["category_id"] == str(own_category.id)

    listed = await client.get("/transactions", headers=attacker.headers)
    stored = {row["id"]: row["category_id"] for row in listed.json()}
    assert stored[str(transaction.id)] == str(own_category.id)


@pytest.mark.parametrize(
    ("label", "target", "body"),
    [
        ("unknown_id", "unknown", {"merchant": EDITED_MERCHANT}),
        # An empty body must not short-circuit the ownership lookup.
        ("unknown_id_with_empty_body", "unknown", {}),
        # Somebody else's transaction is a 404, not a 403: a 403 would
        # confirm the id exists and make transactions enumerable.
        ("another_users_transaction", "foreign", {"merchant": EDITED_MERCHANT}),
    ],
)
async def test_patching_a_transaction_that_is_not_yours_is_not_found(
    client: AsyncClient,
    register_user,
    transaction_factory,
    label: str,
    target: str,
    body: dict,
):
    user: RegisteredUser = await register_user()
    other: RegisteredUser = await register_user()
    foreign = await transaction_factory(other.user_id)
    transaction_id = str(foreign.id) if target == "foreign" else UNKNOWN_ID

    response = await client.patch(
        f"/transactions/{transaction_id}", json=body, headers=user.headers
    )

    assert response.status_code == 404, f"{label}: {response.text}"
    assert response.json()["code"] == ErrorCode.TRANSACTION_NOT_FOUND


@pytest.mark.parametrize(
    ("label", "body"),
    [("empty_object", {}), ("every_field_null", ALL_FIELDS_NULL)],
)
async def test_an_empty_transaction_patch_returns_the_row_unchanged(
    client: AsyncClient,
    register_user,
    transaction_factory,
    label: str,
    body: dict,
):
    """Nothing to apply is a 200, not a write of NULLs.

    Without `exclude_none` the merchant would be overwritten with NULL in a
    NOT NULL column, so the returned row is compared field by field.
    """
    user: RegisteredUser = await register_user()
    transaction = await transaction_factory(user.user_id)
    merchant = transaction.merchant

    response = await client.patch(
        f"/transactions/{transaction.id}", json=body, headers=user.headers
    )

    assert response.status_code == 200, f"{label}: {response.text}"
    assert response.json()["merchant"] == merchant
    assert response.json()["category_id"] is None
    assert response.json()["status"] == "pending"


async def test_editing_a_merchant_into_an_existing_identity_is_a_duplicate(
    client: AsyncClient, register_user, transaction_factory
):
    """Two rows that differ only by merchant must not be merged by an edit.

    Identity is (account_id, start_date, merchant, amount, fee, occurrence),
    and the real savings exports do contain rows identical in everything but
    the description - so renaming one onto another is reachable. The unique
    violation has to be translated into a 409, not left to surface as a 500.
    """
    user: RegisteredUser = await register_user()
    first = await transaction_factory(user.user_id, merchant="auto_test_shop_a")
    second = await transaction_factory(
        user.user_id, account_id=first.account_id, merchant="auto_test_shop_b"
    )
    target_url = f"/transactions/{second.id}"

    response = await client.patch(
        target_url, json={"merchant": first.merchant}, headers=user.headers
    )

    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == ErrorCode.DUPLICATE_TRANSACTION
    # The response has to name what the caller sent, not just that it failed.
    assert body["details"]["fields"] == ["merchant"]
    assert "Traceback" not in body["message"]


async def test_listing_transactions_returns_only_the_callers_own(
    client: AsyncClient, register_user, transaction_factory
):
    user: RegisteredUser = await register_user()
    other: RegisteredUser = await register_user()
    mine = await transaction_factory(user.user_id)
    theirs = await transaction_factory(other.user_id)

    response = await client.get("/transactions", headers=user.headers)

    assert response.status_code == 200, response.text
    listed = {row["id"] for row in response.json()}
    assert str(mine.id) in listed
    assert str(theirs.id) not in listed
