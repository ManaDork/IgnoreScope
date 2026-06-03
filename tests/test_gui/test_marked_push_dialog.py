"""Tests for the MarkedPushDialog (Phase B.3 — per-row review surface)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.marked_push import add_marked_push, load_marked_push
from IgnoreScope.core.marked_staged import (
    StagedEntry,
    add_marked_staged,
    load_marked_staged,
)
from IgnoreScope.gui.marked_push_dialog import MarkedPushDialog
from IgnoreScope.gui.mount_data_tree import MountDataTree

SCOPE = "dev"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def app_stub(tmp_path, monkeypatch):
    """Minimal app stand-in: host_project_root, _current_scope, a real
    MountDataTree (so request_recompute works), and a MagicMock for
    file_ops_handler so Push-now's drain call is observable.

    Mocks ``container_exists=True`` by default so the dialog's Push button
    is enabled — matches the most common test scenario. Tests covering
    the no-container path override this with their own monkeypatch.
    """
    monkeypatch.setattr(
        "IgnoreScope.docker.container_ops.container_exists",
        lambda _docker_name: True,
    )
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    stub = SimpleNamespace(
        host_project_root=tmp_path,
        _current_scope=SCOPE,
        _mount_data_tree=tree,
        file_ops_handler=MagicMock(),
    )
    return stub


def test_dialog_empty_queue_summary(app_stub):
    """Empty queues → summary says so, no rows."""
    dlg = MarkedPushDialog(app_stub)
    assert dlg._list.count() == 0
    assert "empty" in dlg._summary.text().lower()


def test_dialog_lists_host_queue_rows(app_stub, tmp_path):
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "b.txt"])
    dlg = MarkedPushDialog(app_stub)
    assert dlg._list.count() == 2
    assert "2 file(s)" in dlg._summary.text()


def test_dialog_lists_staged_queue_rows(app_stub, tmp_path):
    entry = StagedEntry(
        source=tmp_path / "snap",
        target="/container/path",
        is_dir=True,
    )
    add_marked_staged(tmp_path, SCOPE, [entry])
    dlg = MarkedPushDialog(app_stub)
    assert dlg._list.count() == 1
    label = dlg._list.item(0).text()
    assert "[staged]" in label
    assert "/container/path" in label


def test_reveal_emits_for_host_row(app_stub, tmp_path):
    """Selecting a host-queue row + Reveal → revealRequested(path) emits."""
    target = tmp_path / "src" / "a.txt"
    add_marked_push(tmp_path, SCOPE, [target])
    dlg = MarkedPushDialog(app_stub)
    dlg._list.setCurrentRow(0)

    captured: list[Path] = []
    dlg.revealRequested.connect(lambda p: captured.append(p))

    dlg._on_reveal()
    assert captured == [target]


def test_reveal_no_op_for_staged_row(app_stub, tmp_path):
    """Staged rows have no host-tree path; Reveal is a no-op (no signal)."""
    add_marked_staged(
        tmp_path, SCOPE,
        [StagedEntry(source=tmp_path / "snap", target="/c", is_dir=True)],
    )
    dlg = MarkedPushDialog(app_stub)
    dlg._list.setCurrentRow(0)

    captured = []
    dlg.revealRequested.connect(lambda p: captured.append(p))
    dlg._on_reveal()
    assert captured == []


def test_push_now_calls_full_drain(app_stub, tmp_path):
    """Push now triggers the full drain via drain_marked_push_now (Decision
    locked in plan §B.3: per-file drain deferred — engine errors on the
    file-missing-from-list path).
    """
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    dlg = MarkedPushDialog(app_stub)
    dlg._list.setCurrentRow(0)
    dlg._on_push_now()

    app_stub.file_ops_handler.drain_marked_push_now.assert_called_once()


def test_double_click_host_row_emits_reveal(app_stub, tmp_path):
    """Phase B.4 — double-clicking a host row is a shortcut for the Reveal
    button; emits revealRequested(path) with the row's host path.
    """
    target = tmp_path / "src" / "a.txt"
    add_marked_push(tmp_path, SCOPE, [target])
    dlg = MarkedPushDialog(app_stub)

    captured: list[Path] = []
    dlg.revealRequested.connect(lambda p: captured.append(p))

    item = dlg._list.item(0)
    dlg._on_row_double_clicked(item)

    assert captured == [target]


def test_double_click_staged_row_does_not_emit(app_stub, tmp_path):
    """Staged rows have no host-tree path — double-click is a no-op."""
    add_marked_staged(
        tmp_path, SCOPE,
        [StagedEntry(source=tmp_path / "snap", target="/c", is_dir=True)],
    )
    dlg = MarkedPushDialog(app_stub)

    captured: list[Path] = []
    dlg.revealRequested.connect(lambda p: captured.append(p))

    item = dlg._list.item(0)
    dlg._on_row_double_clicked(item)

    assert captured == []


# ── Phase B.5 — Push Marked Files gated on container existence ─────────────


def test_push_button_disabled_when_no_container(tmp_path, monkeypatch):
    """If no container exists for the current scope, Push Marked Files is
    disabled with an informative tooltip. Clicking it would otherwise
    dead-end on the drain's "Container not created" early return.
    """
    monkeypatch.setattr(
        "IgnoreScope.docker.container_ops.container_exists",
        lambda _docker_name: False,
    )
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)
    stub = SimpleNamespace(
        host_project_root=tmp_path,
        _current_scope=SCOPE,
        _mount_data_tree=tree,
        file_ops_handler=MagicMock(),
    )
    dlg = MarkedPushDialog(stub)

    assert not dlg._push_btn.isEnabled()
    assert "Create Container" in dlg._push_btn.toolTip()
    # Reveal button stays enabled — the user can still navigate to files.
    assert dlg._reveal_btn.isEnabled()
    # Close stays enabled — always escapable.
    assert dlg._close_btn.isEnabled()


def test_push_button_enabled_when_container_exists(app_stub):
    """Container exists → button enabled, no tooltip warning."""
    dlg = MarkedPushDialog(app_stub)
    assert dlg._push_btn.isEnabled()
    assert dlg._push_btn.toolTip() == ""


def test_push_button_disabled_with_no_project(tmp_path, monkeypatch):
    """No host_project_root → disabled with "No project loaded" tooltip."""
    monkeypatch.setattr(
        "IgnoreScope.docker.container_ops.container_exists",
        lambda _docker_name: True,
    )
    stub = SimpleNamespace(
        host_project_root=None,
        _current_scope=SCOPE,
        _mount_data_tree=MountDataTree(),
        file_ops_handler=MagicMock(),
    )
    dlg = MarkedPushDialog(stub)
    assert not dlg._push_btn.isEnabled()
    assert "No project" in dlg._push_btn.toolTip()
