"""Tests for the unified style engine.

Verifies GradientClass, FontStyleClass, StateStyleClass dataclasses
and StyleGui singleton API (build_gradient, palette_color, etc.).
"""

import pytest
from PyQt6.QtGui import QColor

from IgnoreScope.gui.style_engine import (
    StyleGui,
    GradientClass,
    FontStyleClass,
    StateStyleClass,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def hex_of(color: QColor) -> str:
    """Lowercase hex string from QColor (e.g. '#2e3440')."""
    return color.name().lower()


def assert_color(actual: QColor, expected_hex: str, label: str = ""):
    """Assert QColor matches expected hex (case-insensitive)."""
    actual_hex = hex_of(actual)
    expected_lower = expected_hex.lower()
    assert actual_hex == expected_lower, (
        f"{label}: expected {expected_lower}, got {actual_hex}"
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset StyleGui singleton between tests."""
    StyleGui._reset()
    yield
    StyleGui._reset()


@pytest.fixture
def sg() -> StyleGui:
    """Get a fresh StyleGui instance."""
    return StyleGui.instance()


# ===========================================================================
# Dataclass tests
# ===========================================================================

class TestGradientClass:
    """Verify GradientClass frozen dataclass behavior."""

    def test_fields(self):
        g = GradientClass("a", "b", "c", "d")
        assert g.pos1 == "a"
        assert g.pos2 == "b"
        assert g.pos3 == "c"
        assert g.pos4 == "d"

    def test_frozen(self):
        g = GradientClass("a", "b", "c", "d")
        with pytest.raises(AttributeError):
            g.pos1 = "x"

    def test_with_selected_default(self):
        """with_selected replaces pos2/pos3, preserves pos1/pos4."""
        base = GradientClass("masked", "masked", "hidden", "revealed")
        sel = base.with_selected()
        assert sel.pos1 == "masked"
        assert sel.pos2 == "selected"
        assert sel.pos3 == "selected"
        assert sel.pos4 == "revealed"

    def test_with_selected_custom_var(self):
        """with_selected accepts a custom variable name."""
        base = GradientClass("a", "b", "c", "d")
        sel = base.with_selected("highlight")
        assert sel.pos2 == "highlight"
        assert sel.pos3 == "highlight"
        assert sel.pos1 == "a"
        assert sel.pos4 == "d"

    def test_with_selected_returns_new_instance(self):
        base = GradientClass("a", "b", "c", "d")
        sel = base.with_selected()
        assert base is not sel
        assert base.pos2 == "b"  # original unchanged


class TestFontStyleClass:
    """Verify FontStyleClass defaults and frozen behavior."""

    def test_defaults(self):
        f = FontStyleClass()
        assert f.weight == "normal"
        assert f.italic is False
        assert f.text_color_var == "text_primary"

    def test_custom(self):
        f = FontStyleClass(weight="bold", italic=True, text_color_var="text_dim")
        assert f.weight == "bold"
        assert f.italic is True
        assert f.text_color_var == "text_dim"


class TestStateStyleClass:
    """Verify StateStyleClass composition."""

    def test_with_gradient_and_font(self):
        g = GradientClass("a", "b", "c", "d")
        f = FontStyleClass(italic=True)
        s = StateStyleClass(gradient=g, font=f)
        assert s.gradient is g
        assert s.font is f

    def test_deferred_state(self):
        """Gradient can be None for DEFERRED states."""
        s = StateStyleClass(gradient=None, font=FontStyleClass())
        assert s.gradient is None

    def test_default_font(self):
        s = StateStyleClass()
        assert s.font.weight == "normal"


# ===========================================================================
# StyleGui API tests
# ===========================================================================

class TestStyleGuiAPI:
    """Test singleton and utility methods."""

    def test_singleton(self):
        a = StyleGui.instance()
        b = StyleGui.instance()
        assert a is b

    def test_palette_color(self, sg):
        assert sg.palette_color("frost_1") == "#88C0D0"
        assert sg.palette_color("polar_night_0") == "#2E3440"

    def test_ui_color(self, sg):
        assert sg.ui_color("window_bg") == "#2E3440"
        assert sg.ui_color("accent_primary") == "#88C0D0"

    def test_selection_color(self, sg):
        c = sg.selection_color()
        assert hex_of(c) == "#5e81ac"
        assert c.alpha() == 100

    def test_hover_color(self, sg):
        c = sg.hover_color()
        assert hex_of(c) == "#4c566a"
        assert c.alpha() == 60

    def test_build_stylesheet(self, sg):
        """build_stylesheet returns a non-empty string with theme values."""
        css = sg.build_stylesheet()
        assert len(css) > 100
        assert "#2E3440" in css  # window_bg
        assert "#88C0D0" in css  # accent_primary


class TestBuildGradient:
    """Test the universal 4-stop build_gradient method."""

    def test_build_gradient_universal(self, sg):
        """4 stops at 0.0, 0.25, 0.50, 0.75 with correct colors."""
        gradient_class = GradientClass("mounted", "masked", "hidden", "revealed")
        color_vars = {
            "mounted":  "#3D4A3E",
            "masked":   "#4A3B42",
            "hidden":   "#2E3440",
            "revealed": "#4A4838",
        }
        gradient = sg.build_gradient(gradient_class, color_vars, 800)
        stops = gradient.stops()
        assert len(stops) == 4

        # Verify positions
        positions = [s[0] for s in stops]
        assert positions == [0.0, 0.25, 0.50, 0.75]

        # Verify colors
        assert_color(stops[0][1], "#3D4A3E", "pos1=mounted")
        assert_color(stops[1][1], "#4A3B42", "pos2=masked")
        assert_color(stops[2][1], "#2E3440", "pos3=hidden")
        assert_color(stops[3][1], "#4A4838", "pos4=revealed")

    def test_build_gradient_uniform(self, sg):
        """All-same variable produces 4 identical color stops."""
        gradient_class = GradientClass("bg", "bg", "bg", "bg")
        color_vars = {"bg": "#3B4252"}
        gradient = sg.build_gradient(gradient_class, color_vars, 400)
        stops = gradient.stops()
        for _, color in stops:
            assert_color(color, "#3B4252", "uniform")

    def test_build_gradient_width_affects_endpoint(self, sg):
        """Width parameter is reflected in the gradient's finalStop."""
        gradient_class = GradientClass("a", "a", "a", "a")
        color_vars = {"a": "#FFFFFF"}
        g = sg.build_gradient(gradient_class, color_vars, 1200)
        assert g.finalStop().x() == 1200
