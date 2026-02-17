"""HTTP Basic Auth for the web gateway."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from passlib.context import CryptContext  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its bcrypt hash."""
    result: bool = pwd_context.verify(plain_password, hashed_password)
    return result


def authenticate(
    username: str,
    password: str,
    auth_config: dict[str, Any] | None,
) -> bool:
    """Authenticate credentials against auth config.

    Returns True if:
    - Auth is disabled (config missing or enabled=False)
    - Credentials are valid
    """
    if not auth_config or not auth_config.get("enabled", False):
        return True

    expected_username = auth_config.get("username", "")
    password_hash = auth_config.get("password_hash", "")

    if not expected_username or not password_hash:
        return True  # No credentials configured = disabled

    # Constant-time username comparison to prevent timing attacks
    username_ok = secrets.compare_digest(
        username.encode("utf-8"),
        expected_username.encode("utf-8"),
    )

    password_ok = verify_password(password, password_hash)

    return username_ok and password_ok
