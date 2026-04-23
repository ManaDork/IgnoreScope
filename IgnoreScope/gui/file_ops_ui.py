"""File operations UI handler for IgnoreScopeApp.

FileOperationsHandler manages instant push/pull/remove file operations.
No staging, no review dialog — operations execute immediately on RMB action.

GUI is a thin layer: resolve UI context, call CORE preflight/execute,
show dialogs for warnings/errors, update tree state + save config.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from ..core.config import load_config
from ..core.op_result import OpError, OpWarning, OpResult
from ..docker import (
    preflight_push,
    execute_push,
    preflight_pull,
    execute_pull,
    preflight_remove,
    execute_remove,
)

if TYPE_CHECKING:
    from .app import IgnoreScopeApp


# Dialog text for confirmable warnings
WARNING_DIALOGS: dict[OpWarning, tuple[str, str]] = {
    OpWarning.FILE_ALREADY_TRACKED: (
        "Overwrite?",
        "Overwrite {name} in container?",
    ),
    OpWarning.FILE_IN_CONTAINER_UNTRACKED: (
        "Overwrite?",
        "{name} exists in container (not pushed from host). Overwrite?",
    ),
    OpWarning.NOT_IN_MASKED_AREA: (
        "Outside Mask",
        "{name} is not in a masked area — push may have no visible effect. Continue?",
    ),
    OpWarning.LOCAL_FILE_EXISTS: (
        "Overwrite?",
        "Overwrite local {name}?",
    ),
    OpWarning.DESTRUCTIVE_REMOVE: (
        "Remove?",
        "Remove {name} from container? This cannot be undone.",
    ),
    OpWarning.CONTAINER_DATA_LOSS: (
        "Data Loss",
        "All data in the container will be lost. Continue?",
    ),
}

# Dialog titles for blocking errors
ERROR_TITLES: dict[OpError, str] = {
    OpError.NO_PROJECT: "No Project",
    OpError.CONFIG_LOAD_FAILED: "Config Error",
    OpError.CONTAINER_NOT_RUNNING: "Container Not Running",
    OpError.CONTAINER_NOT_FOUND: "Container Not Found",
    OpError.DOCKER_NOT_RUNNING: "Docker Not Available",
    OpError.HOST_FILE_NOT_FOUND: "File Not Found",
    OpError.PARENT_NOT_MOUNTED: "No Parent Mount",
    OpError.INVALID_LOCATION: "Invalid Path",
    OpError.FILE_NOT_IN_CONTAINER: "File Not Found",
    OpError.VALIDATION_FAILED: "Validation Error",
    OpError.PROJECT_IN_INSTALL_DIR: "Invalid Project",
    OpError.NO_PUSHED_FILES: "No Files",
    OpError.NO_MATCHING_FILES: "No Matching Files",
}


class FileOperationsHandler:
    """Manages instant file operations for IgnoreScopeApp.

    Handles:
    - Push file to container (docker cp host->container)
    - Update file in container (overwrite push)
    - Pull file from container (docker cp container->host)
    - Remove file from container (docker exec rm)

    Uses CORE preflight/execute pattern from docker/file_ops.py.
    GUI responsibility: UI context, dialogs, tree state refresh, config save.
    """

    def __init__(self, app: 'IgnoreScopeApp'):
        self._app = app

    def _get_container_context(self):
        """Get container name, root, and host_container_root, or show error and return None."""
        if not self._app.host_project_root:
            return None

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )

        try:
            config = load_config(self._app.host_project_root, self._app._current_scope)
        except Exception as e:
            QMessageBox.warning(
                self._app, "Config Error", f"Could not load config: {e}"
            )
            return None

        container_root = self._app._mount_data_tree.container_root
        host_container_root = config.host_container_root or self._app.host_project_root.parent
        return container_name, container_root, host_container_root

    def _show_error(self, result: OpResult) -> None:
        """Show blocking error dialog from OpResult."""
        title = ERROR_TITLES.get(result.error, "Error") if result.error else "Error"
        QMessageBox.warning(self._app, title, result.message)

    def _confirm_warnings(self, result: OpResult, path: Path) -> bool:
        """Show confirm dialogs for each warning. Returns True if all confirmed."""
        for warning in result.warnings:
            title, text = WARNING_DIALOGS.get(
                warning, ("Confirm?", "Continue with {name}?")
            )
            reply = QMessageBox.question(
                self._app,
                title,
                text.format(name=path.name),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        return True

    def on_push(self, path: Path) -> None:
        """Push a file to the container."""
        ctx = self._get_container_context()
        if not ctx:
            return
        container_name, container_root, host_container_root = ctx
        pushed_files = set(self._app._mount_data_tree.pushed_files)

        # Preflight
        result = preflight_push(
            path, container_name, container_root, host_container_root, pushed_files,
        )
        if result.error:
            self._show_error(result)
            return
        if result.warnings and not self._confirm_warnings(result, path):
            return

        # Execute
        result = execute_push(
            path, container_name, container_root, host_container_root,
        )
        if result.success:
            # add_pushed emits stateChanged → auto_save persists (app.py:400).
            self._app._mount_data_tree.add_pushed(path)
            self._app.statusBar().showMessage(f"Pushed {path.name}", 5000)
        else:
            QMessageBox.warning(self._app, "Push Failed", result.message)

    def on_update(self, path: Path) -> None:
        """Update (overwrite) a file in the container."""
        ctx = self._get_container_context()
        if not ctx:
            return
        container_name, container_root, host_container_root = ctx

        reply = QMessageBox.question(
            self._app, "Overwrite?",
            f"Overwrite {path.name} in container?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Execute directly (update is always a forced push on a tracked file)
        result = execute_push(
            path, container_name, container_root, host_container_root,
        )
        if result.success:
            self._app.statusBar().showMessage(f"Updated {path.name}", 5000)
        else:
            QMessageBox.warning(self._app, "Update Failed", result.message)

    def on_pull(self, path: Path) -> None:
        """Pull a file from the container."""
        ctx = self._get_container_context()
        if not ctx:
            return
        container_name, container_root, host_container_root = ctx

        # Preflight
        result = preflight_pull(
            path, container_name, container_root, host_container_root,
            self._app.host_project_root, self._app.dev_mode,
        )
        if result.error:
            self._show_error(result)
            return
        if result.warnings and not self._confirm_warnings(result, path):
            return

        # Execute
        result = execute_pull(
            path, container_name, container_root, host_container_root,
            self._app.host_project_root, self._app.dev_mode,
        )
        if result.success:
            self._app.statusBar().showMessage(f"Pulled {path.name}", 5000)
        else:
            QMessageBox.warning(self._app, "Pull Failed", result.message)

    def on_remove(self, path: Path) -> None:
        """Remove a file from the container."""
        ctx = self._get_container_context()
        if not ctx:
            return
        container_name, container_root, host_container_root = ctx

        # Preflight
        result = preflight_remove(
            path, container_name, container_root, host_container_root,
        )
        if result.error:
            self._show_error(result)
            return
        if result.warnings and not self._confirm_warnings(result, path):
            return

        # Execute
        result = execute_remove(
            path, container_name, container_root, host_container_root,
        )
        if result.success:
            # remove_pushed emits stateChanged → auto_save persists (app.py:400).
            self._app._mount_data_tree.remove_pushed(path)
            self._app.statusBar().showMessage(f"Removed {path.name} from container", 5000)
        else:
            QMessageBox.warning(self._app, "Remove Failed", result.message)
