"""FRIDAY 2.0 - Main entry point."""

import sys
import traceback

from PySide6.QtWidgets import QMessageBox

from friday.config import load_settings
from friday.core.logging import get_logger, setup_logging
from friday.core.service import CoreService
from friday.ui import MainWindow, create_application

logger = get_logger(__name__)


def _show_config_error(message: str) -> None:
    """Show a startup error dialog, if a GUI can be created."""
    try:
        create_application()
        QMessageBox.critical(None, "FRIDAY 2.0 - Configuration Error", message)
    except Exception:
        # The stderr output remains the fallback if no GUI is available.
        pass


def main() -> int:
    """Main entry point."""
    # Load settings
    try:
        settings = load_settings()
    except Exception as e:
        message = f"Failed to load settings: {e}"
        print(message, file=sys.stderr)
        _show_config_error(message)
        return 1

    # Setup logging
    setup_logging(settings.app.log_level)
    logger.info("Starting FRIDAY 2.0 v%s", settings.app.version)

    # Create Qt application
    app = create_application()

    # Create core service
    core = CoreService(settings=settings)

    # Create main window
    window = MainWindow(core)
    window.show()

    # Start core service
    try:
        core.start()
    except Exception as e:
        logger.exception("Failed to start core service: %s", e)
        window.set_core_failed(str(e))

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
