"""Authentication for web dashboard"""

import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext  # type: ignore[import-untyped]

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Basic Auth handler
security = HTTPBasic()


class AuthConfig:
    """Authentication configuration"""

    def __init__(self, enabled: bool = False, username: str = "", password_hash: str = ""):
        self.enabled = enabled
        self.username = username
        self.password_hash = password_hash

    @classmethod
    def from_config_dict(cls, config_dict: dict) -> "AuthConfig":
        """Create AuthConfig from config dictionary"""
        return cls(
            enabled=config_dict.get("enabled", False),
            username=config_dict.get("username", ""),
            password_hash=config_dict.get("password_hash", ""),
        )


# Global auth config - will be set by web app initialization
_auth_config: AuthConfig | None = None


def set_auth_config(config: AuthConfig) -> None:
    """Set global auth configuration"""
    global _auth_config
    _auth_config = config


def get_auth_config() -> AuthConfig | None:
    """Get global auth configuration"""
    return _auth_config


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    result: bool = pwd_context.verify(plain_password, hashed_password)
    return result


def get_password_hash(password: str) -> str:
    """Hash a password for storing"""
    result: str = pwd_context.hash(password)
    return result


def authenticate_user(username: str, password: str) -> bool:
    """Authenticate a user with username and password"""
    config = get_auth_config()
    if not config or not config.enabled:
        return True  # Auth disabled

    if username != config.username:
        return False

    return verify_password(password, config.password_hash)


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Dependency that requires HTTP Basic Auth.
    Returns username if authenticated, raises HTTPException otherwise.
    """
    config = get_auth_config()

    # If auth is disabled, allow access
    if not config or not config.enabled:
        return "anonymous"

    # Verify credentials
    is_valid = authenticate_user(credentials.username, credentials.password)

    # Use constant-time comparison to prevent timing attacks
    # (passlib already does this for password, but check username too)
    if not is_valid or not secrets.compare_digest(
        credentials.username.encode("utf-8"), config.username.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


def optional_auth(credentials: HTTPBasicCredentials | None = Depends(security)) -> str | None:
    """
    Optional auth dependency - doesn't require credentials if auth is disabled.
    Returns username if authenticated, None if no credentials provided.
    """
    config = get_auth_config()

    # If auth is disabled, allow access
    if not config or not config.enabled:
        return None

    # If credentials provided, verify them
    if credentials and authenticate_user(credentials.username, credentials.password):
        return credentials.username

    return None
