"""Password hashing helpers (PBKDF2-HMAC-SHA256, stdlib only)."""

import hashlib
import hmac
import secrets

_ITERATIONS = 120_000


def hash_password(password: str) -> str:
    """Hash a password, returning 'salt_hex$hash_hex' for storage."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored 'salt_hex$hash_hex' value."""
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return hmac.compare_digest(actual, expected)


def new_wheel_code() -> str:
    """Generate a short, unguessable wheel code (e.g. 'k3F9aQz2')."""
    return secrets.token_urlsafe(6)
