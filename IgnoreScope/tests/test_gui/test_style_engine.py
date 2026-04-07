"""Tests for the unified style engine.

Verifies GradientClass, FontStyleClass, StateStyleClass dataclasses
and StyleGui singleton API (build_gradient, palette_color, etc.).
"""

import pytest
from PyQt6.QtGui import QColor

from IgnoreScope.gui.style_engine import (
    StyleGui,
    GradientClass,
    GradientStop,
    WidgetGradientDef,
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

    @pytest.mark.skip(reason="GradientClass.with_selected not yet implemented")
    def test_with_selected_default(self):
        """with_selected replaces pos2/pos3, preserves pos1/pos4."""
        base = GradientClass("masked", "masked", "hidden", "revealed")
        sel = base.with_selected()
        assert sel.pos1 == "masked"
        assert sel.pos2 == "selected"
        assert sel.pos3 == "selected"
        assert sel.pos4 == "revealed"

    @pytest.mark.skip(reason="GradientClass.with_selected not yet implemented")
    def test_with_selected_custom_var(self):
        """with_selected accepts a custom variable name."""
        base = GradientClass("a", "b", "c", "d")
        sel = base.with_selected("highlight")
        assert sel.pos2 == "highlight"
        assert sel.pos3 == "highlight"
        assert sel.pos1 == "a"
        assert sel.pos4 == "d"

    @pytest.mark.skip(reason="GradientClass.with_selected not yet implemented")
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
        assert sg.palette_color("accent_blue") == "#9BA5FF"
        assert sg.palette_color("base_0") == "#383144"

    def test_ui_color(self, sg):
        assert sg.ui_color("window_bg") == "#3F3A57"
        assert sg.ui_color("accent_primary") == "#9BA5FF"

    def test_selection_color(self, sg):
        c = sg.selection_color()
        assert hex_of(c) == "#9ba5ff"
        assert c.alpha() == 100

    def test_hover_color(self, sg):
        c = sg.hover_color()
        assert hex_of(c) == "#50476f"
        assert c.alpha() == 60

    def test_build_stylesheet(self, sg):
        """build_stylesheet returns a non-empty string with theme values."""
        css = sg.build_stylesheet()
        assert len(css) > 100
        assert "#3F3A57" in css  # window_bg
        assert "#9BA5FF" in css  # accent_primary


class TestBuildGradient:
    """Test the universal 4-stop build_gradient method."""

    def test_build_gradient_universal(self, sg):
        """4 stops at 0.0, 0.4, 0.6, 0.85 — 3-zone layout (self/parent/child)."""
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
        assert positions == [0.0, 0.4, 0.6, 0.85]

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


# ===========================================================================
# Widget Gradient Dataclass tests
# ===========================================================================

class TestGradientStop:
    """Verify GradientStop frozen dataclass behavior."""

    def test_fields(self):
        s = GradientStop(position=0.5, color="frost_0", offset_px=10)
        assert s.position == 0.5
        assert s.color == "frost_0"
        assert s.offset_px == 10

    def test_defaults(self):
        s = GradientStop(position=0.0, color="#FF0000")
        assert s.offset_px == 0

    def test_frozen(self):
        s = GradientStop(position=0.0, color="a")
        with pytest.raises(AttributeError):
            s.position = 0.5


class TestWidgetGradientDef:
    """Verify WidgetGradientDef frozen dataclass behavior."""

    def test_linear_defaults(self):
        stops = (GradientStop(0.0, "a"), GradientStop(1.0, "b"))
        g = WidgetGradientDef(type="linear", stops=stops)
        assert g.anchor == "vertical"
        assert g.angle == 0.0
        assert g.child_opacity == 0

    def test_radial_fields(self):
        stops = (GradientStop(0.0, "a"), GradientStop(1.0, "b"))
        g = WidgetGradientDef(
            type="radial", stops=stops,
            center_x=0.3, center_y=0.7, radius=0.4,
        )
        assert g.center_x == 0.3
        assert g.center_y == 0.7
        assert g.radius == 0.4

    def test_frozen(self):
        stops = (GradientStop(0.0, "a"),)
        g = WidgetGradientDef(type="linear", stops=stops)
        with pytest.raises(AttributeError):
            g.type = "radial"


# ===========================================================================
# Widget Gradient StyleGui API tests
# ===========================================================================

class TestWidgetGradientLoading:
    """Test theme.json gradient loading and resolution."""

    def test_gradients_loaded(self, sg):
        """theme.json 'gradients' section parsed into WidgetGradientDef."""
        names = sg.widget_gradient_names()
        assert "main_window" in names
        assert "dock_panel" in names
        assert "config_panel" in names
        assert "status_bar" in names

    def test_gradient_stop_count(self, sg):
        """Each gradient has the expected number of stops."""
        g = sg._widget_gradients["main_window"]
        assert len(g.stops) == 2
        g = sg._widget_gradients["dock_panel"]
        assert len(g.stops) == 3
        g = sg._widget_gradients["status_bar"]
        assert len(g.stops) == 3

    def test_gradient_types(self, sg):
        """All current gradients are linear."""
        for name in sg.widget_gradient_names():
            assert sg._widget_gradients[name].type == "linear"


class TestResolveGradientColor:
    """Test color reference resolution."""

    def test_hex_passthrough(self, sg):
        assert sg._resolve_gradient_color("#BDA4FF") == "#BDA4FF"

    def test_palette_lookup(self, sg):
        assert sg._resolve_gradient_color("base_0") == "#383144"

    def test_ui_lookup(self, sg):
        assert sg._resolve_gradient_color("surface_bg") == "#50476F"

    def test_unknown_fallback(self, sg):
        result = sg._resolve_gradient_color("nonexistent_var")
        assert result == "#383144"  # falls back to base_0


class TestBuildWidgetGradient:
    """Test widget gradient construction."""

    def test_returns_none_for_unknown(self, sg):
        assert sg.build_widget_gradient("no_such_gradient", 800, 600) is None

    def test_linear_vertical(self, sg):
        """main_window is a vertical linear gradient."""
        from PyQt6.QtGui import QLinearGradient
        grad = sg.build_widget_gradient("main_window", 800, 600)
        assert isinstance(grad, QLinearGradient)
        stops = grad.stops()
        assert len(stops) == 2
        # Vertical: start at top center, end at bottom center
        assert grad.start().x() == 400  # width / 2
        assert grad.start().y() == 0
        assert grad.finalStop().x() == 400
        assert grad.finalStop().y() == 600

    def test_linear_horizontal(self, sg):
        """status_bar is a horizontal linear gradient."""
        grad = sg.build_widget_gradient("status_bar", 1000, 30)
        stops = grad.stops()
        assert len(stops) == 3
        # Horizontal: start at left center, end at right center
        assert grad.start().x() == 0
        assert grad.start().y() == 15  # height / 2
        assert grad.finalStop().x() == 1000
        assert grad.finalStop().y() == 15

    def test_stop_colors_resolved(self, sg):
        """Gradient stop colors resolve from theme variables."""
        grad = sg.build_widget_gradient("main_window", 800, 600)
        stops = grad.stops()
        # base_1 = #3F3A57, base_0 = #383144
        assert_color(stops[0][1], "#3F3A57", "stop 0 = base_1")
        assert_color(stops[1][1], "#383144", "stop 1 = base_0")


class TestRowGradientOpacity:
    """Test row_gradient_opacity property."""

    def test_reads_from_theme(self, sg):
        assert sg.row_gradient_opacity == 242

    def test_default_when_missing(self):
        """Default is 255 if key absent."""
        sg = StyleGui.instance()
        # Remove the key temporarily
        original = sg._theme["delegate"].pop("row_gradient_opacity", None)
        try:
            assert sg.row_gradient_opacity == 255
        finally:
            if original is not None:
                sg._theme["delegate"]["row_gradient_opacity"] = original


class TestChildBg:
    """Test _child_bg opacity computation."""

    def test_transparent_when_opacity_zero(self, sg):
        """child_opacity=0 → 'transparent'."""
        result = sg._child_bg("main_window", "#3B4252")
        assert result == "transparent"

    def test_opaque_when_opacity_255(self, sg):
        """child_opacity=255 → passthrough color."""
        # Temporarily set child_opacity to 255
        gdef = sg._widget_gradients["main_window"]
        original = gdef
        sg._widget_gradients["main_window"] = WidgetGradientDef(
            type=gdef.type, stops=gdef.stops,
            anchor=gdef.anchor, angle=gdef.angle,
            child_opacity=255,
        )
        try:
            assert sg._child_bg("main_window", "#3B4252") == "#3B4252"
        finally:
            sg._widget_gradients["main_window"] = original

    def test_partial_opacity(self, sg):
        """child_opacity between 0 and 255 → rgba string."""
        gdef = sg._widget_gradients["main_window"]
        original = gdef
        sg._widget_gradients["main_window"] = WidgetGradientDef(
            type=gdef.type, stops=gdef.stops,
            anchor=gdef.anchor, angle=gdef.angle,
            child_opacity=128,
        )
        try:
            result = sg._child_bg("main_window", "#3B4252")
            assert result == "rgba(59, 66, 82, 128)"
        finally:
            sg._widget_gradients["main_window"] = original

    def test_unknown_gradient(self, sg):
        """Unknown gradient name → 'transparent'."""
        assert sg._child_bg("nonexistent", "#FF0000") == "transparent"
