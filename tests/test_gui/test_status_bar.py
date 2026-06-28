"""Tests for the status-bar version label + empty-state casing (version-number-gui).

Pins the contract introduced by the ``version-number-gui`` feature:
  * A version label renders ``V{__version__}  |  `` and is the LEFT-MOST
    status-bar widget (left of the project/scope label).
  * The empty-state (no project loaded) label reads the title-cased
    ``"No Project Loaded"``.
  * The displayed version tracks ``IgnoreScope._version.__version__`` — no
    hardcoded copy.

Follows the suite convention: raw ``QApplication`` via a module-scoped
``_qapp`` fixture (no pytest-qt). Geometry is realized with
``WA_DontShowOnScreen`` so the left-of assertion does not flash a window.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from IgnoreScope._version import __version__
from IgnoreScope.gui.app import IgnoreScopeApp


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(_qapp):
    win = IgnoreScopeApp(host_project_root=None)
    yield win
    win.close()
    win.deleteLater()


def test_version_label_text_tracks_version(window):
    """Rendered prefix is ``V<version>  |  `` sourced from ``__version__``."""
    assert window.version_label.text() == f"V{__version__}  |  "


def test_empty_state_is_title_cased(window):
    """No project loaded → the title-cased empty-state literal."""
    window.host_project_root = None
    window._update_status()
    assert window.status_label.text() == "No Project Loaded"


def test_version_label_is_left_of_status_label(window):
    """The version label sits to the LEFT of the project/scope label.

    ``QStatusBar.addWidget`` lays widgets left-to-right in insertion order;
    the version label is added first. We realize geometry off-screen
    (``WA_DontShowOnScreen``) rather than showing a real window.
    """
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.show()
    QApplication.processEvents()
    assert window.version_label.x() < window.status_label.x()
