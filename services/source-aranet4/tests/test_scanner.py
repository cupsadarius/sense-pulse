"""Tests for Aranet4 BLE scanner."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from aranet4_svc.scanner import Aranet4Scanner


def _make_advertisement(
    mac: str,
    name: str = "Aranet4 12345",
    rssi: int = -60,
    co2: int = 450,
    temperature: float = 22.1,
    humidity: int = 45,
    pressure: float = 1013.2,
    battery: int = 85,
    has_readings: bool = True,
) -> SimpleNamespace:
    """Create a mock Aranet4 advertisement."""
    device = SimpleNamespace(address=mac, name=name)
    readings = None
    if has_readings:
        readings = SimpleNamespace(
            co2=co2,
            temperature=temperature,
            humidity=humidity,
            pressure=pressure,
            battery=battery,
        )
    return SimpleNamespace(device=device, readings=readings, rssi=rssi)


def _make_mock_aranet4(fake_find_nearby):
    """Create a mock aranet4 module with client._find_nearby set to the given coroutine."""
    mock_module = MagicMock()
    mock_module.client._find_nearby = fake_find_nearby
    return mock_module


class TestAranet4ScannerScan:
    """Tests for Aranet4Scanner.scan()."""

    @pytest.fixture
    def scanner(self) -> Aranet4Scanner:
        return Aranet4Scanner()

    async def test_scan_empty_sensors(self, scanner: Aranet4Scanner) -> None:
        result = await scanner.scan([], timeout=5)
        assert result == {}

    async def test_scan_finds_configured_sensor(self, scanner: Aranet4Scanner) -> None:
        sensors = [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}]
        adv = _make_advertisement("AA:BB:CC:DD:EE:01", co2=500, temperature=23.5)

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv)

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert "office" in result
        reading = result["office"]
        assert reading is not None
        assert reading.co2 == 500
        assert reading.temperature == 23.5
        assert reading.humidity == 45
        assert reading.pressure == 1013.2
        assert reading.battery == 85
        assert reading.timestamp > 0

    async def test_scan_missing_sensor_returns_none(self, scanner: Aranet4Scanner) -> None:
        sensors = [
            {"label": "office", "mac": "AA:BB:CC:DD:EE:01"},
            {"label": "bedroom", "mac": "AA:BB:CC:DD:EE:02"},
        ]
        adv = _make_advertisement("AA:BB:CC:DD:EE:01")

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv)

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is not None
        assert result["bedroom"] is None

    async def test_scan_multiple_sensors(self, scanner: Aranet4Scanner) -> None:
        sensors = [
            {"label": "office", "mac": "AA:BB:CC:DD:EE:01"},
            {"label": "bedroom", "mac": "AA:BB:CC:DD:EE:02"},
        ]
        adv1 = _make_advertisement("AA:BB:CC:DD:EE:01", co2=450)
        adv2 = _make_advertisement("AA:BB:CC:DD:EE:02", co2=800)

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv1)
            callback(adv2)

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is not None
        assert result["office"].co2 == 450
        assert result["bedroom"] is not None
        assert result["bedroom"].co2 == 800

    async def test_scan_ignores_duplicate_advertisements(self, scanner: Aranet4Scanner) -> None:
        sensors = [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}]
        adv1 = _make_advertisement("AA:BB:CC:DD:EE:01", co2=450)
        adv2 = _make_advertisement("AA:BB:CC:DD:EE:01", co2=999)

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv1)
            callback(adv2)  # duplicate, should be ignored

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is not None
        assert result["office"].co2 == 450  # First reading kept

    async def test_scan_handles_import_error(self, scanner: Aranet4Scanner) -> None:
        sensors = [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}]

        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "aranet4":
                raise ImportError("no aranet4")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is None

    async def test_scan_handles_ble_error(self, scanner: Aranet4Scanner) -> None:
        sensors = [{"label": "office", "mac": "AA:BB:CC:DD:EE:01"}]

        async def failing_find_nearby(callback, duration=10):  # noqa: ARG001
            raise RuntimeError("BLE adapter not found")

        mock_aranet4 = _make_mock_aranet4(failing_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is None

    async def test_scan_case_insensitive_mac(self, scanner: Aranet4Scanner) -> None:
        """MAC addresses should be compared case-insensitively."""
        sensors = [{"label": "office", "mac": "aa:bb:cc:dd:ee:01"}]
        adv = _make_advertisement("AA:BB:CC:DD:EE:01", co2=500)

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv)

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            result = await scanner.scan(sensors, timeout=5)

        assert result["office"] is not None
        assert result["office"].co2 == 500


class TestAranet4ScannerDiscover:
    """Tests for Aranet4Scanner.discover()."""

    @pytest.fixture
    def scanner(self) -> Aranet4Scanner:
        return Aranet4Scanner()

    async def test_discover_finds_devices(self, scanner: Aranet4Scanner) -> None:
        adv1 = _make_advertisement("AA:BB:CC:DD:EE:01", name="Aranet4 12345", rssi=-50)
        adv2 = _make_advertisement("AA:BB:CC:DD:EE:02", name="Aranet4 67890", rssi=-70)

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv1)
            callback(adv2)

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            devices = await scanner.discover(timeout=5)

        assert len(devices) == 2
        assert devices[0]["name"] == "Aranet4 12345"
        assert devices[0]["mac"] == "AA:BB:CC:DD:EE:01"
        assert devices[0]["rssi"] == -50
        assert devices[1]["name"] == "Aranet4 67890"
        assert devices[1]["mac"] == "AA:BB:CC:DD:EE:02"

    async def test_discover_deduplicates(self, scanner: Aranet4Scanner) -> None:
        adv = _make_advertisement("AA:BB:CC:DD:EE:01", name="Aranet4 12345")

        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            callback(adv)
            callback(adv)  # duplicate

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            devices = await scanner.discover(timeout=5)

        assert len(devices) == 1

    async def test_discover_empty(self, scanner: Aranet4Scanner) -> None:
        async def fake_find_nearby(callback, duration=10):  # noqa: ARG001
            pass  # no devices found

        mock_aranet4 = _make_mock_aranet4(fake_find_nearby)
        with patch.dict("sys.modules", {"aranet4": mock_aranet4}):
            devices = await scanner.discover(timeout=5)

        assert devices == []

    async def test_discover_handles_import_error(self, scanner: Aranet4Scanner) -> None:
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "aranet4":
                raise ImportError("no aranet4")
            return real_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", side_effect=fake_import):
            devices = await scanner.discover(timeout=5)

        assert devices == []
