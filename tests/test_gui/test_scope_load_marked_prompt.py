"""Tests for ConfigManager._post_scope_load — the scope-load marked-push prompt."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.marked_push import add_marked_push
from IgnoreScope.gui.config_manager import ConfigManager

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


def test_empty_queue_no_prompt(app, tmp_path):
    """Empty queues → no dialog, no drain, no status message."""
    cm = ConfigManager(app)
    cm._post_scope_load()
    app._show_marked_push_dialog.assert_not_called()
    app.file_ops_handler.drain_marked_push_now.assert_not_called()


def test_placeholder_scope_no_prompt(app, tmp_path):
    from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
    app._current_scope = PLACEHOLDER_SCOPE
    cm = ConfigManager(app)
    add_marked_push(tmp_path, PLACEHOLDER_SCOPE, [tmp_path / "a.txt"])
    cm._post_scope_load()
    app._show_marked_push_dialog.assert_not_called()


def test_container_exists_opens_dialog_modally(app, tmp_path):
    """Phase B.4 — when container exists + queue non-empty, _post_scope_load
    opens MarkedPushDialog modally (replaces the old QMessageBox).
    """
    cm = ConfigManager(app)
    add_marked_push(tmp_path, SCOPE, [tmp_path / "a.txt"])
    with patch(
        "IgnoreScope.docker.container_ops.container_exists",
        return_value=True,
    ):
        cm._post_scope_load()
    # Dialog opened modally — no separate Now/Delay branching here; the
    # dialog's own Push now button drives the drain.
    app._show_marked_push_dialog.assert_called_once_with(modal=True)
    # The QMessageBox is gone — no clickedButton-based dispatch.
    app.file_ops_handler.drain_marked_push_now.assert_not_called()
    # Queue still intact (drain happens only if the user clicks Push now
    # inside the dialog — the dialog's Push button calls drain itself).
    from IgnoreScope.core.marked_push import load_marked_push
    assert load_marked_push(tmp_path, SCOPE) == {tmp_path / "a.txt"}


# ── Phase B.1 — container-existence gating ──────────────────────────────────


def test_no_container_replaces_modal_with_status_message(app, tmp_path):
    """If no container exists for the current scope, the prompt is replaced
    by a non-modal status-bar message. This is the user's E:\\GITM\\_OJAAF\\OJAAF
    repro from files-marked-for-push-fatal-crash.md — clicking "Now" with no
    container was the GUI-crash trigger (the followup data_only reload
    rebuilt sibling/extension subtrees while the proxy held stale indices).
    Removing the modal removes the trigger AND removes a misleading UX
    affordance ("push now?" when there's nowhere to push).
    """
    cm = ConfigManager(app)
    add_marked_push(tmp_path, SCOPE, [tmp_path / "a.txt"])
    with patch(
        "IgnoreScope.docker.container_ops.container_exists",
        return_value=False,
    ):
        cm._post_scope_load()

    # Dialog NOT opened.
    app._show_marked_push_dialog.assert_not_called()
    # Drain NOT triggered.
    app.file_ops_handler.drain_marked_push_now.assert_not_called()
    # Status-bar message instead.
    app.statusBar().showMessage.assert_called_once()
    msg_arg = app.statusBar().showMessage.call_args.args[0]
    assert "marked for push" in msg_arg
    assert "Create Container" in msg_arg
    # Queue untouched.
    from IgnoreScope.core.marked_push import load_marked_push
    assert load_marked_push(tmp_path, SCOPE) == {tmp_path / "a.txt"}
