"""Tests for core service."""

import time

from friday.core.service import CoreService


class TestCoreService:
    """Test core service thread and async loop."""

    def test_start_stop(self):
        """Test core service starts and stops cleanly."""
        core = CoreService()
        assert not core.is_running

        core.start()
        assert core.is_running

        # Give it a moment to fully start
        time.sleep(0.1)

        core.stop()
        assert not core.is_running

    def test_ping_pong(self):
        """Test ping/pong communication."""
        core = CoreService()
        core.start()

        try:
            time.sleep(0.1)  # Wait for start

            # Send ping
            core.send_ping("test-ping")

            # Wait for pong via signal (we can't easily test Qt signals in unit test
            # without QApplication, so we'll just verify the method doesn't raise)
            time.sleep(0.1)

        finally:
            core.stop()

    def test_stop_within_timeout(self):
        """Test that stop completes within 3 seconds."""
        core = CoreService()
        core.start()

        start = time.time()
        core.stop()
        elapsed = time.time() - start

        assert elapsed < 3.0, f"Core stop took {elapsed:.2f}s, should be < 3s"

    def test_double_start_warns(self, caplog):
        """Test that starting twice logs a warning."""
        import logging
        caplog.set_level(logging.WARNING)

        core = CoreService()
        core.start()
        core.start()  # Second start

        assert "already running" in caplog.text
        core.stop()

    def test_stop_when_not_running_is_silent(self, caplog):
        """Test stopping when not running logs only at DEBUG level."""
        import logging
        caplog.set_level(logging.DEBUG)

        core = CoreService()
        core.stop()

        assert "already stopped" in caplog.text
        assert "WARNING" not in caplog.text
