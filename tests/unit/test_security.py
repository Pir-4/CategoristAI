import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plain():
    plain_pass = "test_password"
    hash_pass = hash_password(plain_pass)
    assert hash_pass != plain_pass, "Password wasn't hashed"


def test_hashes_are_unique():
    plain_pass = "test_password"
    hash_pass = hash_password(plain_pass)
    hash_pass_2 = hash_password(plain_pass)
    assert hash_pass != hash_pass_2, "Hashes are equal"


def test_verify_correct_password():
    plain_pass = "test_password"
    hash_pass = hash_password(plain_pass)
    assert verify_password(plain_pass, hash_pass)


def test_verify_wrong_password():
    plain_pass = "test_password"
    wrong_pass = "test_password2"
    hash_pass = hash_password(plain_pass)
    assert not verify_password(wrong_pass, hash_pass)


def test_create_access_token_returns_string():
    token = create_access_token({"sub": "test-id"})
    assert isinstance(token, str)


def test_access_token_contains_sub():
    token = create_access_token({"sub": "test-id"})
    payload = decode_access_token(token)
    assert payload["sub"] == "test-id"


def test_decode_invalid_token_raises():
    with pytest.raises(ValueError):
        decode_access_token("this.is.garbage")
