"""Wiring contract tests for the three GUI signal-hygiene bugfixes.

Three wiring gaps addressed:

  1. ``LocalHostView.convertDeliveryRequested`` → ``MountDataTree.convert_delivery``
     Emitted by the "Convert to Mount" / "Convert to Virtual Mount" RMB
     actions but never connected in ``app._connect_signals``, so the
     gestures were silent no-ops.

  2. ``ScopeView.recreateRequested`` → ``container_ops_ui.recreate_container``
     Emitted by the "Volume Mount" gesture after adding a
     ``delivery="volume"`` spec when a container exists, but the slot
     was never wired. ScopeView also carried its own confirmation
     dialog which is now dropped — ``recreate_container`` owns the
     destructive-action confirmation.

  3. ``file_ops_ui.on_push`` / ``on_remove`` double-save
     Both handlers mutated ``_pushed_files`` via
     ``MountDataTree.add_pushed`` / ``remove_pushed`` (which emits
     ``stateChanged`` → ``_auto_save_config``) AND then called
     ``save_config`` directly. The explicit call is removed; persistence
     rides the ``stateChanged`` chain at ``app.py:400``.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.gui.file_ops_ui import FileOperationsHandler
from IgnoreScope.gui.local_host_view import LocalHostView
from IgnoreScope.gui.mount_data_tree import MountDataTree


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ──────────────────────────────────────────────
# Fix #1: convertDeliveryRequested wiring
# ──────────────────────────────────────────────


class TestConvertDeliveryWiring:
    """When wired as in ``app._connect_signals``, emitting the signal
    flips the spec's delivery on the shared MountDataTree."""

    def test_emit_with_slot_connected_flips_delivery(
        self, tmp_path: Path,
    ):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)

        view = LocalHostView(tree)
        view.convertDeliveryRequested.connect(tree.convert_delivery)

        view.convertDeliveryRequested.emit(src, "detached")

        spec = tree.get_spec_at(src)
        assert spec is not None
        assert spec.delivery == "detached"

    def test_round_trip_bind_to_detached_and_back(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        src = tmp_path / "src"
        src.mkdir()
        tree.toggle_mounted(src, True)

        view = LocalHostView(tree)
        view.convertDeliveryRequested.connect(tree.convert_delivery)

        view.convertDeliveryRequested.emit(src, "detached")
        assert tree.get_spec_at(src).delivery == "detached"

        view.convertDeliveryRequested.emit(src, "bind")
        assert tree.get_spec_at(src).delivery == "bind"


# ──────────────────────────────────────────────
# Fix #3: file_ops_ui does not double-save
# ──────────────────────────────────────────────


class TestFileOpsDoesNotDoubleSave:
    """``on_push`` / ``on_remove`` rely on the ``stateChanged`` chain
    (``add_pushed`` / ``remove_pushed`` → ``_recompute_states`` →
    ``_emit_state_changed``) for persistence. The handlers themselves
    must not call ``save_config`` directly, or every push would trigger
    two writes.
    """

    def _source_of(self, fn) -> str:
        return inspect.getsource(fn)

    def test_on_push_source_does_not_call_save_config(self):
        assert "save_config" not in self._source_of(FileOperationsHandler.on_push)

    def test_on_remove_source_does_not_call_save_config(self):
        assert "save_config" not in self._source_of(FileOperationsHandler.on_remove)

    def test_on_pull_source_does_not_call_save_config(self):
        # Pull does not mutate mount_specs or pushed_files, so it has
        # no persistence path to own — verify no accidental save either.
        assert "save_config" not in self._source_of(FileOperationsHandler.on_pull)

    def test_add_pushed_emits_state_changed(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        emitted: list[None] = []
        tree.stateChanged.connect(lambda: emitted.append(None))

        tree.add_pushed(tmp_path / "file.txt")

        assert emitted == [None]

    def test_remove_pushed_emits_state_changed(self, tmp_path: Path):
        tree = MountDataTree()
        tree.set_host_project_root(tmp_path)
        tree.add_pushed(tmp_path / "file.txt")
        emitted: list[None] = []
        tree.stateChanged.connect(lambda: emitted.append(None))

        tree.remove_pushed(tmp_path / "file.txt")

        assert emitted == [None]
