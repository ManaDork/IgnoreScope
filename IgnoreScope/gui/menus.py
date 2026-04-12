"""MenuBar Structure.

Builds the QMenuBar with File, Edit, Scopes, Container, Launch, and View
menus. Creates QActions with keyboard shortcuts and the View menu's dock
toggleViewActions. Provides dynamic state methods for scope list, container
menu states, and recent projects.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QAction, QActionGroup
from PyQt6.QtWidgets import QMainWindow, QMenu


class MenuManager:
    """Manages menu creation and dynamic state for IgnoreScopeApp.

    All QActions are stored as named attributes for IDE autocomplete.

    Dynamic methods:
        update_scope_list() — rebuild Scopes menu from disk
        update_scope_checkmarks(name) — set checkmark on active scope
        update_docker_menu_states() — enable/disable container items
        add_to_recent(path) — add path to Open Recent submenu
    """

    def __init__(self, app: QMainWindow):
        self._app = app
        self._scope_actions: list[QAction] = []
        self._scope_separator: Optional[QAction] = None
        self._settings = QSettings("IgnoreScope", "IgnoreScope")

    @property
    def scope_actions(self) -> list[QAction]:
        """Public read access to dynamic scope QActions."""
        return self._scope_actions

    def setup_menus(self, dock_widgets: dict) -> None:
        """Build the full menu bar.

        Args:
            dock_widgets: Dict mapping dock names to QDockWidget instances.
                Keys: 'local_host', 'scope'
        """
        menu_bar = self._app.menuBar()

        # ── File ──────────────────────────────────────────────

        file_menu = menu_bar.addMenu("File")
        file_menu.setToolTipsVisible(True)

        self.open_project_action = QAction("Open Location of Project", self._app)  #"Open Project..."
        self.open_project_action.setShortcut("Ctrl+O")
        file_menu.addAction(self.open_project_action)

        self.recent_menu = file_menu.addMenu("Open Recent")

        file_menu.addSeparator()

        self.save_config_action = QAction("Save Configuration", self._app)
        self.save_config_action.setShortcut("Ctrl+S")
        self.save_config_action.setEnabled(False)
        self.save_config_action.setToolTip("No project loaded")
        file_menu.addAction(self.save_config_action)

        file_menu.addSeparator()

        self.open_config_location_action = QAction("Open Config Location", self._app)
        self.open_config_location_action.setEnabled(False)
        self.open_config_location_action.setToolTip("No project loaded")
        file_menu.addAction(self.open_config_location_action)

        self.export_structure_action = QAction("Export Container Structure...", self._app)
        self.export_structure_action.setEnabled(False)
        self.export_structure_action.setToolTip("No project loaded")
        file_menu.addAction(self.export_structure_action)

        file_menu.addSeparator()

        self.shut_down_action = QAction("Shut Down", self._app)
        self.shut_down_action.setShortcut("Ctrl+Q")
        file_menu.addAction(self.shut_down_action)

        # ── Edit ──────────────────────────────────────────────

        edit_menu = menu_bar.addMenu("Edit")
        edit_menu.setToolTipsVisible(True)

        self.undo_action = QAction("Undo", self._app)
        self.undo_action.setShortcut("Ctrl+Z")
        edit_menu.addAction(self.undo_action)

        self.redo_action = QAction("Redo", self._app)
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        edit_menu.addAction(self.redo_action)

        edit_menu.addSeparator()

        self.show_hidden_action = QAction("Display Hidden Items", self._app)
        self.show_hidden_action.setCheckable(True)
        self.show_hidden_action.setChecked(False)
        edit_menu.addAction(self.show_hidden_action)

        edit_menu.addSeparator()

        self.add_sibling_action = QAction("Add Sibling...", self._app)
        self.add_sibling_action.setEnabled(False)
        self.add_sibling_action.setToolTip("No project loaded")
        edit_menu.addAction(self.add_sibling_action)

        self.rename_container_root_action = QAction("Container Root Name...", self._app)
        self.rename_container_root_action.setEnabled(False)
        self.rename_container_root_action.setToolTip("No project loaded")
        edit_menu.addAction(self.rename_container_root_action)

        # ── Scopes ────────────────────────────────────────────

        self.scopes_menu = menu_bar.addMenu("+ New Scope")
        self.scopes_menu.setToolTipsVisible(True)
        self.scopes_menu.menuAction().setVisible(False)

        # Direct-action button for when no scopes exist.
        # Sits in the same menubar position; toggled opposite the dropdown.
        self.scope_direct_action = QAction("+ New Scope", self._app)
        menu_bar.insertAction(self.scopes_menu.menuAction(), self.scope_direct_action)
        self.scope_direct_action.setVisible(False)

        # Separator between dynamic scope entries and static actions
        self._scope_separator = self.scopes_menu.addSeparator()

        self.new_scope_action = QAction("+ New Scope", self._app)
        self.scopes_menu.addAction(self.new_scope_action)

        self.duplicate_scope_action = QAction("+ Duplicate Scope", self._app)
        self.scopes_menu.addAction(self.duplicate_scope_action)

        self.remove_scope_config_action = QAction("Remove Scope Config", self._app)
        self.remove_scope_config_action.setEnabled(False)
        self.scopes_menu.addAction(self.remove_scope_config_action)

        # ── Container ─────────────────────────────────────────

        docker_menu = menu_bar.addMenu("Container")
        docker_menu.setToolTipsVisible(True)

        self.create_container_action = QAction("Create Container", self._app)
        self.create_container_action.setEnabled(False)
        self.create_container_action.setToolTip("No project loaded")
        docker_menu.addAction(self.create_container_action)

        self.update_container_action = QAction("Update Container", self._app)
        self.update_container_action.setEnabled(False)
        self.update_container_action.setToolTip("No running container")
        docker_menu.addAction(self.update_container_action)

        self.recreate_container_action = QAction("Recreate Container", self._app)
        self.recreate_container_action.setEnabled(False)
        self.recreate_container_action.setToolTip("No running container")
        docker_menu.addAction(self.recreate_container_action)

        docker_menu.addSeparator()

        self.remove_container_action = QAction("Remove Container", self._app)
        self.remove_container_action.setEnabled(False)
        self.remove_container_action.setToolTip("No running container")
        docker_menu.addAction(self.remove_container_action)

        docker_menu.addSeparator()

        self.deploy_llm_action = QAction("Install Claude CLI", self._app)
        self.deploy_llm_action.setEnabled(False)
        self.deploy_llm_action.setToolTip("No running container")
        docker_menu.addAction(self.deploy_llm_action)

        self.deploy_git_action = QAction("Install Git", self._app)
        self.deploy_git_action.setEnabled(False)
        self.deploy_git_action.setToolTip("No running container")
        docker_menu.addAction(self.deploy_git_action)

        # ── Launch ────────────────────────────────────────────

        launch_menu = menu_bar.addMenu("Launch")
        launch_menu.setToolTipsVisible(True)

        self.launch_terminal_action = QAction("Launch Container in Terminal", self._app)
        self.launch_terminal_action.setEnabled(False)
        self.launch_terminal_action.setToolTip("No running container")
        launch_menu.addAction(self.launch_terminal_action)

        self.launch_llm_action = QAction("Launch Claude CLI", self._app)
        self.launch_llm_action.setEnabled(False)
        self.launch_llm_action.setToolTip("No running container")
        launch_menu.addAction(self.launch_llm_action)

        self.copy_llm_command_action = QAction("Clipboard: Launch Claude CLI", self._app)
        self.copy_llm_command_action.setEnabled(False)
        self.copy_llm_command_action.setToolTip("No running container")
        launch_menu.addAction(self.copy_llm_command_action)

        # ── Terminal Preference Submenu ───────────────────────
        TERMINALS = [
            ("cmd",        "CMD",                "cmd.exe"),
            ("powershell", "PowerShell",         "powershell.exe"),
            ("pwsh",       "pwsh (PowerShell 7)", "pwsh.exe"),
        ]

        saved_pref = self._settings.value("terminal_preference", "cmd")
        # Detect available terminals
        available = []
        for key, label, exe in TERMINALS:
            # cmd and powershell are always present on Windows
            if key in ("cmd", "powershell") or shutil.which(exe):
                available.append((key, label))

        # Validate saved preference against available terminals
        available_keys = [k for k, _ in available]
        if saved_pref not in available_keys:
            saved_pref = "cmd"
            self._settings.setValue("terminal_preference", saved_pref)

        saved_label = next(l for k, l in available if k == saved_pref)
        self.terminal_menu = QMenu(f"Terminal: {saved_label}", self._app)
        launch_menu.addMenu(self.terminal_menu)

        self._terminal_action_group = QActionGroup(self._app)
        self._terminal_action_group.setExclusive(True)

        for key, label in available:
            action = QAction(label, self._app)
            action.setCheckable(True)
            action.setData(key)
            if key == saved_pref:
                action.setChecked(True)
            self._terminal_action_group.addAction(action)
            self.terminal_menu.addAction(action)

        self._terminal_action_group.triggered.connect(self._on_terminal_changed)

        # ── View ──────────────────────────────────────────────

        view_menu = menu_bar.addMenu("View")
        view_menu.setToolTipsVisible(True)

        for key in ('local_host', 'scope'):
            dock = dock_widgets[key]
            view_menu.addAction(dock.toggleViewAction())

        view_menu.addSeparator()

        self.reset_layout_action = QAction("Reset Layout", self._app)
        view_menu.addAction(self.reset_layout_action)

        # Load recent projects
        self._load_recent_menu()

    # ── Dynamic State Methods ─────────────────────────────────

    def update_scope_list(self) -> None:
        """Populate Scopes menu from disk.

        Three states:
          No project  — both hidden
          Project, no scopes — direct action visible ("+ New Scope" button)
          Project, scopes — dropdown menu visible (title = active scope)
        """
        from ..core.config import list_containers

        # Clear dynamic scope entries (keep static actions)
        for action in self._scope_actions:
            self.scopes_menu.removeAction(action)
        self._scope_actions.clear()

        host_project_root = self._app.host_project_root
        if not host_project_root:
            self.scopes_menu.menuAction().setVisible(False)
            self.scope_direct_action.setVisible(False)
            return

        from .app import PLACEHOLDER_SCOPE
        containers = list_containers(host_project_root)
        containers = [c for c in containers if c != PLACEHOLDER_SCOPE]

        if containers:
            # Dropdown mode — title set by update_scope_checkmarks
            self.scope_direct_action.setVisible(False)
            self.scopes_menu.menuAction().setVisible(True)
            self._scope_separator.setVisible(True)

            for name in containers:
                action = QAction(name, self._app)
                action.setCheckable(True)
                action.triggered.connect(
                    lambda checked, n=name: self._on_scope_action_triggered(n)
                )
                self.scopes_menu.insertAction(self._scope_separator, action)
                self._scope_actions.append(action)

            self.remove_scope_config_action.setEnabled(True)
            self.duplicate_scope_action.setEnabled(True)
        else:
            # Direct-action mode — single button in menubar
            self.scopes_menu.menuAction().setVisible(False)
            self.scope_direct_action.setVisible(True)
            self._scope_separator.setVisible(False)
            self.remove_scope_config_action.setEnabled(False)
            self.duplicate_scope_action.setEnabled(False)

    def _on_scope_action_triggered(self, name: str) -> None:
        """Handle scope menu action click — switch scope."""
        if hasattr(self._app, 'config_manager'):
            self._app.config_manager.switch_scope(name)

    def _on_terminal_changed(self, action: QAction) -> None:
        """Handle terminal preference change — save to QSettings, update title."""
        key = action.data()
        label = action.text()
        self._settings.setValue("terminal_preference", key)
        self.terminal_menu.setTitle(f"Terminal: {label}")

    def update_scope_checkmarks(self, active_scope: str) -> None:
        """Set checkmark on the active scope QAction. Update menu title."""
        for action in self._scope_actions:
            action.setChecked(action.text() == active_scope)
        self.scopes_menu.setTitle(active_scope)

    def update_docker_menu_states(self) -> None:
        """Enable/disable container and launch menu items based on current state.

        Two-signal detection:
          has_config = config dir exists on disk (fast filesystem check)
          has_docker_container = docker inspect finds container (only when has_config)

        Truth table:
          No project                        → all OFF
          Project, no config                → Create ON, rest OFF
          Config exists, no Docker container → Create ON, rest OFF
          Config + Docker container exists   → Create OFF, Update/Recreate/Remove ON
        """
        from ..core.config import get_container_dir
        from ..docker.container_ops import container_exists
        from ..docker.names import build_docker_name
        from .app import PLACEHOLDER_SCOPE

        has_project = self._app.host_project_root is not None
        is_placeholder = self._app._current_scope == PLACEHOLDER_SCOPE

        # Project-dependent actions (always need a project)
        save_config_tip = "Save the current scope configuration to disk" if has_project else "No project loaded"
        self.save_config_action.setEnabled(has_project)
        self.save_config_action.setToolTip(save_config_tip)

        open_config_tip = "Open the folder containing this scope's config" if has_project else "No project loaded"
        self.open_config_location_action.setEnabled(has_project)
        self.open_config_location_action.setToolTip(open_config_tip)

        export_tip = "Export the container folder structure to a file" if has_project else "No project loaded"
        self.export_structure_action.setEnabled(has_project)
        self.export_structure_action.setToolTip(export_tip)

        add_sibling_enabled = has_project and not is_placeholder
        add_sibling_tip = "Add a sibling node at the same level in the tree" if add_sibling_enabled \
                         else ("No project loaded" if not has_project else "Select a scope first")
        self.add_sibling_action.setEnabled(add_sibling_enabled)
        self.add_sibling_action.setToolTip(add_sibling_tip)

        rename_root_enabled = has_project and not is_placeholder
        rename_root_tip = "Rename the container root node" if rename_root_enabled \
                         else ("No project loaded" if not has_project else "Select a scope first")
        self.rename_container_root_action.setEnabled(rename_root_enabled)
        self.rename_container_root_action.setToolTip(rename_root_tip)

        # Two-signal detection
        has_config = False
        has_docker_container = False
        if has_project and not is_placeholder:
            config_dir = get_container_dir(
                self._app.host_project_root, self._app._current_scope
            )
            has_config = config_dir.exists()

            if has_config:
                docker_name = build_docker_name(
                    self._app.host_project_root, self._app._current_scope
                )
                has_docker_container = container_exists(docker_name)

        # Create: enabled when project exists, not placeholder, no Docker container
        create_enabled = has_project and not is_placeholder and not has_docker_container
        if create_enabled:
            create_tip = "Create a new Docker container for this scope"
        elif not has_project:
            create_tip = "No project loaded"
        elif is_placeholder:
            create_tip = "Select a scope first"
        else:
            create_tip = "Container already exists — use Update or Recreate"
        self.create_container_action.setEnabled(create_enabled)
        self.create_container_action.setToolTip(create_tip)

        # Update/Recreate/Remove: enabled only when Docker container exists
        update_tip = "Rebuild the container image without removing it" if has_docker_container else "No running container"
        self.update_container_action.setEnabled(has_docker_container)
        self.update_container_action.setToolTip(update_tip)

        recreate_tip = "Remove and recreate the container from scratch" if has_docker_container else "No running container"
        self.recreate_container_action.setEnabled(has_docker_container)
        self.recreate_container_action.setToolTip(recreate_tip)

        remove_tip = "Permanently remove the Docker container" if has_docker_container else "No running container"
        self.remove_container_action.setEnabled(has_docker_container)
        self.remove_container_action.setToolTip(remove_tip)

        # Deploy/Terminal/LLM: need a Docker container
        deploy_llm_tip = "Install Claude CLI into the running container" if has_docker_container else "No running container"
        self.deploy_llm_action.setEnabled(has_docker_container)
        self.deploy_llm_action.setToolTip(deploy_llm_tip)

        deploy_git_tip = "Install Git into the running container" if has_docker_container else "No running container"
        self.deploy_git_action.setEnabled(has_docker_container)
        self.deploy_git_action.setToolTip(deploy_git_tip)

        launch_terminal_tip = "Open a terminal session inside the container" if has_docker_container else "No running container"
        self.launch_terminal_action.setEnabled(has_docker_container)
        self.launch_terminal_action.setToolTip(launch_terminal_tip)

        launch_llm_tip = "Launch Claude CLI inside the container" if has_docker_container else "No running container"
        self.launch_llm_action.setEnabled(has_docker_container)
        self.launch_llm_action.setToolTip(launch_llm_tip)

        copy_llm_tip = "Copy the Claude CLI launch command to clipboard" if has_docker_container else "No running container"
        self.copy_llm_command_action.setEnabled(has_docker_container)
        self.copy_llm_command_action.setToolTip(copy_llm_tip)

    def update_project_loaded_states(self, loaded: bool) -> None:
        """Enable/disable items that require a loaded project."""
        self.save_config_action.setEnabled(loaded)
        self.create_container_action.setEnabled(loaded)
        self.export_structure_action.setEnabled(loaded)
        self.open_config_location_action.setEnabled(loaded)

    # ── Recent Projects ───────────────────────────────────────

    _MAX_RECENT = 10

    def add_to_recent(self, path: Path) -> None:
        """Add path to Open Recent submenu (persist via QSettings)."""
        path_str = str(path)
        recent = self._settings.value("recentProjects", [], type=list)

        # Remove if already present, then prepend
        if path_str in recent:
            recent.remove(path_str)
        recent.insert(0, path_str)
        recent = recent[:self._MAX_RECENT]

        self._settings.setValue("recentProjects", recent)
        self._load_recent_menu()

    def _load_recent_menu(self) -> None:
        """Populate Open Recent submenu from QSettings."""
        self.recent_menu.clear()
        recent = self._settings.value("recentProjects", [], type=list)

        if not recent:
            empty_action = QAction("(No recent projects)", self._app)
            empty_action.setEnabled(False)
            self.recent_menu.addAction(empty_action)
            return

        for path_str in recent:
            action = QAction(path_str, self._app)
            action.triggered.connect(
                lambda checked, p=path_str: self._open_recent_project(p)
            )
            self.recent_menu.addAction(action)

        self.recent_menu.addSeparator()
        clear_action = QAction("Clear Recent", self._app)
        clear_action.triggered.connect(self._clear_recent)
        self.recent_menu.addAction(clear_action)

    def _open_recent_project(self, path_str: str) -> None:
        """Open a project from the recent list."""
        if hasattr(self._app, 'config_manager'):
            self._app.config_manager.open_project(Path(path_str))

    def _clear_recent(self) -> None:
        """Clear the recent projects list."""
        self._settings.setValue("recentProjects", [])
        self._load_recent_menu()
