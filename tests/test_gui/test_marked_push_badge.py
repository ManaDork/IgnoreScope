"""Tests for the status-bar MarkedPushBadge widget (Phase B.3).

Pins the badge's count + visibility + click contract:
  * Hidden when count == 0 (no badge until queue has entries).
  * Visible with correct count when queue non-empty.
  * Count refreshes on update_count() reading the current app state.
  * Click emits the ``clicked`` signal.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.marked_push import add_marked_push
from IgnoreScope.gui.marked_push_badge import MarkedPushBadge

SCOPE = "dev"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def app_stub(tmp_path):
    """Minimal app stand-in for the badge: only ``host_project_root`` +
    ``_current_scope`` are read by ``update_count``."""
    return SimpleNamespace(
        host_project_root=tmp_path,
        _current_scope=SCOPE,
    )


def test_badge_hidden_with_empty_queue(app_stub):
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    assert badge.count == 0
    assert not badge.isVisible() or badge.isHidden()


def test_badge_visible_and_counts_host_queue(app_stub, tmp_path):
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    assert badge.count == 1


def test_badge_counts_combined_host_plus_staged(app_stub, tmp_path):
    from IgnoreScope.core.marked_staged import StagedEntry, add_marked_staged
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    add_marked_staged(
        tmp_path, SCOPE,
        [StagedEntry(source=tmp_path / "snap", target="/c", is_dir=True)],
    )
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    assert badge.count == 2


def test_badge_zero_when_no_project_loaded():
    """No host_project_root → count=0 regardless of queue state on disk."""
    stub = SimpleNamespace(host_project_root=None, _current_scope=SCOPE)
    badge = MarkedPushBadge(stub)
    badge.update_count()
    assert badge.count == 0


def test_badge_zero_for_placeholder_scope(app_stub):
    """An unset scope (None / empty string) → count=0."""
    app_stub._current_scope = ""
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    assert badge.count == 0


def test_badge_click_emits_signal(app_stub, tmp_path):
    """Left-click emits ``clicked`` — used by the app to open MarkedPushDialog."""
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    badge.show()  # required so the widget is realized for event processing

    fired = []
    badge.clicked.connect(lambda: fired.append(True))

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    badge.mousePressEvent(event)

    assert fired == [True]


def test_badge_right_click_does_not_emit(app_stub, tmp_path):
    """Only left-click should emit — right-click reserved for future menu."""
    add_marked_push(tmp_path, SCOPE, [tmp_path / "src" / "a.txt"])
    badge = MarkedPushBadge(app_stub)
    badge.update_count()
    badge.show()

    fired = []
    badge.clicked.connect(lambda: fired.append(True))

    event = QMouseEvent(
        QMouseEvent.Type.MouseButtonPress,
        QPointF(5, 5),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    badge.mousePressEvent(event)

    assert fired == []
