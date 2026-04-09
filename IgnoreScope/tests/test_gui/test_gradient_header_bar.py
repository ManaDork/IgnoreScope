"""Tests for GradientHeaderBar widget.

Verifies instantiation, DPI-scaled height, label text, action button API,
and signal emission (clicked, contextMenuRequested).
"""

import pytest
from unittest.mock import MagicMock

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.style_engine import StyleGui
from IgnoreScope.gui.gradient_header_bar import (
    GradientHeaderBar,
    BASE_HEADER_HEIGHT,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _qapp():
    """Ensure QApplication exists for widget tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset StyleGui singleton between tests."""
    StyleGui._reset()
    yield
    StyleGui._reset()


@pytest.fixture
def header() -> GradientHeaderBar:
    """Create a GradientHeaderBar with title_bar gradient."""
    w = GradientHeaderBar("title_bar", "Test Header")
    return w


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestInstantiation:

    def test_creates_with_gradient_name(self, header):
        assert header._gradient_name == "title_bar"

    def test_creates_with_label_text(self, header):
        assert header.label_text() == "Test Header"

    def test_creates_with_empty_label(self):
        w = GradientHeaderBar("title_bar")
        assert w.label_text() == ""

    def test_gradient_name_accessible(self, header):
        """Gradient name set by constructor is used by the mixin."""
        assert header._gradient_name == "title_bar"


# ---------------------------------------------------------------------------
# Height
# ---------------------------------------------------------------------------

class TestHeight:

    def test_base_constant(self):
        assert BASE_HEADER_HEIGHT == 36

    def test_header_height_returns_int(self, header):
        assert isinstance(header.header_height, int)

    def test_header_height_positive(self, header):
        assert header.header_height > 0

    def test_header_height_scales_with_dpi(self, header):
        """At 96 DPI the height equals the base constant."""
        dpi = header.logicalDpiX()
        expected = round(BASE_HEADER_HEIGHT * (dpi / 96.0))
        assert header.header_height == expected

    def test_minimum_size_hint_height(self, header):
        assert header.minimumSizeHint().height() == header.header_height

    def test_size_hint_height(self, header):
        assert header.sizeHint().height() == header.header_height


# ---------------------------------------------------------------------------
# Label
# ---------------------------------------------------------------------------

class TestLabel:

    def test_set_label_text(self, header):
        header.set_label_text("New Title")
        assert header.label_text() == "New Title"

    def test_label_initially_set(self, header):
        assert header.label_text() == "Test Header"


# ---------------------------------------------------------------------------
# Action Buttons
# ---------------------------------------------------------------------------

class TestActionButtons:

    def test_add_action_button_returns_button(self, header):
        callback = MagicMock()
        btn = header.add_action_button(QIcon(), "Test", callback)
        assert btn is not None

    def test_add_action_button_tooltip(self, header):
        callback = MagicMock()
        btn = header.add_action_button(QIcon(), "My Tooltip", callback)
        assert btn.toolTip() == "My Tooltip"

    def test_add_action_button_callback_connected(self, header):
        callback = MagicMock()
        btn = header.add_action_button(QIcon(), "Test", callback)
        btn.click()
        callback.assert_called_once()

    def test_add_multiple_buttons(self, header):
        cb1 = MagicMock()
        cb2 = MagicMock()
        btn1 = header.add_action_button(QIcon(), "A", cb1)
        btn2 = header.add_action_button(QIcon(), "B", cb2)
        assert btn1 is not btn2
        assert header._actions_layout.count() == 2

    def test_button_is_flat(self, header):
        btn = header.add_action_button(QIcon(), "T", MagicMock())
        assert btn.isFlat()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

class TestSignals:

    def test_clicked_emits_on_left_click(self, header):
        spy = MagicMock()
        header.clicked.connect(spy)

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QPointF
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        header.mousePressEvent(event)
        spy.assert_called_once()

    def test_clicked_does_not_emit_on_right_click(self, header):
        spy = MagicMock()
        header.clicked.connect(spy)

        from PyQt6.QtGui import QMouseEvent
        from PyQt6.QtCore import QPointF
        event = QMouseEvent(
            QMouseEvent.Type.MouseButtonPress,
            QPointF(5, 5),
            Qt.MouseButton.RightButton,
            Qt.MouseButton.RightButton,
            Qt.KeyboardModifier.NoModifier,
        )
        header.mousePressEvent(event)
        spy.assert_not_called()

    def test_context_menu_requested_emits(self, header):
        spy = MagicMock()
        header.contextMenuRequested.connect(spy)

        from PyQt6.QtGui import QContextMenuEvent
        event = QContextMenuEvent(
            QContextMenuEvent.Reason.Mouse,
            QPoint(10, 10),
            QPoint(100, 100),
        )
        header.contextMenuEvent(event)
        spy.assert_called_once()
        assert isinstance(spy.call_args[0][0], QPoint)


# ---------------------------------------------------------------------------
# Theme integration
# ---------------------------------------------------------------------------

class TestThemeIntegration:

    def test_title_bar_gradient_exists(self):
        sg = StyleGui.instance()
        assert "title_bar" in sg.widget_gradient_names()

    def test_title_bar_gradient_builds(self):
        sg = StyleGui.instance()
        grad = sg.build_widget_gradient("title_bar", 400, 36)
        assert grad is not None
