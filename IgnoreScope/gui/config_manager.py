"""Configuration manager for IgnoreScopeApp.

IS:  Project open/close, scope switching, config read/write via CORE,
     build_config() assembly from GUI widget state, new/duplicate scope dialogs.

IS NOT: Docker container operations (→ container_ops_ui.py)
        File push/pull/remove operations (→ file_ops_ui.py)
        Node state computation (→ core/node_state.py)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox

from ..core.config import (
    ScopeDockerConfig,
    SiblingMount,
    load_config,
    save_config,
    list_containers,
)

if TYPE_CHECKING:
    from .app import IgnoreScopeApp


class ConfigManager:
    """Manages configuration and project loading for IgnoreScopeApp.

    Handles:
    - Open project
    - Switch scope
    - Build/save config
    - New scope creation
    - Export structure
    """

    def __init__(self, app: 'IgnoreScopeApp'):
        self._app = app

    def open_project_dialog(self) -> None:
        """Open file dialog to select a project."""
        start_dir = (
            str(self._app.host_project_root)
            if self._app.host_project_root
            else str(Path.home())
        )
        path = QFileDialog.getExistingDirectory(
            self._app,
            "Select Project Directory",
            start_dir,
        )
        if path:
            self.open_project(Path(path))

    def open_project(self, host_project_root: Path) -> None:
        """Open a project directory."""
        if not host_project_root.exists():
            QMessageBox.warning(
                self._app, "Project Not Found",
                f"Directory not found: {host_project_root}",
            )
            return

        progress = self._app._show_busy_dialog(f"Opening {host_project_root.name}...")

        try:
            # Gate all app-level signal handlers
            self._app._loading = True
            try:
                # Clear state from previous project
                self._app._mount_data_tree.clear()

                self._app.host_project_root = host_project_root.resolve()

                # Default container root to /{parent_folder_name}
                host_container_root = self._app.host_project_root.parent
                self._app.container_root_panel.clear()
                self._app._mount_data_tree.container_root = f"/{host_container_root.name}"

                self._app.setWindowTitle(
                    f"IgnoreScope - {self._app.host_project_root.name}"
                )

                # Set project root on the shared data tree
                self._app._mount_data_tree.set_host_project_root(
                    self._app.host_project_root
                )

                # Reset models to new root — invalidates stale C++ QModelIndex
                # pointers that would crash if accessed before switch_scope().
                self._app._local_host.refresh()
                self._app._scope_view.refresh()
            finally:
                self._app._loading = False

            # Update container list
            self._app.menu_manager.update_scope_list()

            # Load config for default container
            containers = list_containers(self._app.host_project_root)
            if containers:
                # switch_scope handles its own gate + refresh
                self.switch_scope(containers[0], _show_progress=False)
                self._app.menu_manager.add_to_recent(self._app.host_project_root)
            else:
                # No scopes — single refresh pass
                from .app import PLACEHOLDER_SCOPE
                self._app._current_scope = PLACEHOLDER_SCOPE
                self._app._mount_data_tree.current_scope = PLACEHOLDER_SCOPE
                self._app._local_host.refresh()
                self._app._scope_view.refresh()
                self._app._update_status()
                self._app._update_config_viewer()
                self._app.menu_manager.update_docker_menu_states()
        finally:
            progress.close()

    def switch_scope(self, name: str, *, _show_progress: bool = True) -> None:
        """Switch to a different container configuration."""
        progress = None
        if _show_progress:
            progress = self._app._show_busy_dialog(f"Loading {name}...")

        try:
            self._app._current_scope = name
            self._app._mount_data_tree.current_scope = name

            # Gate app-level handlers + batch tree signals
            self._app._loading = True
            self._app._mount_data_tree.begin_batch()

            config = None
            try:
                # Update menu checkmarks
                self._app.menu_manager.update_scope_checkmarks(name)

                # Load config ONCE
                if self._app.host_project_root:
                    try:
                        config = load_config(self._app.host_project_root, name)
                    except Exception as e:
                        QMessageBox.warning(
                            self._app, "Load Error", f"Failed to load config: {e}"
                        )
                        return

                    # Single apply — all data ready, one compute
                    self._app._mount_data_tree.load_config(config)

                    # container_root absorbed by load_config() above

            finally:
                # Reset models (beginResetModel/endResetModel handles full refresh)
                self._app._local_host.refresh()
                self._app._scope_view.refresh()
                # End batch without emitting — refresh already updated everything
                self._app._mount_data_tree.end_batch(emit=False)
                self._app._loading = False

            # Single update pass — all state consistent
            self._app._update_config_viewer()
            self._app._update_status()

            self._app.menu_manager.update_docker_menu_states()
        finally:
            if progress:
                progress.close()

    def build_config(self) -> ScopeDockerConfig:
        """Build a ScopeDockerConfig from current UI state."""
        return self._app._mount_data_tree.build_config(
            scope_name=self._app._current_scope,
            dev_mode=self._app.dev_mode,
        )

    def save_config(self) -> None:
        """Save the current configuration (user-initiated, shows status)."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app,
                "No Project",
                "Please open a project first.",
            )
            return

        from .app import PLACEHOLDER_SCOPE
        if self._app._current_scope == PLACEHOLDER_SCOPE:
            self._app.statusBar().showMessage(
                "Create a named scope before saving", 5000,
            )
            return

        config = self.build_config()

        try:
            save_config(config)
            self._app.statusBar().showMessage(
                f"Configuration saved for {self._app._current_scope}",
                5000,
            )
        except Exception as e:
            QMessageBox.critical(
                self._app,
                "Save Error",
                f"Failed to save configuration: {e}",
            )

    def auto_save(self) -> None:
        """Save config to disk silently after GUI state mutations.

        Called by stateChanged signal on every toggle operation.
        No status bar message, no error dialog — keeps disk in sync
        with in-memory state as the single source of truth.
        """
        if not self._app.host_project_root:
            return
        from .app import PLACEHOLDER_SCOPE
        if self._app._current_scope == PLACEHOLDER_SCOPE:
            return
        try:
            config = self.build_config()
            save_config(config)
        except Exception:
            pass  # Auto-save failures non-critical — user can Ctrl+S

    def get_config_text(self) -> str:
        """Generate JSON text from current UI state."""
        if not self._app.host_project_root:
            return "// No project loaded"

        try:
            config = self.build_config()
            config_dict = config.to_dict(self._app.host_project_root)
            return json.dumps(config_dict, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"// Error generating config:\n// {e}"

    def new_scope(self) -> None:
        """Create a new container configuration with fresh defaults."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from .new_scope_dialog import NewScopeDialog
        from .app import PLACEHOLDER_SCOPE

        dialog = NewScopeDialog(self._app)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.scope_name:
            name = dialog.scope_name

            if name == PLACEHOLDER_SCOPE:
                QMessageBox.warning(
                    self._app,
                    "Reserved Name",
                    f"'{name}' is reserved. Please choose a different name.",
                )
                return

            containers = list_containers(self._app.host_project_root)
            if name in containers:
                QMessageBox.warning(
                    self._app,
                    "Scope Exists",
                    f"Scope '{name}' already exists.",
                )
                return

            if self._app._current_scope == PLACEHOLDER_SCOPE:
                # Migrate: current UI state becomes the new named scope
                config = self.build_config()
                config.scope_name = name
            else:
                # Fresh scope (creating additional scope while on a named one)
                config = ScopeDockerConfig(
                    scope_name=name,
                    host_project_root=self._app.host_project_root,
                    container_root=self._app._mount_data_tree.container_root,
                )

            try:
                save_config(config)
                self._cleanup_placeholder()
                self._app.menu_manager.update_scope_list()
                self.switch_scope(name)
                self._app.menu_manager.add_to_recent(self._app.host_project_root)
            except Exception as e:
                QMessageBox.critical(
                    self._app,
                    "Create Error",
                    f"Failed to create container: {e}",
                )

    def duplicate_scope(self) -> None:
        """Duplicate the current scope into a new container configuration."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from .new_scope_dialog import NewScopeDialog
        from .app import PLACEHOLDER_SCOPE

        dialog = NewScopeDialog(self._app)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.scope_name:
            name = dialog.scope_name

            if name == PLACEHOLDER_SCOPE:
                QMessageBox.warning(
                    self._app,
                    "Reserved Name",
                    f"'{name}' is reserved. Please choose a different name.",
                )
                return

            containers = list_containers(self._app.host_project_root)
            if name in containers:
                QMessageBox.warning(
                    self._app,
                    "Scope Exists",
                    f"Scope '{name}' already exists.",
                )
                return

            config = self.build_config()
            config.scope_name = name

            try:
                save_config(config)
                self._app.menu_manager.update_scope_list()
                self.switch_scope(name)
                self._app.menu_manager.add_to_recent(self._app.host_project_root)
            except Exception as e:
                QMessageBox.critical(
                    self._app,
                    "Duplicate Error",
                    f"Failed to duplicate container: {e}",
                )

    # ── Sibling Management ─────────────────────────────────────

    def add_sibling_dialog(self) -> None:
        """Open folder picker to add a sibling directory."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first.",
            )
            return

        path = QFileDialog.getExistingDirectory(
            self._app,
            "Select Sibling Directory",
            str(self._app.host_project_root.parent),
        )
        if path:
            self.add_sibling(Path(path))

    def add_sibling(self, host_path: Path) -> None:
        """Add sibling folder to current config. Auto-derives container_path."""
        host_path = host_path.resolve()
        container_path = self._derive_container_path(host_path)
        sibling = SiblingMount(
            host_path=host_path,
            container_path=container_path,
        )
        # Rebuild config with new sibling appended
        config = self.build_config()
        config.siblings.append(sibling)
        save_config(config)
        # Reload tree so sibling appears
        self._app._mount_data_tree.load_config(config)
        self._app._local_host.refresh()
        self._app._scope_view.refresh()
        self._app._update_config_viewer()

    def remove_sibling(self, host_path: Path) -> None:
        """Remove sibling by host_path after user confirmation."""
        reply = QMessageBox.question(
            self._app,
            "Remove Sibling",
            f"Remove sibling '{host_path.name}'?\n\n"
            "This removes the sibling from IgnoreScope configuration.\n"
            "The folder and its contents on disk are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        config = self.build_config()
        config.siblings = [
            s for s in config.siblings if s.host_path != host_path
        ]
        save_config(config)
        self._app._mount_data_tree.load_config(config)
        self._app._local_host.refresh()
        self._app._scope_view.refresh()
        self._app._update_config_viewer()

    def _derive_container_path(self, host_path: Path) -> str:
        """Auto-derive container_path under container_root, handle collisions."""
        container_root = self._app._mount_data_tree.container_root
        base = f"{container_root}/{host_path.name}"
        existing = {
            s.container_path
            for s in self._app._mount_data_tree.get_sibling_configs()
        }
        if base not in existing:
            return base
        for i in range(2, 100):
            candidate = f"{container_root}/{host_path.name}_{i}"
            if candidate not in existing:
                return candidate
        raise ValueError(f"Too many siblings with name '{host_path.name}'")

    def _cleanup_placeholder(self) -> None:
        """Remove placeholder scope from disk if it exists."""
        from .app import PLACEHOLDER_SCOPE
        from ..core.config import delete_scope_config
        if self._app.host_project_root:
            delete_scope_config(self._app.host_project_root, PLACEHOLDER_SCOPE)

    def export_structure(self) -> None:
        """Export container structure as text dialog."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from .export_structure import generate_container_structure
        from PyQt6.QtWidgets import QVBoxLayout, QTextEdit

        tree_data = self._app._mount_data_tree.get_config_data()
        text = generate_container_structure(
            host_project_root=self._app.host_project_root,
            container_root=self._app._mount_data_tree.container_root,
            mounts=tree_data['mounts'],
            masked=tree_data['masked'],
            revealed=tree_data['revealed'],
        )

        dialog = QDialog(self._app)
        dialog.setWindowTitle("Container Structure")
        dialog.setMinimumSize(600, 400)
        layout = QVBoxLayout(dialog)
        text_edit = QTextEdit()
        text_edit.setPlainText(text)
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)
        dialog.exec()
