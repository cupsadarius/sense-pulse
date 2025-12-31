"""Tests for HardwareService."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from sense_pulse.services.hardware import HardwareService, MatrixState, SensorReadings


class TestHardwareServiceInitialization:
    """Test HardwareService initialization."""

    @pytest.mark.asyncio
    async def test_initialize_without_hardware(self):
        """Test initialization when SenseHat is not available."""
        service = HardwareService()

        # Mock the import to raise ImportError
        with patch.dict(sys.modules, {"sense_hat": None}):
            result = await service.initialize()

        assert result is False
        assert service.is_initialized is True
        assert service.is_available is False

    @pytest.mark.asyncio
    async def test_initialize_with_exception(self):
        """Test initialization when SenseHat raises exception."""
        service = HardwareService()

        # Create a mock module that raises when SenseHat is instantiated
        mock_module = MagicMock()
        mock_module.SenseHat.side_effect = RuntimeError("Hardware not found")

        with patch.dict(sys.modules, {"sense_hat": mock_module}):
            result = await service.initialize()

        assert result is False
        assert service.is_initialized is True
        assert service.is_available is False

    @pytest.mark.asyncio
    async def test_initialize_twice_is_noop(self):
        """Test that double initialization is safe."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        result = await service.initialize()

        assert result is False  # Returns cached availability

    @pytest.mark.asyncio
    async def test_shutdown_clears_state(self):
        """Test shutdown clears all state."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        await service.shutdown()

        assert service.is_initialized is False
        assert service.is_available is False

    @pytest.mark.asyncio
    async def test_shutdown_with_hardware_clears_display(self):
        """Test shutdown clears display when hardware available."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        service._sense_hat = mock_sense_hat

        await service.shutdown()

        mock_sense_hat.clear.assert_called_once()
        assert service.is_initialized is False
        assert service.is_available is False
        assert service.sense_hat is None


class TestHardwareServiceDisplayState:
    """Test display state tracking."""

    def test_set_display_mode(self):
        """Test setting display mode."""
        service = HardwareService()

        service.set_display_mode("scrolling")

        assert service._current_mode == "scrolling"

    def test_set_web_rotation_offset_valid(self):
        """Test setting valid web rotation offset."""
        service = HardwareService()

        service.set_web_rotation_offset(180)

        assert service.web_rotation_offset == 180

    def test_set_web_rotation_offset_invalid(self):
        """Test setting invalid web rotation offset is ignored."""
        service = HardwareService()
        original = service.web_rotation_offset

        service.set_web_rotation_offset(45)  # Invalid

        assert service.web_rotation_offset == original

    def test_initial_state(self):
        """Test initial state values."""
        service = HardwareService()

        assert service.is_available is False
        assert service.is_initialized is False
        assert service.current_rotation == 0
        assert service.web_rotation_offset == 90
        assert service._current_mode == "idle"


class TestHardwareServiceWithoutHardware:
    """Test service behavior when hardware is unavailable."""

    @pytest.mark.asyncio
    async def test_get_sensor_readings_unavailable(self):
        """Test sensor readings when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        readings = await service.get_sensor_readings()

        assert isinstance(readings, SensorReadings)
        assert readings.available is False
        assert readings.temperature is None
        assert readings.humidity is None
        assert readings.pressure is None

    @pytest.mark.asyncio
    async def test_set_pixels_unavailable(self):
        """Test set_pixels when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        result = await service.set_pixels([[0, 0, 0]] * 64)

        assert result is False

    @pytest.mark.asyncio
    async def test_clear_display_unavailable(self):
        """Test clear_display when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        result = await service.clear_display()

        assert result is False

    @pytest.mark.asyncio
    async def test_get_matrix_state_unavailable(self):
        """Test matrix state when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        state = await service.get_matrix_state()

        assert isinstance(state, MatrixState)
        assert state.available is False
        assert len(state.pixels) == 64

    @pytest.mark.asyncio
    async def test_show_message_unavailable(self):
        """Test show_message when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        result = await service.show_message("Hello")

        assert result is False

    def test_get_matrix_state_dict_unavailable(self):
        """Test get_matrix_state_dict when hardware unavailable."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        state_dict = service.get_matrix_state_dict()

        assert isinstance(state_dict, dict)
        assert state_dict["available"] is False
        assert len(state_dict["pixels"]) == 64
        assert state_dict["mode"] == "idle"
        assert state_dict["rotation"] == 0
        assert state_dict["web_offset"] == 90


