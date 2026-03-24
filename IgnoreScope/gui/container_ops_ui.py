"""Container operations for IgnoreScopeApp.

ContainerOperations handles Docker container lifecycle and terminal launching.
Uses CORE orchestrators from docker/container_lifecycle.py — no CLI imports.
"""

from __future__ import annotations

import platform
import subprocess
from typing import TYPE_CHECKING, Callable, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QMessageBox,
    QProgressDialog,
)

from ..core.config import (
    save_config,
    list_containers,
    delete_scope_config,
)
from ..core.op_result import OpResult
from ..docker import (
    execute_create,
    execute_update,
    execute_remove_container,
    ensure_container_running,
    get_terminal_command,
    get_llm_command,
)

if TYPE_CHECKING:
    from .app import IgnoreScopeApp


class ContainerWorker(QThread):
    """Worker thread for container operations."""

    progress = pyqtSignal(str)  # Emits status text
    finished = pyqtSignal(bool, str)  # Emits (success, message)

    def __init__(self, operation: Callable[[], OpResult], parent=None):
        super().__init__(parent)
        self._operation = operation

    def run(self):
        """Run container operation in background via CORE orchestrator."""
        try:
            result = self._operation()
            self.finished.emit(result.success, result.message)
        except Exception as e:
            self.finished.emit(False, f"Error: {e}")


class DeployWorker(QThread):
    """Worker thread for Claude CLI deployment into a running container."""

    finished = pyqtSignal(bool, str, str)  # success, message, version

    def __init__(self, container_name: str, parent=None):
        super().__init__(parent)
        self._container_name = container_name

    def run(self):
        """Run Claude CLI deployment in background."""
        try:
            from ..container_ext import ClaudeInstaller, DeployMethod

            deployer = ClaudeInstaller(auto_launch=False)
            result = deployer.deploy_runtime(
                self._container_name,
                method=DeployMethod.FULL,
                timeout=300,
            )
            self.finished.emit(result.success, result.message, result.version)
        except Exception as e:
            self.finished.emit(False, f"Installation error: {e}", "")


class GitDeployWorker(QThread):
    """Worker thread for Git deployment into a running container."""

    finished = pyqtSignal(bool, str, str)  # success, message, version

    def __init__(self, container_name: str, parent=None):
        super().__init__(parent)
        self._container_name = container_name

    def run(self):
        """Run Git deployment in background."""
        try:
            from ..container_ext import GitInstaller
            deployer = GitInstaller()
            result = deployer.deploy(self._container_name, distro="auto")
            self.finished.emit(result.success, result.message, result.version)
        except Exception as e:
            self.finished.emit(False, f"Installation error: {e}", "")


