"""Test helpers: plain functions and types the tests call directly.

Why this module exists rather than living in `conftest.py`: conftest is
pytest's *fixture* file. Pytest imports it by itself, once per directory, and
it is the one module in the suite that is never imported by name. Importing it
anyway loads a second copy under a different module name, so anything defined
at module level - the engine included - then exists twice.

The split the suite follows:

* `tests/conftest.py`   - fixtures and pytest hooks only. Nothing imports it.
* `tests/helpers.py`    - behaviour: functions and types the tests call.
* `tests/test_data/`    - data: payloads, cases, and expected values.
"""

import uuid
from dataclasses import dataclass
from uuid import UUID

# Everything the suite creates carries this prefix, so any row that ever
# escapes the rollback is obvious and findable with one query.
AUTO_TEST_PREFIX = "auto_test_"


def auto_test_name(width: int = 8) -> str:
    """A unique, greppable name for anything the suite creates."""
    return f"{AUTO_TEST_PREFIX}{uuid.uuid4().hex[:width]}"


def auto_test_login() -> str:
    """A unique login that fits users.login (String(30))."""
    return auto_test_name()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


@dataclass(frozen=True)
class RegisteredUser:
    """Everything a test needs about a user it just created."""

    login: str
    password: str
    user_id: UUID
    access_token: str
    refresh_token: str

    @property
    def headers(self) -> dict[str, str]:
        return auth_headers(self.access_token)