class TestHardwareServiceRotation:
    """Test rotation handling."""

    @pytest.mark.asyncio
    async def test_set_rotation_invalid_value(self):
        """Test that invalid rotation values are rejected."""
        service = HardwareService()
        service._initialized = True
        service._available = False

        result = await service.set_rotation(45)  # Invalid

        assert result is False
        assert service.current_rotation == 0  # Unchanged

    @pytest.mark.asyncio
    async def test_set_rotation_valid_values(self):
        """Test that valid rotation values are accepted."""
        service = HardwareService()
        service._initialized = True
        service._available = False  # Will track state even without hardware

        for rotation in (0, 90, 180, 270):
            result = await service.set_rotation(rotation)
            assert result is False  # No hardware, but state is tracked
            assert service.current_rotation == rotation

    @pytest.mark.asyncio
    async def test_set_rotation_with_hardware(self):
        """Test set_rotation calls hardware when available."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        service._sense_hat = mock_sense_hat

        result = await service.set_rotation(90)

        assert result is True
        assert service.current_rotation == 90
        mock_sense_hat.set_rotation.assert_called_once_with(90)


class TestHardwareServiceWithMockedHardware:
    """Test service with mocked hardware."""

    @pytest.mark.asyncio
    async def test_set_pixels_with_hardware(self):
        """Test set_pixels calls hardware when available."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        service._sense_hat = mock_sense_hat

        pixels = [[255, 0, 0]] * 64
        result = await service.set_pixels(pixels, mode="test")

        assert result is True
        assert service._current_mode == "test"
        mock_sense_hat.set_pixels.assert_called_once_with(pixels)

    @pytest.mark.asyncio
    async def test_clear_display_with_hardware(self):
        """Test clear_display calls hardware when available."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        service._sense_hat = mock_sense_hat

        result = await service.clear_display()

        assert result is True
        assert service._current_mode == "cleared"
        mock_sense_hat.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_sensor_readings_with_hardware(self):
        """Test sensor readings with mocked hardware."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        mock_sense_hat.get_temperature.return_value = 25.5
        mock_sense_hat.get_humidity.return_value = 45.2
        mock_sense_hat.get_pressure.return_value = 1013.25
        service._sense_hat = mock_sense_hat

        readings = await service.get_sensor_readings()

        assert readings.available is True
        assert readings.temperature == 25.5
        assert readings.humidity == 45.2
        assert readings.pressure == 1013.2  # Rounded to 1 decimal
        assert readings.error is None

    @pytest.mark.asyncio
    async def test_get_sensor_readings_with_error(self):
        """Test sensor readings when hardware raises exception."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        mock_sense_hat.get_temperature.side_effect = RuntimeError("Sensor error")
        service._sense_hat = mock_sense_hat

        readings = await service.get_sensor_readings()

        assert readings.available is False
        assert readings.temperature is None
        assert readings.error is not None
        assert "Sensor error" in readings.error

    @pytest.mark.asyncio
    async def test_get_matrix_state_with_hardware(self):
        """Test matrix state with mocked hardware."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        expected_pixels = [[255, 0, 0]] * 64
        mock_sense_hat.get_pixels.return_value = expected_pixels
        service._sense_hat = mock_sense_hat
        service._current_mode = "test_mode"
        service._current_rotation = 90
        service._web_rotation_offset = 180

        state = await service.get_matrix_state()

        assert state.available is True
        assert state.pixels == expected_pixels
        assert state.mode == "test_mode"
        assert state.rotation == 90
        assert state.web_offset == 180

    @pytest.mark.asyncio
    async def test_show_message_with_hardware(self):
        """Test show_message calls hardware when available."""
        service = HardwareService()
        service._initialized = True
        service._available = True
        mock_sense_hat = MagicMock()
        service._sense_hat = mock_sense_hat

        result = await service.show_message("Test", scroll_speed=0.05, text_colour=(0, 255, 0))

        assert result is True
        assert service._current_mode == "scrolling"
        mock_sense_hat.show_message.assert_called_once_with(
            "Test",
            scroll_speed=0.05,
            text_colour=(0, 255, 0),
        )


class TestDataClasses:
    """Test dataclass structures."""

    def test_matrix_state_creation(self):
        """Test MatrixState dataclass."""
        state = MatrixState(
            pixels=[[0, 0, 0]] * 64,
            mode="test",
            rotation=90,
            web_offset=180,
            available=True,
        )

        assert state.mode == "test"
        assert state.rotation == 90
        assert state.web_offset == 180
        assert state.available is True
        assert len(state.pixels) == 64

    def test_sensor_readings_creation(self):
        """Test SensorReadings dataclass."""
        readings = SensorReadings(
            temperature=25.0,
            humidity=50.0,
            pressure=1013.0,
            available=True,
            error=None,
        )

        assert readings.temperature == 25.0
        assert readings.humidity == 50.0
        assert readings.pressure == 1013.0
        assert readings.available is True
        assert readings.error is None

    def test_sensor_readings_with_error(self):
        """Test SensorReadings dataclass with error."""
        readings = SensorReadings(
            temperature=None,
            humidity=None,
            pressure=None,
            available=False,
            error="Test error",
        )

        assert readings.temperature is None
        assert readings.available is False
        assert readings.error == "Test error"
