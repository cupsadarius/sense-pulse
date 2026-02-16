"""Tests for sleep schedule logic."""

from __future__ import annotations

from unittest.mock import patch

from sensehat.schedule import is_sleep_time


class TestIsSleepTime:
    def test_sleep_time_during_sleep_window(self) -> None:
        """Should return True when current hour is within sleep window."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 23
            assert is_sleep_time(23, 7) is True

    def test_sleep_time_before_midnight(self) -> None:
        """Should return True at midnight during 23-7 window."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 0
            assert is_sleep_time(23, 7) is True

    def test_sleep_time_early_morning(self) -> None:
        """Should return True at 3am during 23-7 window."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 3
            assert is_sleep_time(23, 7) is True

    def test_awake_time_after_end(self) -> None:
        """Should return False when past the sleep end hour."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 7
            assert is_sleep_time(23, 7) is False

    def test_awake_time_afternoon(self) -> None:
        """Should return False during normal waking hours."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            assert is_sleep_time(23, 7) is False

    def test_awake_time_evening(self) -> None:
        """Should return False before sleep starts."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 22
            assert is_sleep_time(23, 7) is False

    def test_same_hour_means_no_sleep(self) -> None:
        """When start == end, no sleep window (always awake)."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            assert is_sleep_time(12, 12) is False

    def test_non_wrapping_window_inside(self) -> None:
        """Non-wrapping window (e.g., 13-15): inside should return True."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 14
            assert is_sleep_time(13, 15) is True

    def test_non_wrapping_window_outside_before(self) -> None:
        """Non-wrapping window (e.g., 13-15): before should return False."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            assert is_sleep_time(13, 15) is False

    def test_non_wrapping_window_outside_after(self) -> None:
        """Non-wrapping window (e.g., 13-15): after should return False."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 15
            assert is_sleep_time(13, 15) is False

    def test_wrapping_window_at_start_boundary(self) -> None:
        """Wrapping window should include the start hour exactly."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 22
            assert is_sleep_time(22, 6) is True

    def test_wrapping_window_just_before_end(self) -> None:
        """Wrapping window should include hour just before end."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 5
            assert is_sleep_time(22, 6) is True

    def test_wrapping_window_at_end_boundary(self) -> None:
        """End hour should NOT be included (exclusive)."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 6
            assert is_sleep_time(22, 6) is False

    def test_non_wrapping_at_start_boundary(self) -> None:
        """Non-wrapping: start hour should be included (inclusive)."""
        with patch("sensehat.schedule.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 13
            assert is_sleep_time(13, 15) is True
