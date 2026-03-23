import bcrypt


def hash_password(plain: str) -> str:
    b_plain = plain.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hash_plain = bcrypt.hashpw(b_plain, salt)
    return hash_plain.decode()


def verify_password(plain: str, hashed: str) -> bool:
    b_plain = plain.encode("utf-8")
    b_hashed = hashed.encode("utf-8")
    return bcrypt.checkpw(b_plain, b_hashed)
