"""Tests for web authentication"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPBasicCredentials

from sense_pulse.web.auth import (
    AuthConfig,
    authenticate_user,
    get_auth_config,
    get_password_hash,
    require_auth,
    set_auth_config,
    verify_password,
)


class TestPasswordHashing:
    """Test password hashing functions"""

    def test_hash_and_verify_password(self):
        """Test password hashing and verification"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed != password
        assert verify_password(password, hashed) is True
        assert verify_password("wrong_password", hashed) is False

    def test_hash_produces_different_hashes(self):
        """Test that same password produces different hashes (salt)"""
        password = "test_password"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestAuthConfig:
    """Test AuthConfig class"""

    def test_auth_config_from_dict(self):
        """Test creating AuthConfig from dict"""
        config_dict = {
            "enabled": True,
            "username": "testuser",
            "password_hash": "hash123",
        }

        config = AuthConfig.from_config_dict(config_dict)

        assert config.enabled is True
        assert config.username == "testuser"
        assert config.password_hash == "hash123"

    def test_auth_config_from_dict_with_defaults(self):
        """Test creating AuthConfig from empty dict uses defaults"""
        config = AuthConfig.from_config_dict({})

        assert config.enabled is False
        assert config.username == ""
        assert config.password_hash == ""


class TestAuthConfigGlobal:
    """Test global auth config management"""

    def test_set_and_get_auth_config(self):
        """Test setting and getting global auth config"""
        config = AuthConfig(enabled=True, username="admin", password_hash="hash")

        set_auth_config(config)
        retrieved = get_auth_config()

        assert retrieved is config
        assert retrieved.enabled is True
        assert retrieved.username == "admin"


class TestAuthenticateUser:
    """Test user authentication"""

    def test_authenticate_with_auth_disabled(self):
        """Test authentication when auth is disabled"""
        config = AuthConfig(enabled=False)
        set_auth_config(config)

        # Should always succeed when disabled
        assert authenticate_user("any", "password") is True

    def test_authenticate_with_valid_credentials(self):
        """Test authentication with valid credentials"""
        password = "secure_password"
        hashed = get_password_hash(password)

        config = AuthConfig(enabled=True, username="admin", password_hash=hashed)
        set_auth_config(config)

        assert authenticate_user("admin", password) is True

    def test_authenticate_with_invalid_username(self):
        """Test authentication with wrong username"""
        password = "secure_password"
        hashed = get_password_hash(password)

        config = AuthConfig(enabled=True, username="admin", password_hash=hashed)
        set_auth_config(config)

        assert authenticate_user("wrong_user", password) is False

    def test_authenticate_with_invalid_password(self):
        """Test authentication with wrong password"""
        password = "secure_password"
        hashed = get_password_hash(password)

        config = AuthConfig(enabled=True, username="admin", password_hash=hashed)
        set_auth_config(config)

        assert authenticate_user("admin", "wrong_password") is False


class TestRequireAuth:
    """Test require_auth dependency"""

    def test_require_auth_when_disabled(self):
        """Test require_auth allows access when auth disabled"""
        config = AuthConfig(enabled=False)
        set_auth_config(config)

        credentials = HTTPBasicCredentials(username="any", password="any")
        result = require_auth(credentials)

        assert result == "anonymous"

    def test_require_auth_with_valid_credentials(self):
        """Test require_auth with valid credentials"""
        password = "secure_password"
        hashed = get_password_hash(password)

        config = AuthConfig(enabled=True, username="admin", password_hash=hashed)
        set_auth_config(config)

        credentials = HTTPBasicCredentials(username="admin", password=password)
        result = require_auth(credentials)

        assert result == "admin"

    def test_require_auth_with_invalid_credentials(self):
        """Test require_auth raises exception with invalid credentials"""
        password = "secure_password"
        hashed = get_password_hash(password)

        config = AuthConfig(enabled=True, username="admin", password_hash=hashed)
        set_auth_config(config)

        credentials = HTTPBasicCredentials(username="admin", password="wrong")

        with pytest.raises(HTTPException) as exc_info:
            require_auth(credentials)

        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in exc_info.value.detail
