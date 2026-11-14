"""FRIDAY 2.0 - Main entry point."""

import sys
import traceback

from friday.config import load_settings
from friday.core import CoreService, get_logger, setup_logging
from friday.ui import MainWindow, create_application

logger = get_logger(__name__)


def main() -> int:
    """Main entry point."""
    # Load settings
    try:
        settings = load_settings()
    except Exception as e:
        print(f"Failed to load settings: {e}", file=sys.stderr)
        return 1

    # Setup logging
    setup_logging(settings.app.log_level)
    logger.info("Starting FRIDAY 2.0 v%s", settings.app.version)

    # Create Qt application
    app = create_application()

    # Create core service
    core = CoreService()

    # Create main window
    window = MainWindow(core)
    window.show()

    # Start core service
    try:
        core.start()
    except Exception as e:
        logger.exception("Failed to start core service: %s", e)
        window._status_label.setText(f"Core: failed - {e}")
        window._ping_button.setEnabled(False)

    # Run Qt event loop
    exit_code = app.exec()

    # Clean shutdown
    logger.info("Shutting down...")
    core.stop()

    return exit_code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
