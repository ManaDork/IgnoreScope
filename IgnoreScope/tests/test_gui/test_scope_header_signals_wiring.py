"""Tests for Phase 3 Task 3.2: container_running wiring + unified_mount_specs.

Covers:
  - MountDataTree.unified_mount_specs() merges user + extension-synthesized specs
  - _query_is_container_running short-circuits on placeholder/empty scope
  - _query_is_container_running delegates to get_container_info
  - ScopeView._compute_header_signals composes the full signal triple
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.local_mount_config import ExtensionConfig
from IgnoreScope.gui.mount_data_tree import MountDataTree
from IgnoreScope.gui.scope_view import (
    ScopeView,
    _query_is_container_running,
)
from IgnoreScope.gui.style_engine import ScopeHeaderSignals, StyleGui


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


# ──────────────────────────────────────────────
# MountDataTree.unified_mount_specs()
# ──────────────────────────────────────────────


class TestUnifiedMountSpecs:
    def test_empty_tree_returns_empty_list(self):
        tree = MountDataTree()
        assert tree.unified_mount_specs() == []

    def test_user_specs_only(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        unified = tree.unified_mount_specs()
        assert len(unified) == 1
        assert unified[0].delivery == "bind"
        assert unified[0].owner == "user"

    def test_extension_specs_only(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        ext = ExtensionConfig(
            name="claude",
            isolation_paths=["/root/.claude", "/root/.anthropic"],
        )
        tree._extensions.append(ext)
        unified = tree.unified_mount_specs()
        assert len(unified) == 2
        assert all(s.delivery == "volume" for s in unified)
        assert all(s.owner == "extension:claude" for s in unified)

    def test_user_plus_extension_specs_merged(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        ext = ExtensionConfig(
            name="claude", isolation_paths=["/root/.claude"],
        )
        tree._extensions.append(ext)
        unified = tree.unified_mount_specs()
        assert len(unified) == 2
        deliveries = {s.delivery for s in unified}
        assert deliveries == {"bind", "volume"}

    def test_returns_fresh_list_each_call(self, tmp_path: Path):
        # Callers mutating the returned list must not affect tree state.
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        first = tree.unified_mount_specs()
        first.clear()
        second = tree.unified_mount_specs()
        assert len(second) == 1


# ──────────────────────────────────────────────
# _query_is_container_running short-circuits
# ──────────────────────────────────────────────


class TestQueryIsContainerRunningShortCircuits:
    def test_none_host_root_returns_false(self):
        # Should short-circuit WITHOUT calling get_container_info.
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
        ) as mock:
            result = _query_is_container_running(None, "scope")
        assert result is False
        mock.assert_not_called()

    def test_empty_scope_name_returns_false(self, tmp_path: Path):
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
        ) as mock:
            result = _query_is_container_running(tmp_path, "")
        assert result is False
        mock.assert_not_called()

    def test_placeholder_scope_returns_false(self, tmp_path: Path):
        from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
        ) as mock:
            result = _query_is_container_running(tmp_path, PLACEHOLDER_SCOPE)
        assert result is False
        mock.assert_not_called()


# ──────────────────────────────────────────────
# _query_is_container_running delegates to get_container_info
# ──────────────────────────────────────────────


class TestQueryIsContainerRunningDelegates:
    def test_missing_container_returns_false(self, tmp_path: Path):
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
            return_value=None,
        ):
            assert _query_is_container_running(tmp_path, "scope") is False

    def test_running_container_returns_true(self, tmp_path: Path):
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
            return_value={"running": True},
        ):
            assert _query_is_container_running(tmp_path, "scope") is True

    def test_stopped_container_returns_false(self, tmp_path: Path):
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
            return_value={"running": False},
        ):
            assert _query_is_container_running(tmp_path, "scope") is False

    def test_missing_running_key_returns_false(self, tmp_path: Path):
        with patch(
            "IgnoreScope.docker.container_ops.get_container_info",
            return_value={},
        ):
            assert _query_is_container_running(tmp_path, "scope") is False


# ──────────────────────────────────────────────
# ScopeView._compute_header_signals composition
# ──────────────────────────────────────────────


class TestComputeHeaderSignals:
    @pytest.fixture
    def tree_and_view(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        tree.current_scope = "test_scope"
        view = ScopeView(tree)
        return tree, view

    def test_empty_scope_off(self, tree_and_view, tmp_path: Path):
        tree, view = tree_and_view
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            signals = view._compute_header_signals()
        assert signals == ScopeHeaderSignals(
            container_running=False, fully_virtual=False, has_mounts=False,
        )

    def test_bind_only_running(self, tree_and_view, tmp_path: Path):
        tree, view = tree_and_view
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            signals = view._compute_header_signals()
        assert signals == ScopeHeaderSignals(
            container_running=True, fully_virtual=False, has_mounts=True,
        )

    def test_detached_only_fully_virtual(self, tree_and_view, tmp_path: Path):
        tree, view = tree_and_view
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_detached_mount(src, True)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=False,
        ):
            signals = view._compute_header_signals()
        assert signals == ScopeHeaderSignals(
            container_running=False, fully_virtual=True, has_mounts=False,
        )

    def test_extension_only_fully_virtual(self, tree_and_view, tmp_path: Path):
        # Extension-synthesized volume specs (e.g., Claude auth) count as virtual.
        tree, view = tree_and_view
        ext = ExtensionConfig(name="claude", isolation_paths=["/root/.claude"])
        tree._extensions.append(ext)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            signals = view._compute_header_signals()
        assert signals == ScopeHeaderSignals(
            container_running=True, fully_virtual=True, has_mounts=False,
        )

    def test_user_bind_plus_extension_not_fully_virtual(
        self, tree_and_view, tmp_path: Path,
    ):
        # Any bind spec (user-authored) flips fully_virtual to False.
        tree, view = tree_and_view
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)
        ext = ExtensionConfig(name="claude", isolation_paths=["/root/.claude"])
        tree._extensions.append(ext)
        with patch(
            "IgnoreScope.gui.scope_view._query_is_container_running",
            return_value=True,
        ):
            signals = view._compute_header_signals()
        assert signals == ScopeHeaderSignals(
            container_running=True, fully_virtual=False, has_mounts=True,
        )
