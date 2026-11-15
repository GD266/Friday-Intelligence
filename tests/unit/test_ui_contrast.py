"""Offscreen palette tests for the main window transcript."""

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from friday.core.service import CoreService
from friday.ui.main_window import MainWindow


def _channel_luminance(value: int) -> float:
    srgb = value / 255.0
    if srgb <= 0.04045:
        return srgb / 12.92
    return ((srgb + 0.055) / 1.055) ** 2.4


def _relative_luminance(color: QColor) -> float:
    return (
        0.2126 * _channel_luminance(color.red())
        + 0.7152 * _channel_luminance(color.green())
        + 0.0722 * _channel_luminance(color.blue())
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    first_luminance = _relative_luminance(first)
    second_luminance = _relative_luminance(second)
    lighter = max(first_luminance, second_luminance)
    darker = min(first_luminance, second_luminance)
    return (lighter + 0.05) / (darker + 0.05)


def _light_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3f3f3"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#1a1a1a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f7f7"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#1a1a1a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#f3f3f3"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#1a1a1a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0078d7"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#0066cc"))
    return palette


def _dark_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#1e1e1e"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#252526"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#2d2d30"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#2d2d30"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0078d7"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Link, QColor("#4da6ff"))
    return palette


@pytest.mark.parametrize(
    "palette_factory",
    [_light_palette, _dark_palette],
    ids=["light", "dark"],
)
def test_transcript_contrast_in_both_themes(
    qt_app: QApplication, palette_factory
) -> None:
    """Render offscreen and check transcript text against its background."""
    original_palette = qt_app.palette()
    window = None
    try:
        qt_app.setPalette(palette_factory())
        window = MainWindow(CoreService())
        window.show()
        qt_app.processEvents()
        window.grab()

        palette = window._transcript.palette()
        text = palette.color(QPalette.ColorRole.Text)

        # Sample the transcript's rendered viewport instead of the palette so
        # a hardcoded background would be caught here.
        viewport = window._transcript.viewport()
        image = viewport.grab().toImage()
        background = image.pixelColor(
            image.width() // 2, image.height() // 2
        )

        assert _contrast_ratio(text, background) >= 4.5

        error = window._error_color()
        assert _contrast_ratio(error, background) >= 4.5
        assert error.red() > error.green()
        assert error.red() > error.blue()
    finally:
        if window is not None:
            window.close()
            window.deleteLater()
        qt_app.setPalette(original_palette)
        qt_app.processEvents()
