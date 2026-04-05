from app.core.security import hash_password, verify_password


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
