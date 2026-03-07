"""Window Assembly + Data Layer + Signal Wiring.

Creates the QMainWindow, 2 QDockWidgets, and status bar. Arranges docks into
default layout and persists user arrangement via QSettings. Applies the
application stylesheet from StyleGui.

Data layer (L2): Creates MountDataTree, injects LocalHostView and ScopeView
into dock placeholders.

Signal wiring (L6): Instantiates ConfigManager, FileOperationsHandler,
ContainerOperations. Connects all menu actions and view signals.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QAction, QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QDockWidget,
    QLabel,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QMenu,
)

from .style_engine import StyleGui
from .container_root_panel import ContainerRootPanel
from .menus import MenuManager
from .mount_data_tree import MountDataTree
from .local_host_view import LocalHostView
from .scope_view import ScopeView

PLACEHOLDER_SCOPE = "temp"


class IgnoreScopeApp(QMainWindow):
    """Main application window with QDockWidget-based layout.

    Public attributes (docks -- 2 total):
        local_host_dock, scope_dock

    Public attributes (content):
        local_host_config_container (QWidget) -- tree placeholder (top of local_host_dock)
        scope_config_container (QWidget) -- tree placeholder (top of scope_dock)
        container_root_panel (ContainerRootPanel) -- header + JSON viewer (bottom of scope_dock)

    Public attributes (data layer):
        _mount_data_tree (MountDataTree)

    Public attributes (views):
        _local_host (LocalHostView), _scope_view (ScopeView)

    Public attributes (state):
        _current_scope (str)

    Public attributes (startup params):
        host_project_root (Optional[Path]) -- host project root from CLI
        dev_mode (bool) -- developer mode flag from CLI

    Public attributes (other):
        menu_manager (MenuManager), status_label (QLabel)
        config_manager (ConfigManager), file_ops_handler (FileOperationsHandler)
        container_ops (ContainerOperations)
    """

    def __init__(
        self,
        host_project_root: Optional[Path] = None,
        *,
        dev_mode: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.host_project_root = host_project_root
        self.dev_mode = dev_mode
        self._settings = QSettings("IgnoreScope", "IgnoreScope")

        self._setup_ui()
        self._setup_docks()
        self._setup_menus()

        # Runtime state
        self._current_scope: str = PLACEHOLDER_SCOPE
        self._loading: bool = False

        # Data layer
        self._mount_data_tree = MountDataTree(parent=self)

        # Views — inject into dock placeholders
        self._local_host = LocalHostView(self._mount_data_tree)
        self.local_host_config_container.layout().addWidget(self._local_host)

        self._scope_view = ScopeView(self._mount_data_tree)
        self.scope_config_container.layout().addWidget(self._scope_view)

        # Arrange docks after views are injected — dock sizeHints must
        # reflect actual content for Qt to compute correct proportions
        self._arrange_default_layout()

        # Logic Phase handlers
        from .config_manager import ConfigManager
        from .file_ops_ui import FileOperationsHandler
        from .container_ops_ui import ContainerOperations

        self.config_manager = ConfigManager(self)
        self.file_ops_handler = FileOperationsHandler(self)
        self.container_ops = ContainerOperations(self)

        self._connect_signals()
        self._setup_tray()
        self._restore_layout()

        # Auto-open project if passed via CLI
        if self.host_project_root:
            self.config_manager.open_project(self.host_project_root)

    # ── Setup ────────────────────────────────────────────────

    def _setup_ui(self):
        """Window title, size, stylesheet, central widget, status bar."""
        self.setWindowTitle("IgnoreScope")
        self.setMinimumSize(1100, 700)
        self.resize(1400, 900)
        self.setStyleSheet(StyleGui.instance().build_stylesheet())

        # Hidden central widget — docks fill entire window
        central = QWidget()
        central.setMaximumSize(0, 0)
        self.setCentralWidget(central)

        # Status bar
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_label = QLabel("No project loaded")
        status_bar.addWidget(self.status_label)

    def _setup_docks(self):
        """Create 3 QDockWidgets with container layouts."""

        # ── Local Host Configuration (left) ──
        # Tree container (populated later via view injection)
        self.local_host_dock = QDockWidget("Local Host Configuration", self)
        self.local_host_dock.setObjectName("localHostDock")
        local_host_widget = QWidget()
        local_host_layout = QVBoxLayout(local_host_widget)
        local_host_layout.setContentsMargins(2, 4, 2, 4)
        self.local_host_config_container = QWidget()
        QVBoxLayout(self.local_host_config_container)
        local_host_layout.addWidget(self.local_host_config_container, stretch=1)
        self.local_host_dock.setWidget(local_host_widget)

        # ── Scope Configuration (right) ──
        # QSplitter: tree (75%) + ContainerRootPanel with header + JSON viewer (25%)
        self.scope_dock = QDockWidget("Scope Configuration", self)
        self.scope_dock.setObjectName("scopeDock")
        scope_widget = QWidget()
        scope_layout = QVBoxLayout(scope_widget)
        scope_layout.setContentsMargins(2, 4, 2, 4)
        self.scope_config_container = QWidget()
        QVBoxLayout(self.scope_config_container)
        self.container_root_panel = ContainerRootPanel()
        scope_splitter = QSplitter(Qt.Orientation.Vertical)
        scope_splitter.addWidget(self.scope_config_container)
        scope_splitter.addWidget(self.container_root_panel)
        scope_splitter.setStretchFactor(0, 3)  # tree: 75%
        scope_splitter.setStretchFactor(1, 1)  # panel: 25%
        scope_layout.addWidget(scope_splitter)
        self.scope_dock.setWidget(scope_widget)

    # ── Default Layout Sizes (pixels) ────────────────────────
    # Columns: left (Local Host), right (Scope + JSON viewer)
    _DEFAULT_COL_LEFT = 500
    _DEFAULT_COL_RIGHT = 500

    def _arrange_default_layout(self):
        """Place docks in the default 2-column arrangement.

        Must be called after dock content widgets are populated (view
        injection) so that Qt computes area proportions from correct
        sizeHints. resizeDocks() provides explicit proportional control.
        """
        # Left: Local Host Configuration
        self.addDockWidget(
            Qt.DockWidgetArea.LeftDockWidgetArea, self.local_host_dock)

        # Right: Scope Configuration (includes JSON viewer)
        self.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea, self.scope_dock)

        # Apply default proportions
        self.resizeDocks(
            [self.local_host_dock, self.scope_dock],
            [self._DEFAULT_COL_LEFT, self._DEFAULT_COL_RIGHT],
            Qt.Orientation.Horizontal,
        )

    def _setup_menus(self):
        """Instantiate MenuManager, pass dock dict, connect Reset Layout."""
        dock_widgets = {
            'local_host': self.local_host_dock,
            'scope': self.scope_dock,
        }
        self.menu_manager = MenuManager(self)
        self.menu_manager.setup_menus(dock_widgets)
        self.menu_manager.reset_layout_action.triggered.connect(self.reset_layout)

    # ── Signal Wiring ────────────────────────────────────────

    def _connect_signals(self) -> None:
        """Wire Logic Phase signal connections."""
        mm = self.menu_manager
        cm = self.config_manager
        fo = self.file_ops_handler
        co = self.container_ops

        # File menu
        mm.open_project_action.triggered.connect(cm.open_project_dialog)
        mm.save_config_action.triggered.connect(cm.save_config)

        # Edit menu — Undo/Redo deferred (actions stay disabled)
        # Click-to-Toggle: single action controls both tree delegates
        mm.click_toggle_action.triggered.connect(
            lambda checked: (
                setattr(self._local_host._delegate, 'click_toggle_enabled', checked),
                setattr(self._scope_view._delegate, 'click_toggle_enabled', checked),
            ),
        )

        # Scopes menu
        mm.scope_direct_action.triggered.connect(cm.new_scope)
        mm.new_scope_action.triggered.connect(cm.new_scope)
        mm.duplicate_scope_action.triggered.connect(cm.duplicate_scope)
        mm.remove_scope_config_action.triggered.connect(co.remove_scope_config)

        # Docker menu
        mm.create_container_action.triggered.connect(co.create_container)
        mm.update_container_action.triggered.connect(co.update_container)
        mm.recreate_container_action.triggered.connect(co.recreate_container)
        mm.remove_container_action.triggered.connect(co.remove_container)
        mm.deploy_llm_action.triggered.connect(co.deploy_llm_to_container)

        # Tools menu
        mm.add_sibling_action.triggered.connect(cm.add_sibling_dialog)
        mm.launch_terminal_action.triggered.connect(co.launch_container_terminal)
        mm.launch_llm_action.triggered.connect(co.launch_llm_in_container)
        mm.open_config_location_action.triggered.connect(co.open_config_location)
        mm.rename_container_root_action.triggered.connect(co.rename_container_root)
        mm.export_structure_action.triggered.connect(cm.export_structure)

        # Sibling removal from LocalHostView context menu
        self._local_host.removeSiblingRequested.connect(cm.remove_sibling)

        # ScopeView file operation signals (RMB context menu)
        self._scope_view.pushRequested.connect(fo.on_push)
        self._scope_view.updateRequested.connect(fo.on_update)
        self._scope_view.pullRequested.connect(fo.on_pull)
        self._scope_view.removeRequested.connect(fo.on_remove)

        # ScopeView header container controls
        self._scope_view.startContainerRequested.connect(co.start_container)
        self._scope_view.stopContainerRequested.connect(co.stop_container)

        # Push checkbox toggle (check→push, uncheck→remove) — both panels
        self._scope_view._model.pushToggleRequested.connect(
            self._on_push_checkbox_toggle
        )
        self._local_host._model.pushToggleRequested.connect(
            self._on_push_checkbox_toggle
        )

        # Selection sync: left panel node → right panel expand
        self._local_host.nodeSelected.connect(self._scope_view.expand_to_path)

        # Sync (force re-push) from LocalHostView context menu
        self._local_host.syncRequested.connect(fo.on_update)

        # Tree state -> config viewer + auto-save to disk
        self._mount_data_tree.stateChanged.connect(self._update_config_viewer)
        self._mount_data_tree.stateChanged.connect(self._auto_save_config)

        # Container root panel — RMB context menu
        self.container_root_panel.openConfigLocationRequested.connect(
            co.open_config_location,
        )

    # ── Public API ───────────────────────────────────────────

    def reset_layout(self):
        """Remove all docks and re-add in default arrangement."""
        for dock in (self.local_host_dock, self.scope_dock):
            self.removeDockWidget(dock)
            dock.setVisible(True)
        self._arrange_default_layout()

    # ── Push Checkbox Handler ────────────────────────────────

    def _on_push_checkbox_toggle(self, path: Path, checked: bool) -> None:
        """Route Push checkbox: check→push, uncheck→remove."""
        if checked:
            self.file_ops_handler.on_push(path)
        else:
            self.file_ops_handler.on_remove(path)

    # ── Helper Methods ───────────────────────────────────────

    def _update_status(self) -> None:
        """Update status bar text from current state."""
        if not self.host_project_root:
            self.status_label.setText("No project loaded")
        else:
            self.status_label.setText(
                f"Project: {self.host_project_root.name}  |  Scope: {self._current_scope}"
            )

    def _update_config_viewer(self) -> None:
        """Refresh JSON preview from current config state."""
        if self._loading:
            return
        if hasattr(self, 'config_manager'):
            self.container_root_panel.config_text = self.config_manager.get_config_text()

    def _auto_save_config(self) -> None:
        """Auto-save config to disk after user mutations.

        Keeps scope_docker_desktop.json in sync with in-memory state.
        Gated by _loading to prevent re-saving during project/scope load.
        """
        if self._loading:
            return
        if hasattr(self, 'config_manager') and self.host_project_root:
            self.config_manager.auto_save()

    def _show_busy_dialog(self, message: str) -> 'QProgressDialog':
        """Show indeterminate progress dialog. Caller must .close()."""
        from PyQt6.QtWidgets import QProgressDialog, QApplication

        dlg = QProgressDialog(message, None, 0, 0, self)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.show()
        QApplication.processEvents()
        return dlg

    # ── Layout Persistence ───────────────────────────────────

    # Bump when dock count or arrangement changes to invalidate stale state
    _LAYOUT_VERSION = 11

    def _save_layout(self):
        """Save window geometry and dock state to QSettings."""
        self._settings.setValue("layoutVersion", self._LAYOUT_VERSION)
        self._settings.setValue("windowGeometry", self.saveGeometry())
        self._settings.setValue("windowState", self.saveState())

    def _restore_layout(self):
        """Restore window geometry and dock state from QSettings.

        Discards saved state when layout version changes (e.g. dock
        count changed from 3 to 4) to avoid stale restoration.
        """
        saved_version = self._settings.value("layoutVersion", 0, type=int)
        if saved_version != self._LAYOUT_VERSION:
            self._settings.remove("windowGeometry")
            self._settings.remove("windowState")
            self._settings.remove("layoutVersion")
            return

        try:
            geometry = self._settings.value("windowGeometry")
            if geometry is not None:
                self.restoreGeometry(geometry)
            state = self._settings.value("windowState")
            if state is not None:
                self.restoreState(state)
        except (TypeError, Exception):
            # Stale or incompatible saved state — use defaults
            self._settings.remove("windowGeometry")
            self._settings.remove("windowState")
            self._settings.remove("layoutVersion")

    # ── System Tray ────────────────────────────────────────────

    def _setup_tray(self):
        """Create system tray icon with context menu."""
        from PyQt6.QtWidgets import QApplication

        self._tray_icon = QSystemTrayIcon(
            QApplication.instance().windowIcon(), self
        )

        tray_menu = QMenu(self)
        self._tray_toggle_action = QAction("Hide", self)
        self._tray_toggle_action.triggered.connect(self._toggle_visibility)
        tray_menu.addAction(self._tray_toggle_action)
        tray_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self._quit_app)
        tray_menu.addAction(exit_action)

        # Update toggle text when menu is about to show
        tray_menu.aboutToShow.connect(self._update_tray_toggle_text)

        self._tray_icon.setContextMenu(tray_menu)
        self._tray_icon.activated.connect(self._on_tray_activated)
        self._tray_icon.show()

    def _update_tray_toggle_text(self):
        """Set Show/Hide text based on current window visibility."""
        self._tray_toggle_action.setText(
            "Hide" if self.isVisible() else "Show"
        )

    def _toggle_visibility(self):
        """Toggle window visibility from tray."""
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def _on_tray_activated(self, reason):
        """Handle tray icon double-click to toggle visibility."""
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def _quit_app(self):
        """Full exit: cleanup, save, quit."""
        self._save_layout()
        if self.host_project_root:
            self.config_manager._cleanup_placeholder()
        self._tray_icon.hide()
        from PyQt6.QtWidgets import QApplication
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent):
        """Minimize to tray on close; fall back to full exit if no tray."""
        self._save_layout()
        if self._tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            if self.host_project_root:
                self.config_manager._cleanup_placeholder()
            event.accept()
