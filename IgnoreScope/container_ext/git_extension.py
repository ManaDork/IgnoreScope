"""Git extension installer.

Provides deployment of Git into containers via apt-get (debian) or apk (alpine).
Includes default .gitignore template for IgnoreScope workflows.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from .install_extension import ExtensionInstaller, DeployMethod, DeployResult


class GitInstaller(ExtensionInstaller):
    """Installer for Git in containers.

    Detects container distro (debian/alpine) and installs Git via
    the appropriate package manager. Uses the inherited deploy_runtime() flow.
    """

    BINARY_PATH = "/usr/bin/git"

    # Default .gitignore for IgnoreScope workflows.
    # Blanket-ignore all; whitelist Claude workflow artifacts in scope dir.
    # Claude uses 'git add -f' to track specific source files it modifies.
    GITIGNORE_TEMPLATE = """\
# Ignore EVERYTHING by default.
# Claude uses 'git add -f' to track specific source files it modifies.
# Workflow artifacts in .ignore_scope/{scope_name}/ are whitelisted below.
*

# Whitelist: Claude workflow artifacts
!.ignore_scope/{scope_name}/
!.ignore_scope/{scope_name}/**

# Re-ignore: IgnoreScope host config inside whitelisted scope dir
.ignore_scope/{scope_name}/scope_docker_desktop.json
.ignore_scope/{scope_name}/Dockerfile
.ignore_scope/{scope_name}/docker-compose.yml
.ignore_scope/{scope_name}/.llm/

# Re-ignore: ephemeral state
.ignore_scope/{scope_name}/.context-mode/
.ignore_scope/{scope_name}/.claude/settings.local.json
*.db
"""

    INSTALL_COMMANDS = {
        "debian": [
            ['bash', '-c',
             'apt-get update && apt-get install -y --no-install-recommends git '
             '&& rm -rf /var/lib/apt/lists/*'],
        ],
        "alpine": [
            ['sh', '-c', 'apk add --no-cache git'],
        ],
    }

    def __init__(self, distro: str = "auto"):
        """Initialize Git installer.

        Args:
            distro: Target distro ("debian", "alpine", or "auto" for detection).
        """
        self._distro = distro
        self._resolved_distro: str = ""

    @property
    def name(self) -> str:
        return "Git"

    @property
    def binary_name(self) -> str:
        return "git"

    @property
    def supported_methods(self) -> list[DeployMethod]:
        return [DeployMethod.FULL]

    # =========================================================================
    # Distro detection
    # =========================================================================

    def detect_distro(self, container_name: str) -> str:
        """Detect container distro by probing for apk.

        Args:
            container_name: Name of running container

        Returns:
            "alpine" if apk is found, "debian" otherwise (default).
        """
        from ..docker import exec_in_container

        success, _, _ = exec_in_container(
            container_name, ['sh', '-c', 'command -v apk'], timeout=10
        )
        return "alpine" if success else "debian"

    # =========================================================================
    # Runtime deployment (docker exec)
    # =========================================================================

    def get_isolation_paths(self) -> list[str]:
        """Git is a system package (apt-get/apk). No isolation — survives in image layer."""
        return []

    def get_install_commands(self, method: DeployMethod) -> list[list[str]]:
        """Get installation commands for the resolved distro.

        Args:
            method: Deployment method (ignored — Git only supports FULL).

        Returns:
            List of command arrays for docker exec.
        """
        distro = self._resolved_distro or "debian"
        return list(self.INSTALL_COMMANDS.get(distro, self.INSTALL_COMMANDS["debian"]))

    # =========================================================================
    # Verification
    # =========================================================================

    def get_version_command(self) -> list[str]:
        """Get command to check Git version."""
        return ['git', '--version']

    def parse_version_output(self, output: str) -> str | None:
        """Parse version from git --version output.

        Expected format: "git version 2.39.2"

        Args:
            output: Raw command output

        Returns:
            Version string or None
        """
        if not output:
            return None
        match = re.search(r'(\d+\.\d+\.\d+)', output)
        return match.group(1) if match else None

    def is_installed(self, container_name: str) -> bool:
        """Quick check if Git is installed via test -x.

        Args:
            container_name: Name of container

        Returns:
            True if Git binary exists and is executable
        """
        from ..docker import exec_in_container

        success, _, _ = exec_in_container(
            container_name, ['test', '-x', self.BINARY_PATH], timeout=5
        )
        return success

    # =========================================================================
    # High-level deploy (wraps base deploy_runtime)
    # =========================================================================

    def deploy(
        self,
        container_name: str,
        distro: str = "auto",
        timeout: int = 120,
    ) -> DeployResult:
        """Deploy Git to a running container.

        Args:
            container_name: Name of target container
            distro: "debian", "alpine", or "auto" for detection
            timeout: Command timeout in seconds

        Returns:
            DeployResult with success status and details
        """
        from ..docker import ensure_container_running

        if distro == "auto":
            success, msg = ensure_container_running(container_name)
            if not success:
                return DeployResult(
                    success=False,
                    message=f"Container not available: {msg}",
                )
            self._resolved_distro = self.detect_distro(container_name)
        else:
            self._resolved_distro = distro

        return self.deploy_runtime(
            container_name, method=DeployMethod.FULL, timeout=timeout
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
        """Write default .gitignore into the container.

        Args:
            container_name: Name of running container.
            context: Token dict — requires "scope_name".
            project_dir: Container project root (e.g. "/MyProject").
            scope_dir: Container scope dir (e.g. "/MyProject/.ignore_scope/dev").

        Returns:
            List with one DeployResult for .gitignore.
        """
        from ..docker import push_file_to_container

        scope_name = context.get("scope_name", "default")
        content = self.GITIGNORE_TEMPLATE.replace("{scope_name}", scope_name)
        container_dest = f"{project_dir}/.gitignore"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".gitignore", delete=False, encoding="utf-8",
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            success, msg = push_file_to_container(
                container_name, tmp_path, container_dest
            )
            if success:
                return [DeployResult(
                    success=True, message=f"Wrote {container_dest}",
                )]
            return [DeployResult(
                success=False, message=f"Push .gitignore failed: {msg}",
            )]
        finally:
            tmp_path.unlink(missing_ok=True)

    # =========================================================================
    # Git identity configuration
    # =========================================================================

    def configure_identity(
        self, container_name: str, name: str, email: str
    ) -> tuple[bool, str]:
        """Configure git user.name and user.email in the container.

        Args:
            container_name: Name of running container
            name: Git user name
            email: Git user email

        Returns:
            (success, message)
        """
        from ..docker import exec_in_container

        cmd = [
            'sh', '-c',
            f'git config --global user.name "{name}" '
            f'&& git config --global user.email "{email}"',
        ]
        success, stdout, stderr = exec_in_container(container_name, cmd, timeout=10)
        if success:
            return True, f"Git identity configured: {name} <{email}>"
        return False, f"Failed to configure identity: {stderr or stdout}"