class ContainerOperations:
    """Manages Docker container operations for IgnoreScopeApp.

    Handles:
    - Create, update, recreate, remove containers
    - Remove scope config
    - Launch terminal and LLM in container

    Uses CORE orchestrators — GUI responsibility is dialogs + UI refresh.
    """

    def __init__(self, app: 'IgnoreScopeApp'):
        self._app = app
        self._container_worker: Optional[ContainerWorker] = None
        self._deploy_worker: Optional[DeployWorker] = None
        self._git_deploy_worker: Optional[GitDeployWorker] = None

    def _create_progress_dialog(self, title: str, message: str) -> QProgressDialog:
        """Create and show an indeterminate progress dialog.

        Args:
            title: Dialog window title.
            message: Dialog body text.

        Returns:
            Configured QProgressDialog (already shown).
        """
        progress = QProgressDialog(
            message,
            None,  # No cancel button
            0,
            0,  # Indeterminate
            self._app,
        )
        progress.setWindowTitle(title)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setMinimumDuration(0)
        progress.setMinimumSize(350, 120)
        progress.show()
        QApplication.processEvents()
        return progress

    def _run_container_operation(
        self,
        operation: Callable[[], OpResult],
        title: str,
        message: str,
        success_title: str,
    ) -> None:
        """Shared helper: progress dialog + worker thread + completion handler.

        Args:
            operation: Callable returning OpResult (runs on worker thread)
            title: Progress dialog window title
            message: Progress dialog body text
            success_title: Title for success message box
        """
        progress = self._create_progress_dialog(title, message)

        self._container_worker = ContainerWorker(operation, self._app)
        self._container_worker.finished.connect(
            lambda ok, msg: self._on_operation_finished(ok, msg, progress, success_title)
        )
        self._container_worker.start()

    def _on_operation_finished(
        self, success: bool, msg: str, progress: QProgressDialog,
        success_title: str,
    ) -> None:
        """Handle container operation completion."""
        progress.close()

        if success:
            QMessageBox.information(self._app, success_title, msg)
            self._app.menu_manager.update_scope_list()
            self._app.menu_manager.update_docker_menu_states()
            self._app._scope_view.refresh()
            self._app.menu_manager.add_to_recent(self._app.host_project_root)
        else:
            # Split multi-line errors: first line as summary, rest as detail
            lines = msg.split("\n", 1)
            summary = lines[0]
            detail = lines[1] if len(lines) > 1 else ""

            error_box = QMessageBox(self._app)
            error_box.setIcon(QMessageBox.Icon.Critical)
            error_box.setWindowTitle("Operation Failed")
            error_box.setText(summary)
            if detail:
                error_box.setDetailedText(detail)
            error_box.exec()

    def _validate_and_save_config(self):
        """Build config from GUI, validate, save. Returns config or None on error."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return None

        from .app import PLACEHOLDER_SCOPE
        if self._app._current_scope == PLACEHOLDER_SCOPE:
            QMessageBox.warning(
                self._app, "No Scope",
                "Create a named scope before building a container.",
            )
            return None

        config = self._app.config_manager.build_config()

        errors = config.validate()
        if errors:
            QMessageBox.warning(
                self._app,
                "Validation Errors",
                "Configuration has errors:\n" + "\n".join(f"- {e}" for e in errors),
            )
            return None

        try:
            save_config(config)
        except Exception as e:
            QMessageBox.critical(
                self._app, "Save Error", f"Failed to save config: {e}"
            )
            return None

        return config

    def create_container(self) -> None:
        """Create the Docker container from current configuration."""
        config = self._validate_and_save_config()
        if config is None:
            return

        host_project_root = self._app.host_project_root
        self._run_container_operation(
            operation=lambda: execute_create(host_project_root, config),
            title="Creating Container",
            message="Building Docker container...\n\nThis may take a minute on first build.",
            success_title="Container Created",
        )

    def update_container(self) -> None:
        """Update existing container, retaining configured volumes."""
        config = self._validate_and_save_config()
        if config is None:
            return

        host_project_root = self._app.host_project_root
        self._run_container_operation(
            operation=lambda: execute_update(host_project_root, config),
            title="Updating Container",
            message="Updating Docker container...\nRetaining existing volume data.",
            success_title="Container Updated",
        )

    def recreate_container(self) -> None:
        """Remove and recreate the container (destroys all volumes)."""
        if not self._app.host_project_root:
            return

        reply = QMessageBox.question(
            self._app,
            "Recreate Container",
            f"This will remove and recreate container '{self._app._current_scope}'.\n"
            "All data in the container will be lost.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        config = self._validate_and_save_config()
        if config is None:
            return

        host_project_root = self._app.host_project_root
        scope = self._app._current_scope

        def _recreate() -> OpResult:
            remove_result = execute_remove_container(
                host_project_root, scope,
                remove_images=True, remove_volumes=True,
            )
            if not remove_result.success and "not found" not in remove_result.message.lower():
                return remove_result
            return execute_create(host_project_root, config)

        self._run_container_operation(
            operation=_recreate,
            title="Recreating Container",
            message="Removing and rebuilding Docker container...\n\nAll volumes will be destroyed.",
            success_title="Container Recreated",
        )

    def remove_container(self) -> None:
        """Remove the Docker container only. Config files are preserved.

        Removes the Docker container, volumes, and images via docker compose down.
        The scope_docker_desktop.json configuration is intentionally LEFT on disk so the
        user can recreate the container from the same settings. To delete config
        files, use remove_scope_config() instead.
        """
        if not self._app.host_project_root:
            return

        reply = QMessageBox.question(
            self._app,
            "Remove Container",
            f"Remove container '{self._app._current_scope}' and all its volumes?\n\n"
            "Configuration settings will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            result = execute_remove_container(
                self._app.host_project_root,
                self._app._current_scope,
                remove_images=True,
            )

            if result.success:
                QMessageBox.information(self._app, "Container Removed", result.message)
                self._app.menu_manager.update_docker_menu_states()
                self._app._scope_view.refresh()
                # Refresh config viewer to confirm config is preserved
                self._app._update_config_viewer()
                self._app._update_status()
            else:
                QMessageBox.warning(self._app, "Remove Failed", result.message)

    def remove_scope_config(self) -> None:
        """Remove scope config (JSON) without touching Docker container.

        NOTE: This cascade manually resets 8+ GUI panels. If new panels are added,
        this method must be updated. Future candidate for app.reset_to_scope().
        """
        if not self._app.host_project_root:
            return

        scope_name = self._app._current_scope

        # Use CORE function to check existence
        from ..core.config import get_container_dir
        config_dir = get_container_dir(
            self._app.host_project_root, scope_name
        )
        if not config_dir.exists():
            QMessageBox.information(
                self._app,
                "No Scope Config",
                f"No scope config found for '{scope_name}'.",
            )
            return

        # Guard: block removal if Docker container still exists
        from ..docker.container_ops import container_exists
        from ..docker.names import build_docker_name
        docker_name = build_docker_name(self._app.host_project_root, scope_name)
        if container_exists(docker_name):
            QMessageBox.warning(
                self._app,
                "Container Exists",
                f"Cannot remove scope config for '{scope_name}' — "
                "its Docker container still exists.\n\n"
                "Remove the Docker container first (Docker → Remove Container).",
            )
            return

        reply = QMessageBox.question(
            self._app,
            "Remove Scope Config",
            f"Remove scope config for '{scope_name}'?\n\n"
            f"This will delete:\n{config_dir}\n\n"
            "The Docker container itself will NOT be affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            success, msg = delete_scope_config(
                self._app.host_project_root, scope_name,
            )
            if success:
                QMessageBox.information(
                    self._app, "Scope Config Removed",
                    f"Scope config for '{scope_name}' has been removed.",
                )
                # Refresh container list and switch to first available or default
                self._app.menu_manager.update_scope_list()
                containers = list_containers(self._app.host_project_root)
                if containers:
                    self._app.config_manager.switch_scope(containers[0])
                else:
                    from .app import PLACEHOLDER_SCOPE
                    self._app._current_scope = PLACEHOLDER_SCOPE
                    self._app._mount_data_tree.clear()
                    self._app._mount_data_tree.set_host_project_root(
                        self._app.host_project_root
                    )
                    self._app.container_root_panel.clear()
                    self._app._mount_data_tree.container_root = ""
                    self._app._local_host.refresh()
                    self._app._scope_view.refresh()
                    self._app._update_status()
                    self._app._update_config_viewer()
                self._app.menu_manager.update_docker_menu_states()
            else:
                QMessageBox.warning(self._app, "Remove Failed", msg)

    def rename_container_root(self) -> None:
        """Show dialog to rename the container root path."""
        from PyQt6.QtWidgets import QInputDialog

        current_root = self._app._mount_data_tree.container_root
        new_root, accepted = QInputDialog.getText(
            self._app,
            "Rename Container Root",
            "Container Root:",
            text=current_root,
        )

        if not accepted or new_root.strip() == current_root:
            return

        new_root = new_root.strip()

        # Warn if Docker container exists — rename requires recreate
        from ..docker.container_ops import container_exists
        from ..docker.names import build_docker_name
        docker_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )
        if container_exists(docker_name):
            reply = QMessageBox.question(
                self._app,
                "Container Exists",
                "Warning: This change requires a container recreate.\n\nProceed?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Setting the property triggers stateChanged → auto-save + config viewer
        self._app._mount_data_tree.container_root = new_root

    def start_container(self) -> None:
        """Start (or ensure running) the current scope's Docker container."""
        if not self._app.host_project_root:
            return
        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope,
        )
        success, msg = ensure_container_running(container_name)
        if success:
            self._app.statusBar().showMessage(msg, 5000)
        else:
            QMessageBox.warning(self._app, "Start Failed", msg)
        self._app.menu_manager.update_docker_menu_states()
        self._app._scope_view.refresh()

    def stop_container(self) -> None:
        """Stop the current scope's Docker container."""
        if not self._app.host_project_root:
            return
        from ..docker.names import build_docker_name
        from ..docker.container_ops import stop_container as docker_stop
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope,
        )
        success, msg = docker_stop(container_name)
        if success:
            self._app.statusBar().showMessage(msg, 5000)
        else:
            QMessageBox.warning(self._app, "Stop Failed", msg)
        self._app.menu_manager.update_docker_menu_states()
        self._app._scope_view.refresh()

    def launch_container_terminal(self) -> None:
        """Launch a terminal session inside the Docker container."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )

        success, msg = ensure_container_running(container_name)
        if not success:
            QMessageBox.warning(self._app, "Container Error", msg)
            return

        docker_cmd = get_terminal_command(container_name)
        self._launch_terminal(docker_cmd, container_name, "terminal")

    def open_config_location(self) -> None:
        """Open the current scope's config directory in the OS file explorer."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from .app import PLACEHOLDER_SCOPE
        if self._app._current_scope == PLACEHOLDER_SCOPE:
            self._app.statusBar().showMessage("Create a named scope first", 5000)
            return

        from ..core.config import get_container_dir

        config_dir = get_container_dir(
            self._app.host_project_root, self._app._current_scope
        )

        if not config_dir.exists():
            QMessageBox.warning(
                self._app,
                "No Config",
                f"Config directory does not exist:\n{config_dir}",
            )
            return

        system = platform.system()
        try:
            if system == "Windows":
                subprocess.Popen(["explorer", str(config_dir)])
            elif system == "Darwin":
                subprocess.Popen(["open", str(config_dir)])
            else:
                subprocess.Popen(["xdg-open", str(config_dir)])

            self._app.statusBar().showMessage(
                f"Opened config: {config_dir}", 5000
            )
        except Exception as e:
            QMessageBox.critical(
                self._app,
                "Open Failed",
                f"Failed to open config location: {e}",
            )

    def launch_llm_in_container(self) -> None:
        """Launch Claude Code (LLM) inside the Docker container.

        Pre-flight: checks if the LLM binary exists in the container.
        If missing, offers to deploy before launching.
        """
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )
        container_root = self._app._mount_data_tree.container_root
        project_name = self._app.host_project_root.name
        work_dir = f"{container_root}/{project_name}"

        success, msg = ensure_container_running(container_name)
        if not success:
            QMessageBox.warning(self._app, "Container Error", msg)
            return

        # Pre-flight: verify LLM binary exists in container
        from ..container_ext import ClaudeInstaller

        deployer = ClaudeInstaller()
        if not deployer.is_installed(container_name):
            reply = QMessageBox.question(
                self._app,
                "Claude CLI Not Installed",
                f"{deployer.name} is not installed in container '{container_name}'.\n\n"
                "Would you like to install it now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.deploy_llm_to_container()
            return

        docker_cmd = get_llm_command(
            container_name, work_dir, deployer.BINARY_PATH
        )
        self._launch_terminal(docker_cmd, container_name, "Claude Code")

    def copy_llm_command(self) -> None:
        """Copy the LLM launch command to clipboard."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )
        container_root = self._app._mount_data_tree.container_root
        project_name = self._app.host_project_root.name
        work_dir = f"{container_root}/{project_name}"

        from ..container_ext import ClaudeInstaller
        deployer = ClaudeInstaller(auto_launch=False)

        docker_cmd = get_llm_command(
            container_name, work_dir, deployer.BINARY_PATH
        )

        QApplication.clipboard().setText(docker_cmd)
        self._app.statusBar().showMessage(
            f"Copied to clipboard: {docker_cmd}", 5000
        )

    def deploy_llm_to_container(self) -> None:
        """Deploy Claude Code LLM into the running container."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )

        success, msg = ensure_container_running(container_name)
        if not success:
            QMessageBox.warning(self._app, "Container Error", msg)
            return

        reply = QMessageBox.question(
            self._app,
            "Install Claude CLI",
            f"Install Claude CLI into container '{container_name}'?\n\n"
            "This will install via curl and may take a few minutes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        progress = self._create_progress_dialog(
            "Installing Claude CLI",
            "Installing Claude CLI...\n\nThis may take a few minutes.",
        )

        self._deploy_worker = DeployWorker(container_name, self._app)
        self._deploy_worker.finished.connect(
            lambda ok, message, version: self._on_deploy_finished(
                ok, message, version, progress
            )
        )
        self._deploy_worker.start()

    def deploy_git_to_container(self) -> None:
        """Deploy Git into the running container."""
        if not self._app.host_project_root:
            QMessageBox.warning(
                self._app, "No Project", "Please open a project first."
            )
            return

        from ..docker.names import build_docker_name
        container_name = build_docker_name(
            self._app.host_project_root, self._app._current_scope
        )

        success, msg = ensure_container_running(container_name)
        if not success:
            QMessageBox.warning(self._app, "Container Error", msg)
            return

        # Pre-flight: check if already installed
        from ..container_ext import GitInstaller
        installer = GitInstaller()
        if installer.is_installed(container_name):
            reply = QMessageBox.question(
                self._app,
                "Git Already Installed",
                f"Git is already installed in container '{container_name}'.\n\n"
                "Would you like to reinstall?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        reply = QMessageBox.question(
            self._app,
            "Install Git",
            f"Install Git into container '{container_name}'?\n\n"
            "This will install via the container's package manager.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        progress = self._create_progress_dialog(
            "Installing Git",
            "Installing Git...\n\nThis may take a minute.",
        )

        self._git_deploy_worker = GitDeployWorker(container_name, self._app)
        self._git_deploy_worker.finished.connect(
            lambda ok, message, version: self._on_deploy_finished(
                ok, message, version, progress
            )
        )
        self._git_deploy_worker.start()

    def _on_deploy_finished(
        self, success: bool, message: str, version: str,
        progress: QProgressDialog,
    ) -> None:
        """Handle LLM deployment completion."""
        progress.close()

        if success:
            version_info = f" (v{version})" if version else ""
            QMessageBox.information(
                self._app,
                "Installation Complete",
                f"{message}{version_info}",
            )
        else:
            QMessageBox.critical(
                self._app,
                "Installation Failed",
                message,
            )

    def _launch_terminal(
        self, docker_cmd: str, container_name: str, description: str
    ) -> None:
        """Launch a terminal with the given docker command."""
        system = platform.system()

        try:
            if system == "Windows":
                from PyQt6.QtCore import QSettings
                settings = QSettings("IgnoreScope", "IgnoreScope")
                terminal = settings.value("terminal_preference", "cmd")

                if terminal in ("powershell", "pwsh"):
                    exe = "pwsh" if terminal == "pwsh" else "powershell"
                    subprocess.Popen(
                        f'start {exe} -NoExit -Command "{docker_cmd}"',
                        shell=True,
                    )
                else:
                    subprocess.Popen(
                        f'start cmd /k "{docker_cmd}"',
                        shell=True,
                    )
            elif system == "Darwin":  # macOS
                script = f'tell application "Terminal" to do script "{docker_cmd}"'
                subprocess.Popen(["osascript", "-e", script])
            else:  # Linux
                terminals = [
                    ["gnome-terminal", "--", "bash", "-c", docker_cmd],
                    ["konsole", "-e", docker_cmd],
                    ["xterm", "-e", docker_cmd],
                ]
                for term_cmd in terminals:
                    try:
                        subprocess.Popen(term_cmd)
                        break
                    except FileNotFoundError:
                        continue
                else:
                    raise FileNotFoundError("No supported terminal emulator found")

            self._app.statusBar().showMessage(
                f"Launched {description} in {container_name}", 5000
            )
        except Exception as e:
            QMessageBox.critical(
                self._app,
                "Launch Failed",
                f"Failed to launch {description}: {e}",
            )
