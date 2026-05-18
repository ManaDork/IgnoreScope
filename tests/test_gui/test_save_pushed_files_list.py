"""Tests for ContainerOperations.save_pushed_files_list and the Recreate auto-dump.

`save_pushed_files_list(auto=False)` is the menu entry — opens a Save dialog and
writes the user's chosen path. `save_pushed_files_list(auto=True)` is the path
``recreate_container`` uses to drop a timestamped snapshot under
``.ignore_scope/<scope>/`` before destroying the container.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from IgnoreScope.core.config import ScopeDockerConfig, get_container_dir, save_config
from IgnoreScope.gui.container_ops_ui import ContainerOperations

SCOPE = "dev"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def app(tmp_path):
    m = MagicMock()
    m.host_project_root = tmp_path
    m._current_scope = SCOPE
    return m


def _save_config_with_pushed(tmp_path, *rel_paths):
    cfg = ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE)
    for rel in rel_paths:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
        cfg.pushed_files.add(p)
    save_config(cfg)
    return cfg


# ── Interactive (auto=False) ──────────────────────────────────────


def test_save_writes_relative_posix_lines(app, tmp_path):
    _save_config_with_pushed(tmp_path, "src/a.txt", "b.txt")
    out = tmp_path / "out.txt"
    co = ContainerOperations(app)
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=(str(out), "")):
        result = co.save_pushed_files_list()
    assert out.read_text(encoding="utf-8").splitlines() == ["b.txt", "src/a.txt"]
    assert result == out
    app.statusBar().showMessage.assert_called()


def test_save_no_pushed_files_shows_info(app, tmp_path):
    save_config(ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE))
    co = ContainerOperations(app)
    with patch("IgnoreScope.gui.container_ops_ui.QMessageBox") as msgbox, \
         patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as save_dlg:
        result = co.save_pushed_files_list()
    msgbox.information.assert_called_once()
    save_dlg.assert_not_called()
    assert result is None


def test_save_cancelled_dialog_is_noop(app, tmp_path):
    _save_config_with_pushed(tmp_path, "a.txt")
    co = ContainerOperations(app)
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName", return_value=("", "")):
        result = co.save_pushed_files_list()
    app.statusBar().showMessage.assert_not_called()
    assert result is None


def test_save_placeholder_scope_is_noop(app, tmp_path):
    from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
    app._current_scope = PLACEHOLDER_SCOPE
    co = ContainerOperations(app)
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as save_dlg:
        result = co.save_pushed_files_list()
    save_dlg.assert_not_called()
    assert result is None


# ── Auto-dump (auto=True) — Recreate flow ─────────────────────────


def test_auto_writes_timestamped_file_under_scope_dir(app, tmp_path):
    _save_config_with_pushed(tmp_path, "src/a.txt", "b.txt")
    co = ContainerOperations(app)
    with patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as save_dlg:
        result = co.save_pushed_files_list(auto=True)
    # No Save dialog in auto mode.
    save_dlg.assert_not_called()
    assert result is not None
    expected_dir = get_container_dir(tmp_path, SCOPE)
    assert result.parent == expected_dir
    # Name is pushed_files_<YYYYMMDD_HHMMSS>.txt
    assert re.fullmatch(r"pushed_files_\d{8}_\d{6}\.txt", result.name)
    assert result.read_text(encoding="utf-8").splitlines() == ["b.txt", "src/a.txt"]
    # Auto mode is silent on the status bar.
    app.statusBar().showMessage.assert_not_called()


def test_auto_no_pushed_files_returns_none_silently(app, tmp_path):
    save_config(ScopeDockerConfig(host_project_root=tmp_path, scope_name=SCOPE))
    co = ContainerOperations(app)
    with patch("IgnoreScope.gui.container_ops_ui.QMessageBox") as msgbox, \
         patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as save_dlg:
        result = co.save_pushed_files_list(auto=True)
    assert result is None
    # Auto mode never raises a dialog — no info box, no save dialog.
    msgbox.information.assert_not_called()
    msgbox.warning.assert_not_called()
    save_dlg.assert_not_called()


# ── Recreate wires the auto-dump + the host re-queue ──────────────


def test_recreate_auto_dumps_and_requeues_pushed_files(app, tmp_path):
    """recreate_container must (1) write a timestamped pushed-files snapshot,
    (2) enqueue every pushed_file into the host marked-push queue *before*
    removing the container, so the post-create drain re-pushes them from host.
    """
    from IgnoreScope.core.marked_push import load_marked_push
    cfg = _save_config_with_pushed(tmp_path, "src/a.txt", "b.txt")

    co = ContainerOperations(app)
    co._validate_and_save_config = MagicMock(return_value=cfg)
    co._run_container_operation = MagicMock()

    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes,
    ) as question, \
         patch("PyQt6.QtWidgets.QFileDialog.getSaveFileName") as save_dlg:
        co.recreate_container()

    # The Recreate confirmation should reflect the new "re-pushed from host" copy.
    confirm_text = question.call_args.args[2]
    assert "re-pushed from the host" in confirm_text
    assert "in-container edits" in confirm_text

    # Auto-dump used the scope dir, NOT the QFileDialog.
    save_dlg.assert_not_called()
    snapshots = list(get_container_dir(tmp_path, SCOPE).glob("pushed_files_*.txt"))
    assert len(snapshots) == 1
    assert snapshots[0].read_text(encoding="utf-8").splitlines() == ["b.txt", "src/a.txt"]

    # Host marked-push queue now contains every previously pushed file.
    queued = load_marked_push(tmp_path, SCOPE)
    assert queued == set(cfg.pushed_files)

    # And the orchestration was kicked off (not synchronously here — the
    # ContainerWorker thread is what would actually call execute_remove +
    # execute_create).
    co._run_container_operation.assert_called_once()


def test_recreate_cancel_does_not_dump_or_requeue(app, tmp_path):
    from IgnoreScope.core.marked_push import load_marked_push
    cfg = _save_config_with_pushed(tmp_path, "a.txt")

    co = ContainerOperations(app)
    co._validate_and_save_config = MagicMock(return_value=cfg)
    co._run_container_operation = MagicMock()

    with patch.object(
        QMessageBox, "question", return_value=QMessageBox.StandardButton.No,
    ):
        co.recreate_container()

    # No snapshot file, no queue mutation, no orchestration.
    assert not list(get_container_dir(tmp_path, SCOPE).glob("pushed_files_*.txt"))
    assert load_marked_push(tmp_path, SCOPE) == set()
    co._run_container_operation.assert_not_called()
