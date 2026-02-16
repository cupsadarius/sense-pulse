"""Tests for sense_common.config helpers."""

from sense_common.config import (
    get_config_value,
    get_env,
    get_env_bool,
    get_env_float,
    get_env_int,
    get_env_json,
    get_redis_url,
)


class TestGetEnv:
    def test_existing_var(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "hello")
        assert get_env("TEST_VAR") == "hello"

    def test_missing_var_default(self):
        assert get_env("NONEXISTENT_VAR_12345", "fallback") == "fallback"

    def test_missing_var_empty_default(self):
        assert get_env("NONEXISTENT_VAR_12345") == ""


class TestGetEnvInt:
    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "42")
        assert get_env_int("TEST_INT") == 42

    def test_invalid_int(self, monkeypatch):
        monkeypatch.setenv("TEST_INT", "not_a_number")
        assert get_env_int("TEST_INT", 10) == 10

    def test_missing(self):
        assert get_env_int("NONEXISTENT_VAR_12345", 99) == 99


class TestGetEnvFloat:
    def test_valid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "3.14")
        assert get_env_float("TEST_FLOAT") == 3.14

    def test_invalid_float(self, monkeypatch):
        monkeypatch.setenv("TEST_FLOAT", "abc")
        assert get_env_float("TEST_FLOAT", 1.0) == 1.0

    def test_missing(self):
        assert get_env_float("NONEXISTENT_VAR_12345", 2.5) == 2.5


class TestGetEnvBool:
    def test_true_values(self, monkeypatch):
        for val in ("true", "True", "TRUE", "1", "yes", "YES"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert get_env_bool("TEST_BOOL") is True

    def test_false_values(self, monkeypatch):
        for val in ("false", "0", "no", "anything_else"):
            monkeypatch.setenv("TEST_BOOL", val)
            assert get_env_bool("TEST_BOOL") is False

    def test_missing(self):
        assert get_env_bool("NONEXISTENT_VAR_12345") is False
        assert get_env_bool("NONEXISTENT_VAR_12345", True) is True


class TestGetEnvJson:
    def test_valid_json(self, monkeypatch):
        monkeypatch.setenv("TEST_JSON", '[{"label": "office", "mac": "AA:BB"}]')
        result = get_env_json("TEST_JSON")
        assert result == [{"label": "office", "mac": "AA:BB"}]

    def test_invalid_json(self, monkeypatch):
        monkeypatch.setenv("TEST_JSON", "not-json")
        assert get_env_json("TEST_JSON", []) == []

    def test_missing(self):
        assert get_env_json("NONEXISTENT_VAR_12345", {"default": True}) == {"default": True}


class TestGetRedisUrl:
    def test_default(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        assert get_redis_url() == "redis://redis:6379"

    def test_custom(self, monkeypatch):
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6380")
        assert get_redis_url() == "redis://localhost:6380"


class TestGetConfigValue:
    def test_redis_config_first(self):
        """Redis config takes priority over env."""
        result = get_config_value(
            {"location": "London"},
            "WEATHER_LOCATION",
            default="",
        )
        assert result == "London"

    def test_env_fallback(self, monkeypatch):
        """Falls back to env when Redis config is None."""
        monkeypatch.setenv("WEATHER_LOCATION", "Paris")
        result = get_config_value(None, "WEATHER_LOCATION", default="")
        assert result == "Paris"

    def test_default_fallback(self):
        """Falls back to default when both Redis and env are missing."""
        result = get_config_value(None, "NONEXISTENT_VAR_12345", default="Berlin")
        assert result == "Berlin"

    def test_env_fallback_int(self, monkeypatch):
        monkeypatch.setenv("ARANET4_TIMEOUT", "15")
        result = get_config_value(None, "ARANET4_TIMEOUT", default=10)
        assert result == 15

    def test_env_fallback_bool(self, monkeypatch):
        monkeypatch.setenv("SLEEP_DISABLE_PI_LEDS", "true")
        result = get_config_value(None, "SLEEP_DISABLE_PI_LEDS", default=False)
        assert result is True

    def test_env_fallback_json_list(self, monkeypatch):
        monkeypatch.setenv("ARANET4_SENSORS", '[{"label":"office","mac":"AA:BB"}]')
        result = get_config_value(None, "ARANET4_SENSORS", default=[])
        assert result == [{"label": "office", "mac": "AA:BB"}]

    def test_custom_config_key(self):
        result = get_config_value(
            {"host": "http://pihole"},
            "PIHOLE_HOST",
            default="",
            config_key="host",
        )
        assert result == "http://pihole"

    def test_redis_config_key_missing(self, monkeypatch):
        """If key not in Redis config, fall through to env."""
        monkeypatch.setenv("WEATHER_LOCATION", "Tokyo")
        result = get_config_value({"other": "value"}, "WEATHER_LOCATION", default="")
        assert result == "Tokyo"
