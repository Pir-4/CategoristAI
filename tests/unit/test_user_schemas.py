"""Schema-level guarantees: the public shape of a user and the input guards.

Pure pydantic and one unsaved SQLAlchemy instance - no database needed.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from app.core import UserRole
from app.models import User
from app.schemas import LoginRequest, UserCreate, UserRead, UserUpdate
from tests.test_data.users import USER_READ_FIELDS


def test_user_read_exposes_only_public_fields():
    """The one place that decides what leaves the service.

    Every user-returning endpoint serialises through `UserRead`, so a field
    added here leaks from all of them at once. `role` is on the list next to
    the hash on purpose: it tells an attacker which account is worth taking.
    """
    user = User(
        id=uuid4(),
        login="auto_test_reader",
        hashed_password="$2b$12$auto.test.hash.value.not.a.real.one",
        role=UserRole.ADMIN,
        created_at=datetime.now(UTC),
    )

    public = UserRead.model_validate(user)

    assert set(public.model_dump()) == USER_READ_FIELDS
    assert user.hashed_password not in public.model_dump_json()
    assert str(UserRole.ADMIN) not in public.model_dump_json()


@pytest.mark.parametrize(
    ("schema", "payload", "is_valid"),
    [
        # --- real-world shapes: the logins in the database are 5-8 chars ---
        (UserCreate, {"login": "auto_test_x", "password": "12345"}, True),
        (LoginRequest, {"login": "auto_test_x", "password": "12345"}, True),
        (UserUpdate, {"login": "auto_test_x"}, True),
        (UserUpdate, {"password": "12345"}, True),
        # A no-op patch is allowed: every field is optional.
        (UserUpdate, {}, True),
        # --- defensive guards, not seen in real data ---
        # A four-character password must not be accepted anywhere.
        (UserCreate, {"login": "auto_test_x", "password": "1234"}, False),
        (LoginRequest, {"login": "auto_test_x", "password": "1234"}, False),
        (UserUpdate, {"password": "1234"}, False),
        # users.login is String(30); a longer value would be truncated or
        # rejected by the database instead of by validation.
        (UserCreate, {"login": "a" * 31, "password": "12345"}, False),
        (UserCreate, {"login": "a" * 30, "password": "12345"}, True),
        (UserUpdate, {"login": "a" * 31}, False),
        # An empty login is not a login.
        (UserCreate, {"login": "", "password": "12345"}, False),
        (UserUpdate, {"login": ""}, False),
    ],
)
def test_credential_schemas_enforce_their_boundaries(
    schema: type[BaseModel], payload: dict, is_valid: bool
):
    if is_valid:
        assert schema.model_validate(payload)
        return

    with pytest.raises(ValidationError):
        schema.model_validate(payload)
