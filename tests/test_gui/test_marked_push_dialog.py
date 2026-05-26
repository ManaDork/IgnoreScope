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
def app_stub(tmp_path):
    """Minimal app stand-in: host_project_root, _current_scope, a real
    MountDataTree (so request_recompute works), and a MagicMock for
    file_ops_handler so Push-now's drain call is observable.
    """
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


def test_unmark_host_removes_from_queue(app_stub, tmp_path):
    """Skip-and-Unmark on a host row drops it from marked_push AND from
    pushed_files (matching the drain's skip_and_unmark semantic).
    """
    target = tmp_path / "src" / "a.txt"
    add_marked_push(tmp_path, SCOPE, [target])
    # Pre-seed pushed_files so we can observe the discard.
    app_stub._mount_data_tree._pushed_files.add(target)

    dlg = MarkedPushDialog(app_stub)
    dlg._list.setCurrentRow(0)
    dlg._on_unmark()

    assert load_marked_push(tmp_path, SCOPE) == set()
    assert target not in app_stub._mount_data_tree._pushed_files


def test_unmark_staged_removes_from_staged_queue(app_stub, tmp_path):
    entry = StagedEntry(
        source=tmp_path / "snap", target="/c", is_dir=True,
    )
    add_marked_staged(tmp_path, SCOPE, [entry])

    dlg = MarkedPushDialog(app_stub)
    dlg._list.setCurrentRow(0)
    dlg._on_unmark()

    assert load_marked_staged(tmp_path, SCOPE) == set()


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
