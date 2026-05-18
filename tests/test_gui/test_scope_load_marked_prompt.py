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
    cm = ConfigManager(app)
    with patch("IgnoreScope.gui.config_manager.QMessageBox") as msgbox:
        cm._post_scope_load()
    msgbox.assert_not_called()
    app.file_ops_handler.drain_marked_push_now.assert_not_called()


def test_placeholder_scope_no_prompt(app, tmp_path):
    from IgnoreScope.gui.app import PLACEHOLDER_SCOPE
    app._current_scope = PLACEHOLDER_SCOPE
    cm = ConfigManager(app)
    add_marked_push(tmp_path, PLACEHOLDER_SCOPE, [tmp_path / "a.txt"])
    with patch("IgnoreScope.gui.config_manager.QMessageBox") as msgbox:
        cm._post_scope_load()
    msgbox.assert_not_called()


def test_now_triggers_drain(app, tmp_path):
    cm = ConfigManager(app)
    add_marked_push(tmp_path, SCOPE, [tmp_path / "a.txt"])
    with patch("IgnoreScope.gui.config_manager.QMessageBox") as msgbox:
        box = msgbox.return_value
        # clickedButton() returns the same object addButton() returned → the "Now" button.
        box.clickedButton.return_value = box.addButton.return_value
        cm._post_scope_load()
    app.file_ops_handler.drain_marked_push_now.assert_called_once()


def test_delay_leaves_queue_and_shows_status(app, tmp_path):
    cm = ConfigManager(app)
    add_marked_push(tmp_path, SCOPE, [tmp_path / "a.txt"])
    with patch("IgnoreScope.gui.config_manager.QMessageBox") as msgbox:
        # clickedButton() returns a fresh mock ≠ the "Now" button → "Delay".
        msgbox.return_value.clickedButton.return_value = object()
        cm._post_scope_load()
    app.file_ops_handler.drain_marked_push_now.assert_not_called()
    app.statusBar().showMessage.assert_called()
    from IgnoreScope.core.marked_push import load_marked_push
    assert load_marked_push(tmp_path, SCOPE) == {tmp_path / "a.txt"}
