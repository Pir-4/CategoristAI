"""Credential scrubbing in the validation-error handler.

The e2e case in `tests/integration/test_auth.py` proves the wiring for one
flat body. These cases reach the shapes HTTP cannot easily produce: nested
objects, lists of objects, and token fields.
"""

import pytest

from app.api.errors import REDACTED, redact_validation_errors
from app.api.errors import _scrub as scrub

SECRET = "sup3rs3cret"


@pytest.mark.parametrize(
    ("label", "value", "expected"),
    [
        (
            "flat_password",
            {"login": "auto_test_x", "password": SECRET},
            {"login": "auto_test_x", "password": REDACTED},
        ),
        (
            "nested_body",
            {"user": {"login": "auto_test_x", "password": SECRET}},
            {"user": {"login": "auto_test_x", "password": REDACTED}},
        ),
        (
            "list_of_objects",
            {"users": [{"password": SECRET}, {"password": SECRET}]},
            {"users": [{"password": REDACTED}, {"password": REDACTED}]},
        ),
        (
            "every_credential_key",
            {
                "token": SECRET,
                "access_token": SECRET,
                "refresh_token": SECRET,
                "hashed_password": SECRET,
                "secret_key": SECRET,
                "authorization": SECRET,
            },
            {
                "token": REDACTED,
                "access_token": REDACTED,
                "refresh_token": REDACTED,
                "hashed_password": REDACTED,
                "secret_key": REDACTED,
                "authorization": REDACTED,
            },
        ),
        (
            # Everything that is not a credential must survive intact,
            # otherwise the error stops being diagnosable.
            "harmless_fields_survive",
            {"login": "auto_test_x", "count": 3, "nested": {"role": "user"}},
            {"login": "auto_test_x", "count": 3, "nested": {"role": "user"}},
        ),
    ],
)
def test_scrub_redacts_credentials_at_any_depth(label, value, expected):
    assert scrub(value) == expected


@pytest.mark.parametrize(
    ("label", "errors"),
    [
        (
            # pydantic puts the rejected value in `input` when the failing
            # field *is* the credential.
            "credential_field_failed",
            [
                {
                    "type": "string_too_short",
                    "loc": ("body", "password"),
                    "msg": "String should have at least 5 characters",
                    "input": SECRET,
                }
            ],
        ),
        (
            # ... and the *whole body* in `input` when another field failed.
            # Scrubbing only by `loc` would leak the password here.
            "other_field_failed",
            [
                {
                    "type": "missing",
                    "loc": ("body", "login"),
                    "msg": "Field required",
                    "input": {"password": SECRET},
                }
            ],
        ),
        (
            "nested_body_of_another_failure",
            [
                {
                    "type": "missing",
                    "loc": ("body", "user", "login"),
                    "msg": "Field required",
                    "input": {"user": {"password": SECRET}},
                }
            ],
        ),
    ],
)
def test_redact_validation_errors_never_returns_the_credential(label, errors):
    redacted = redact_validation_errors(errors)

    assert SECRET not in repr(redacted)
    # The diagnostic parts are untouched, so the client still learns which
    # field was wrong and why.
    assert [e["loc"] for e in redacted] == [e["loc"] for e in errors]
    assert [e["msg"] for e in redacted] == [e["msg"] for e in errors]
