"""Tests for Sense HAT command handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from sense_common.models import Command, CommandResponse
from sensehat.commands import CommandHandler
from sensehat.display import SenseHatDisplay


@pytest.fixture
def mock_display() -> SenseHatDisplay:
    """Create a display with mocked methods."""
    display = SenseHatDisplay(sense_hat_instance=None)
    display.clear = AsyncMock()
    display.set_rotation = MagicMock()
    display.get_pixels = MagicMock(return_value=[[0, 0, 0]] * 64)
    display._current_mode = "idle"
    display.rotation = 0
    return display


@pytest.fixture
def handler(mock_display: SenseHatDisplay) -> CommandHandler:
    return CommandHandler(display=mock_display)


class TestClearCommand:
    async def test_clear_calls_display_clear(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        cmd = Command(action="clear", request_id="test-1", params={})
        response = await handler.handle(cmd)

        mock_display.clear.assert_awaited_once()
        assert response.status == "ok"
        assert response.request_id == "test-1"

    async def test_clear_response_has_message(self, handler: CommandHandler) -> None:
        cmd = Command(action="clear", request_id="test-2", params={})
        response = await handler.handle(cmd)

        assert response.data is not None
        assert "message" in response.data


class TestSetRotationCommand:
    async def test_set_rotation_valid(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        cmd = Command(action="set_rotation", request_id="test-3", params={"rotation": 180})
        response = await handler.handle(cmd)

        mock_display.set_rotation.assert_called_once_with(180)
        assert response.status == "ok"
        assert response.data["rotation"] == 180

    async def test_set_rotation_all_valid_values(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        for rotation in (0, 90, 180, 270):
            mock_display.set_rotation.reset_mock()
            cmd = Command(
                action="set_rotation",
                request_id=f"test-rot-{rotation}",
                params={"rotation": rotation},
            )
            response = await handler.handle(cmd)
            assert response.status == "ok"
            mock_display.set_rotation.assert_called_once_with(rotation)

    async def test_set_rotation_invalid(self, handler: CommandHandler) -> None:
        cmd = Command(action="set_rotation", request_id="test-4", params={"rotation": 45})
        response = await handler.handle(cmd)

        assert response.status == "error"
        assert "Invalid rotation" in response.error

    async def test_set_rotation_default_zero(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        """Default rotation should be 0 when not specified in params."""
        cmd = Command(action="set_rotation", request_id="test-5", params={})
        response = await handler.handle(cmd)

        mock_display.set_rotation.assert_called_once_with(0)
        assert response.status == "ok"


class TestGetMatrixCommand:
    async def test_get_matrix_returns_pixels(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        pixels = [[255, 0, 0]] * 64
        mock_display.get_pixels.return_value = pixels
        mock_display._current_mode = "scrolling"
        mock_display.rotation = 90

        cmd = Command(action="get_matrix", request_id="test-6", params={})
        response = await handler.handle(cmd)

        assert response.status == "ok"
        assert response.data["pixels"] == pixels
        assert response.data["mode"] == "scrolling"
        assert response.data["rotation"] == 90

    async def test_get_matrix_empty_display(
        self, handler: CommandHandler, mock_display: SenseHatDisplay
    ) -> None:
        """Should return blank pixels when display is cleared."""
        cmd = Command(action="get_matrix", request_id="test-7", params={})
        response = await handler.handle(cmd)

        assert response.status == "ok"
        assert len(response.data["pixels"]) == 64


class TestUnknownCommand:
    async def test_unknown_action(self, handler: CommandHandler) -> None:
        cmd = Command(action="unknown_action", request_id="test-8", params={})
        response = await handler.handle(cmd)

        assert response.status == "error"
        assert "Unknown action" in response.error
        assert response.request_id == "test-8"


class TestCommandResponse:
    async def test_response_model_fields(self, handler: CommandHandler) -> None:
        """All responses should have request_id and status."""
        cmd = Command(action="clear", request_id="test-9", params={})
        response = await handler.handle(cmd)

        assert isinstance(response, CommandResponse)
        assert response.request_id == "test-9"
        assert response.status in ("ok", "error")
