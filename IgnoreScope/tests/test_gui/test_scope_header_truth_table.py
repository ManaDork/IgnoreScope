"""Tests for Phase 3 Task 3.9: full 6-row truth-table render assertions.

Exercises every valid ``ScopeHeaderSignals`` state end-to-end through
``ScopeView.refresh()`` and asserts the column-0 header text and
``QHeaderView::section`` stylesheet match the visual encoding locked in
``THEME_WORKFLOW.md § Scope Header Signal Mapping``.

Pairs with:
  - test_scope_header_signals.py — resolver truth table (pure)
  - test_scope_header_signals_wiring.py — _compute_header_signals wiring
  - test_scope_header_render.py — unit-level stylesheet routing

This file is the integration layer between the three.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.local_mount_config import ExtensionConfig
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import ScopeView
from IgnoreScope.gui.style_engine import StyleGui


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


@dataclass(frozen=True)
class _Case:
    name: str
    running: bool
    add_bind: bool
    add_extension: bool
    expect_dot: str       # "●" / "○" / ""
    expect_bg: bool       # background-color rule present
    expect_border: bool   # border-bottom rule present


# The 6 valid truth-table rows mapped to input gestures + expected render.
# Mutually exclusive by invariant: we never construct a (bind + ext-only)
# row that maps to fully_virtual — extension-only = fully_virtual, bind
# present = has_mounts.
_CASES = [
    _Case("empty_stopped",           False, False, False, "○", False, False),
    _Case("empty_running",           True,  False, False, "●", False, False),
    _Case("has_bind_stopped",        False, True,  False, "○", False, True),
    _Case("has_bind_running",        True,  True,  False, "●", False, True),
    _Case("fully_virtual_stopped",   False, False, True,  "○", True,  False),
    _Case("fully_virtual_running",   True,  False, True,  "●", True,  False),
]


@pytest.mark.parametrize("case", _CASES, ids=lambda c: c.name)
def test_truth_table_end_to_end(case: _Case, tmp_path: Path):
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    tree.current_scope = "test_scope"

    if case.add_bind:
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)

    if case.add_extension:
        tree._extensions.append(
            ExtensionConfig(name="claude", isolation_paths=["/root/.claude"]),
        )

    view = ScopeView(tree)
    with patch(
        "IgnoreScope.gui.scope_view._query_is_container_running",
        return_value=case.running,
    ):
        view.refresh()

    header_text = view._config.columns[0].header
    css = view._tree_view.header().styleSheet()

    # Dot prefix
    assert header_text.startswith(f"{case.expect_dot} "), (
        f"{case.name}: expected dot {case.expect_dot!r} prefix, got {header_text!r}"
    )

    # Background-color rule
    if case.expect_bg:
        assert "background-color:" in css, (
            f"{case.name}: expected background-color rule in {css!r}"
        )
    else:
        assert "background-color" not in css, (
            f"{case.name}: expected no background-color rule in {css!r}"
        )

    # Border-bottom rule
    if case.expect_border:
        assert "border-bottom:" in css, (
            f"{case.name}: expected border-bottom rule in {css!r}"
        )
    else:
        assert "border-bottom" not in css, (
            f"{case.name}: expected no border-bottom rule in {css!r}"
        )
