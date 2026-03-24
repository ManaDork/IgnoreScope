"""P4 MCP Server extension installer.

Provides deployment of the P4 MCP Server binary into containers
from a /devenv mount (PyInstaller directory build).
Includes default .p4config and .p4ignore templates for IgnoreScope workflows.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .install_extension import ExtensionInstaller, DeployMethod, DeployResult


class P4McpInstaller(ExtensionInstaller):
    """Installer for P4 MCP Server in containers.

    Copies the PyInstaller directory build from a /devenv mount into
    /usr/local/lib/p4-mcp-server/ and symlinks the binary into PATH.
    Uses the inherited deploy_runtime() flow.
    """

    LIB_DIR = "/usr/local/lib/p4-mcp-server"
    SYMLINK_PATH = "/usr/local/bin/p4-mcp-server-linux"

    # P4 connection config template. Tokens: {p4port}, {p4user}, {p4client}
    P4CONFIG_TEMPLATE = """\
P4PORT={p4port}
P4USER={p4user}
P4CLIENT={p4client}
"""

    # P4 ignore rules — hides git artifacts from Perforce. Static (no tokens).
    P4IGNORE_TEMPLATE = """\
.git
.git*
.gitignore
.p4ignore
.ignore_scope/
"""

    def __init__(self, devenv_mount: str = "/devenv") -> None:
        """Initialize P4 MCP installer.

        Args:
            devenv_mount: Container path where C:\\_dev_env is mounted.
        """
        self._devenv_mount = devenv_mount

    @property
    def name(self) -> str:
        return "P4 MCP Server"

    @property
    def binary_name(self) -> str:
        return "p4-mcp-server"

    @property
    def supported_methods(self) -> list[DeployMethod]:
        return [DeployMethod.FULL]

    @property
    def src_dir(self) -> str:
        """Source directory for P4 MCP build inside the devenv mount."""
        return f"{self._devenv_mount}/mcp/p4-mcp-server/linux"

    # =========================================================================
    # Runtime deployment (docker exec)
    # =========================================================================

    def get_install_commands(self, method: DeployMethod = DeployMethod.FULL) -> list[list[str]]:
        """Get installation commands to copy and symlink P4 MCP binary.

        Args:
            method: Deployment method (ignored — P4 MCP only supports FULL).

        Returns:
            List containing a single bash command for cp + chmod + ln.
        """
        return [
            [
                'bash', '-c',
                f'test -d "{self.src_dir}" '
                f'&& test -f "{self.src_dir}/p4-mcp-server" '
                f'&& cp -r "{self.src_dir}" "{self.LIB_DIR}" '
                f'&& chmod +x "{self.LIB_DIR}/p4-mcp-server" '
                f'&& ln -sf "{self.LIB_DIR}/p4-mcp-server" "{self.SYMLINK_PATH}" '
                f'&& echo "staged OK"',
            ]
        ]

    # =========================================================================
    # Verification
    # =========================================================================

    def get_version_command(self) -> list[str]:
        """Get command to check P4 MCP Server version."""
        return [self.SYMLINK_PATH, "--version"]

    def parse_version_output(self, output: str) -> str | None:
        """Parse version from P4 MCP Server output.

        Tries semver pattern first; falls back to "installed" for
        non-empty output (PyInstaller binary may not have clean version).

        Args:
            output: Raw command output

        Returns:
            Version string, "installed" for non-parseable output, or None
        """
        if not output:
            return None
        match = re.search(r'v?(\d+\.\d+\.\d+)', output)
        if match:
            return match.group(1)
        if output.strip():
            return "installed"
        return None

    def is_installed(self, container_name: str) -> bool:
        """Quick check if P4 MCP Server is installed via test -x.

        Args:
            container_name: Name of container

        Returns:
            True if symlink exists and is executable
        """
        from ..docker import exec_in_container

        success, _, _ = exec_in_container(
            container_name, ['test', '-x', self.SYMLINK_PATH], timeout=5
        )
        return success

    # =========================================================================
    # Precondition checks
    # =========================================================================

    def check_devenv_mount(self, container_name: str) -> tuple[bool, str]:
        """Check that the /devenv mount is present in the container.

        Args:
            container_name: Name of running container

        Returns:
            (True, "") if mount is present, (False, error_message) otherwise
        """
        from ..docker import exec_in_container

        check_cmd = ['bash', '-c', f'test -d "{self._devenv_mount}"']
        success, _, _ = exec_in_container(
            container_name, check_cmd, timeout=10
        )
        if success:
            return True, ""
        return False, (
            f"The {self._devenv_mount} mount is not present. "
            f"Configure C:\\_dev_env sibling in IgnoreScope GUI."
        )

    # =========================================================================
    # Config deployment (template files)
    # =========================================================================

    def deploy_config(
        self,
        container_name: str,
        context: dict[str, str],
        project_dir: str,
        scope_dir: str,
    ) -> list[DeployResult]:
        """Write default .p4config and .p4ignore into the container.

        Args:
            container_name: Name of running container.
            context: Token dict — requires "p4port", "p4user", "p4client".
            project_dir: Container project root (e.g. "/MyProject").
            scope_dir: Container scope dir (e.g. "/MyProject/.ignore_scope/dev").

        Returns:
            List of DeployResults (one per file written).
        """
        from ..docker import push_file_to_container

        results: list[DeployResult] = []

        # --- .p4config (rendered) → scope_dir/.p4config ---
        p4config_content = self.P4CONFIG_TEMPLATE
        for token in ("p4port", "p4user", "p4client"):
            p4config_content = p4config_content.replace(
                f"{{{token}}}", context.get(token, "")
            )
        p4config_dest = f"{scope_dir}/.p4config"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".p4config", delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(p4config_content)
            tmp_path = Path(tmp.name)

        try:
            success, msg = push_file_to_container(
                container_name, tmp_path, p4config_dest
            )
            if success:
                results.append(DeployResult(
                    success=True, message=f"Wrote {p4config_dest}",
                ))
            else:
                results.append(DeployResult(
                    success=False, message=f"Push .p4config failed: {msg}",
                ))
                return results
        finally:
            tmp_path.unlink(missing_ok=True)

        # --- .p4ignore (static) → project_dir/.p4ignore ---
        p4ignore_dest = f"{project_dir}/.p4ignore"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".p4ignore", delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(self.P4IGNORE_TEMPLATE)
            tmp_path = Path(tmp.name)

        try:
            success, msg = push_file_to_container(
                container_name, tmp_path, p4ignore_dest
            )
            if success:
                results.append(DeployResult(
                    success=True, message=f"Wrote {p4ignore_dest}",
                ))
            else:
                results.append(DeployResult(
                    success=False, message=f"Push .p4ignore failed: {msg}",
                ))
        finally:
            tmp_path.unlink(missing_ok=True)

        return results

    # =========================================================================
    # High-level deploy (wraps base deploy_runtime)
    # =========================================================================

    def deploy(
        self,
        container_name: str,
        timeout: int = 60,
    ) -> DeployResult:
        """Deploy P4 MCP Server to a running container.

        Args:
            container_name: Name of target container
            timeout: Command timeout in seconds

        Returns:
            DeployResult with success status and details
        """
        from ..docker import ensure_container_running

        success, msg = ensure_container_running(container_name)
        if not success:
            return DeployResult(
                success=False,
                message=f"Container not available: {msg}",
            )

        mount_ok, mount_msg = self.check_devenv_mount(container_name)
        if not mount_ok:
            return DeployResult(
                success=False,
                message=mount_msg,
            )

        return self.deploy_runtime(
            container_name, method=DeployMethod.FULL, timeout=timeout
        )


# Convenience functions
def deploy_p4_mcp(
    container_name: str, devenv_mount: str = "/devenv", timeout: int = 60
) -> DeployResult:
    """Deploy P4 MCP Server into running container.

    Args:
        container_name: Target container name
        devenv_mount: Container path where devenv is mounted
        timeout: Installation timeout in seconds

    Returns:
        DeployResult with status
    """
    installer = P4McpInstaller(devenv_mount=devenv_mount)
    return installer.deploy(container_name, timeout=timeout)


def verify_p4_mcp(container_name: str) -> DeployResult:
    """Verify P4 MCP Server is installed and get version.

    Args:
        container_name: Target container name

    Returns:
        DeployResult with version if installed
    """
    installer = P4McpInstaller()
    return installer.verify(container_name)
