"""System Tray Icon.

IS: QSystemTrayIcon lifecycle, tray context menu (Show/Hide, Exit),
tray-based window visibility toggle, application quit sequence.

IS NOT: Menu bar (menus.py), window close event override (app.py),
Docker container operations (container_ops_ui.py).
"""

from __future__ import annotations

from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMainWindow, QMenu, QSystemTrayIcon


class SystemTrayManager:
    """Manages system tray icon and context menu.

    Composition pattern: takes an app reference (QMainWindow) and
    delegates all window operations through it.
    """

    def __init__(self, app: QMainWindow):
        self._app = app
        self._setup_tray()

    def _setup_tray(self):
        """Create system tray icon with context menu."""
        from PyQt6.QtWidgets import QApplication

        self._tray_icon = QSystemTrayIcon(
            QApplication.instance().windowIcon(), self._app
        )

        tray_menu = QMenu(self._app)
        self._tray_toggle_action = QAction("Hide", self._app)
        self._tray_toggle_action.triggered.connect(self._toggle_visibility)
        tray_menu.addAction(self._tray_toggle_action)
        tray_menu.addSeparator()
        exit_action = QAction("Exit", self._app)
        exit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(exit_action)

        # Update toggle text when menu is about to show
        tray_menu.aboutToShow.connect(self._update_tray_toggle_text)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _update_tray_toggle_text(self):
        """Set Show/Hide text based on current window visibility."""
        self._tray_toggle_action.setText(
            "Hide" if self._app.isVisible() else "Show"
        )

    def _toggle_visibility(self):
        """Toggle window visibility from tray."""
        if self._app.isVisible():
            self._app.hide()
        else:
            self._app.show()
            self._app.activateWindow()

    def _on_tray_activated(self, reason):
        """Handle tray icon double-click to toggle visibility."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    # ── Public API ───────────────────────────────────────────

    def is_tray_visible(self) -> bool:
        """Whether the tray icon is currently visible."""
        return self._tray_icon.isVisible()

    def quit_app(self):
        """Full exit: save layout, cleanup, hide tray, quit."""
        self._app._save_layout()
        if self._app.host_project_root:
            self._app.config_manager._cleanup_placeholder()
        self._tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()
