"""Claude Code CLI extension installer.

Provides deployment of Claude Code CLI into containers via
native installation (curl installer script).
"""

from __future__ import annotations

import re
from datetime import datetime

from .install_extension import ExtensionInstaller, DeployMethod, DeployResult
from ..core.constants import CONTAINER_CLAUDE_AUTH


class ClaudeInstaller(ExtensionInstaller):
    """Installer for Claude Code CLI.

    Installs via native curl installer (curl -fsSL https://claude.ai/install.sh | bash).
    Two deployment variants:
    - MINIMAL: Single curl command, assumes deps present in image.
    - FULL: Provisions deps (curl, ca-certificates) via apt-get, then curl install.
    """

    # Installation URL
    NATIVE_INSTALL_URL = "https://claude.ai/install.sh"

    # Binary location after native install
    BINARY_PATH = "/root/.local/bin/claude"

    # Auth volume mount point — single source of truth in core.constants
    AUTH_MOUNT = CONTAINER_CLAUDE_AUTH

    def __init__(self, auto_launch: bool = True):
        """Initialize Claude installer.

        Args:
            auto_launch: If True, entrypoint auto-launches Claude.
                        If False, drops to shell.
        """
        self.auto_launch = auto_launch

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def binary_name(self) -> str:
        return "claude"

    @property
    def supported_methods(self) -> list[DeployMethod]:
        return [DeployMethod.MINIMAL, DeployMethod.FULL]

    # =========================================================================
    # Runtime deployment (docker exec)
    # =========================================================================

    def get_isolation_paths(self) -> list[str]:
        """Claude CLI installs to /root/.local/bin/ and /root/.local/lib/."""
        return ["/root/.local"]

    def get_install_commands(self, method: DeployMethod) -> list[list[str]]:
        """Get installation commands for runtime deployment.

        Args:
            method: MINIMAL assumes deps present, FULL provisions deps first.

        Returns:
            List of command arrays for docker exec
        """
        if method == DeployMethod.MINIMAL:
            # Assumes curl/ca-certificates already in image
            return [
                ['bash', '-c', f'curl -fsSL {self.NATIVE_INSTALL_URL} | bash'],
            ]
        else:
            # Self-provision prereqs first (python:3.11-slim has no curl)
            return [
                ['bash', '-c',
                 'apt-get update && apt-get install -y --no-install-recommends '
                 'curl ca-certificates && rm -rf /var/lib/apt/lists/*'],
                ['bash', '-c', f'curl -fsSL {self.NATIVE_INSTALL_URL} | bash'],
            ]

    # =========================================================================
    # Verification
    # =========================================================================

    def get_version_command(self) -> list[str]:
        """Get command to check Claude version."""
        return [self.BINARY_PATH, '--version']

    def parse_version_output(self, output: str) -> str | None:
        """Parse version from claude --version output.

        Expected format: "claude-code version X.Y.Z" or similar

        Args:
            output: Raw command output

        Returns:
            Version string or None
        """
        if not output:
            return None

        # Try common version patterns
        patterns = [
            r'(\d+\.\d+\.\d+)',  # X.Y.Z
            r'version\s+(\S+)',  # "version X.Y.Z"
            r'v(\d+\.\d+\.\d+)',  # vX.Y.Z
        ]

        for pattern in patterns:
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                return match.group(1)

        # Fallback: return first line if short
        first_line = output.split('\n')[0].strip()
        if len(first_line) < 50:
            return first_line

        return None

    # =========================================================================
    # Claude-specific utilities
    # =========================================================================

    def is_installed(self, container_name: str) -> bool:
        """Quick check if Claude is installed via test -x.

        Args:
            container_name: Name of container

        Returns:
            True if Claude binary exists and is executable
        """
        from ..docker import exec_in_container

        success, _, _ = exec_in_container(
            container_name, ['test', '-x', self.BINARY_PATH], timeout=5
        )
        return success

    def get_auth_volume_mount(self, volume_name: str) -> str:
        """Get volume mount string for Claude auth persistence.

        Args:
            volume_name: Name of the Docker volume

        Returns:
            Volume mount string for docker-compose
        """
        return f"{volume_name}:{self.AUTH_MOUNT}"

