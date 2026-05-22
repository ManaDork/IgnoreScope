"""Tests for FileOperationsHandler.on_push — the marked-push inversion.

The Qt dialogs (QProgressDialog / QMessageBox) and the Docker probe are mocked;
the app is a stand-in. The marked-push queue file is real (tmp_path).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.marked_push import load_marked_push, remove_marked_push
from IgnoreScope.core.op_result import OpResult
from IgnoreScope.gui.file_ops_ui import FileOperationsHandler

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


@pytest.fixture
def host_file(tmp_path):
    f = tmp_path / "src" / "a.txt"
    f.parent.mkdir(parents=True)
    f.write_text("x", encoding="utf-8")
    return f


def _running():
    return {"running": True, "status": "running"}


def test_on_push_always_enqueues_even_when_no_container(app, host_file, tmp_path):
    h = FileOperationsHandler(app)
    with patch("IgnoreScope.docker.container_ops.get_container_info", return_value=None), \
         patch("IgnoreScope.gui.file_ops_ui.drain_with_user_feedback") as drain:
        h.on_push(host_file)
    assert load_marked_push(tmp_path, SCOPE) == {host_file}
    drain.assert_not_called()
    app.statusBar().showMessage.assert_called()  # "Marked … for push"


def test_on_push_stopped_container_does_not_drain(app, host_file, tmp_path):
    h = FileOperationsHandler(app)
    with patch("IgnoreScope.docker.container_ops.get_container_info",
               return_value={"running": False, "status": "exited"}), \
         patch("IgnoreScope.gui.file_ops_ui.drain_with_user_feedback") as drain:
        h.on_push(host_file)
    assert load_marked_push(tmp_path, SCOPE) == {host_file}
    drain.assert_not_called()


def test_on_push_running_container_drains_and_resyncs(app, host_file, tmp_path):
    h = FileOperationsHandler(app)

    def fake_drain(hpr, scope, **kw):
        remove_marked_push(hpr, scope, [host_file])  # simulate a successful cp
        return OpResult(success=True, message="Drained 1 file(s)")

    with patch("IgnoreScope.docker.container_ops.get_container_info", return_value=_running()), \
         patch("IgnoreScope.gui.file_ops_ui.QProgressDialog"), \
         patch("IgnoreScope.gui.file_ops_ui.drain_with_user_feedback", side_effect=fake_drain) as drain:
        h.on_push(host_file)

    drain.assert_called_once()
    # on_stale + progress wired
    assert "on_stale_cb" in drain.call_args.kwargs and "progress_cb" in drain.call_args.kwargs
    app.config_manager.reload_current_scope.assert_called_once()
    msgs = [c.args[0] for c in app.statusBar().showMessage.call_args_list]
    assert any("Pushed a.txt" in m for m in msgs)
    assert load_marked_push(tmp_path, SCOPE) == set()


def test_on_push_still_queued_after_drain_warns(app, host_file, tmp_path):
    h = FileOperationsHandler(app)
    fail = OpResult(success=False, message="0 drained, 1 still queued",
                    details=[f"cp failed, left queued: {host_file} — denied"])
    with patch("IgnoreScope.docker.container_ops.get_container_info", return_value=_running()), \
         patch("IgnoreScope.gui.file_ops_ui.QProgressDialog"), \
         patch("IgnoreScope.gui.file_ops_ui.QMessageBox") as msgbox, \
         patch("IgnoreScope.gui.file_ops_ui.drain_with_user_feedback", return_value=fail):
        h.on_push(host_file)
    msgbox.warning.assert_called_once()


def test_on_push_skipped_and_unmarked_reports_unmark(app, host_file, tmp_path):
    h = FileOperationsHandler(app)

    def fake_drain(hpr, scope, **kw):
        remove_marked_push(hpr, scope, [host_file])  # unmark dequeues it
        return OpResult(success=True, message="Drained 0 file(s)",
                        details=[f"skipped and unmarked: {host_file}"])

    with patch("IgnoreScope.docker.container_ops.get_container_info", return_value=_running()), \
         patch("IgnoreScope.gui.file_ops_ui.QProgressDialog"), \
         patch("IgnoreScope.gui.file_ops_ui.drain_with_user_feedback", side_effect=fake_drain):
        h.on_push(host_file)
    msgs = [c.args[0] for c in app.statusBar().showMessage.call_args_list]
    assert any("Unmarked a.txt" in m for m in msgs)


def test_on_push_placeholder_scope_is_noop(app, host_file, tmp_path):
    from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
    app._current_scope = PLACEHOLDER_SCOPE
    h = FileOperationsHandler(app)
    h.on_push(host_file)
    assert load_marked_push(tmp_path, PLACEHOLDER_SCOPE) == set()
