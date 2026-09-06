"""Pure crypto layer: no database, no HTTP, no mocks.

The only test double here is the clock, and even that is done by moving the
configured token lifetime rather than by patching `datetime`.
"""

import time

import jwt
import pytest

from app.core import ErrorCode, settings
from app.core.exceptions import AuthError
from app.core.security import (
    burn_password_time,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

PASSWORD = "auto_test_password"

# Long enough that PyJWT does not warn about the key length.
FOREIGN_SECRET = "auto_test_secret_that_is_not_ours_0123456789"


def test_hash_verifies_the_original_and_rejects_everything_else():
    hashed = hash_password(PASSWORD)

    assert hashed != PASSWORD
    assert verify_password(PASSWORD, hashed) is True
    assert verify_password(PASSWORD + "x", hashed) is False
    # A prefix must not pass: bcrypt compares the whole string, and a
    # truncating comparison would accept every password starting the same way.
    assert verify_password(PASSWORD[:-1], hashed) is False


def test_each_hash_uses_a_fresh_salt():
    """Two hashes of one password must differ, yet both must verify.

    Equal hashes mean the salt is fixed, which makes the whole table
    attackable with one precomputed set.
    """
    first, second = hash_password(PASSWORD), hash_password(PASSWORD)

    assert first != second
    assert verify_password(PASSWORD, first)
    assert verify_password(PASSWORD, second)


def test_burn_password_time_costs_as_much_as_a_real_verify():
    """The unknown-login branch must pay the same bcrypt price.

    Compared against a real verify rather than an absolute bound, so the
    parity survives a change of cost parameter - and so a `_dummy_hash` built
    with cheaper rounds than `hash_password` is caught.
    """
    hashed = hash_password(PASSWORD)

    started = time.perf_counter()
    verify_password("wrong_password", hashed)
    verify_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    burn_password_time()
    burn_ms = (time.perf_counter() - started) * 1000

    assert 0.3 < burn_ms / verify_ms < 3.0, (
        f"burn_password_time took {burn_ms:.1f} ms against "
        f"{verify_ms:.1f} ms for a real verify - the two failure branches of "
        "/auth/login are distinguishable by response time"
    )


def test_access_token_carries_its_subject_and_an_expiry():
    payload = decode_access_token(create_access_token({"sub": "test-subject"}))

    assert payload["sub"] == "test-subject"
    # Without `exp` a leaked token is valid forever.
    assert payload["exp"] > time.time()


@pytest.mark.parametrize(
    "case",
    ["garbage", "foreign_secret", "expired"],
)
def test_decode_rejects_bad_tokens_with_distinct_codes(case, monkeypatch):
    """Expiry and invalidity must not collapse into one code.

    The client decides "refresh me" versus "send the user back to the login
    screen" from this code alone.
    """
    expected = {
        "garbage": ErrorCode.INVALID_TOKEN,
        "foreign_secret": ErrorCode.INVALID_TOKEN,
        "expired": ErrorCode.TOKEN_EXPIRED,
    }[case]

    if case == "garbage":
        token = "this.is.garbage"
    elif case == "foreign_secret":
        token = jwt.encode(
            {"sub": "test-subject"},
            FOREIGN_SECRET,
            algorithm=settings.security.algorithm,
        )
    else:
        monkeypatch.setattr(
            settings.security, "access_token_expire_minutes", -1
        )
        token = create_access_token({"sub": "test-subject"})

    with pytest.raises(AuthError) as raised:
        decode_access_token(token)

    assert raised.value.code == expected
    # The token itself must never travel with the error.
    assert token not in str(raised.value)
