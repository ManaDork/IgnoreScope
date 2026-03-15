"""Claude Code CLI deployer.

Provides deployment of Claude Code CLI into containers via:
- Native installation (curl installer script)
- NPM installation (@anthropic-ai/claude-code)
"""

from __future__ import annotations

import re
from datetime import datetime

from .deployer import LLMDeployer, DeployMethod, DeployResult


class ClaudeDeployer(LLMDeployer):
    """Deployer for Claude Code CLI.

    Supports two installation methods:
    - NATIVE: curl -fsSL https://claude.ai/install.sh | bash
    - NPM: npm install -g @anthropic-ai/claude-code

    Native is preferred for build-time (baked into image).
    NPM is useful for runtime deployment to existing containers.
    """

    # Installation URLs and packages
    NATIVE_INSTALL_URL = "https://claude.ai/install.sh"
    # Legacy fallback from pre-.exe era. Not used by current RUNTIME pipeline.
    NPM_PACKAGE = "@anthropic-ai/claude-code"

    # Binary location after native install
    BINARY_PATH = "/root/.local/bin/claude"

    # Auth volume mount point
    AUTH_MOUNT = "/root/.claude"

    def __init__(self, auto_launch: bool = True):
        """Initialize Claude deployer.

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
        return [DeployMethod.BUILD_TIME, DeployMethod.RUNTIME]

    # =========================================================================
    # Build-time deployment (Dockerfile generation)
    # =========================================================================

    def get_dockerfile_snippets(self) -> dict[str, str]:
        """Get Dockerfile snippets for Claude installation.

        SHELVED — used only by generate_dockerfile_with_llm() which is not
        wired into production. Kept for future reference.

        Returns complete Dockerfile segments for:
        - System packages
        - Claude installation
        - Environment variables
        """
        return {
            'packages': 'git curl ca-certificates nodejs npm',

            'install': f'''\
# Install Claude Code CLI (native installer)
# Uses bash (not sh) because installer script requires bash syntax
# Installs to ~/.local/bin/claude (doesn't conflict with {self.AUTH_MOUNT} auth volume)
RUN curl -fsSL {self.NATIVE_INSTALL_URL} | bash

# Ensure Claude is in PATH
ENV PATH="{self.BINARY_PATH.rsplit('/', 1)[0]}:$PATH"
''',

            'env': '''\
# Configure Claude environment
ENV CLAUDE_PROJECT_DIR=/workspace
ENV CLAUDE_CODE_DISABLE_AUTO_UPDATE=1
''',
        }

    def get_entrypoint_script(self, workspace_dir: str = "/workspace") -> str:
        """Generate entrypoint script for Claude containers.

        SHELVED — used only by generate_dockerfile_with_llm() which is not
        wired into production. Kept for future reference.

        The entrypoint:
        1. Sets up environment
        2. Optionally syncs hooks/settings
        3. Auto-launches Claude if installed and enabled
        4. Falls back to shell otherwise

        Args:
            workspace_dir: Container workspace directory

        Returns:
            Shell script content
        """
        now = datetime.now().strftime("%Y-%m-%d")

        auto_launch_block = ""
        if self.auto_launch:
            auto_launch_block = f'''
# Auto-launch Claude if available and no command specified
if [ "$1" = "bash" ] || [ "$1" = "sh" ] || [ -z "$1" ]; then
    if [ -x "{self.BINARY_PATH}" ]; then
        echo "[IgnoreScope] Launching Claude Code..."
        cd "{workspace_dir}"
        exec "{self.BINARY_PATH}"
    fi
fi
'''

        return f'''\
#!/bin/bash
# IgnoreScope Container Entrypoint
# Generated: {now}
#
# This script:
# 1. Sets up the Claude environment
# 2. Auto-launches Claude if installed (optional)
# 3. Falls back to executing the provided command

set -e

# Ensure workspace exists
mkdir -p "{workspace_dir}"

# Set working directory
cd "{workspace_dir}"

# Environment setup
export CLAUDE_PROJECT_DIR="{workspace_dir}"
export CLAUDE_CODE_DISABLE_AUTO_UPDATE=1
{auto_launch_block}
# Execute the provided command (or default to bash)
if [ -z "$1" ]; then
    exec /bin/bash
else
    exec "$@"
fi
'''

    # =========================================================================
    # Runtime deployment (docker exec)
    # =========================================================================

    def get_install_commands(self, method: DeployMethod) -> list[list[str]]:
        """Get installation commands for runtime deployment.

        Args:
            method: BUILD_TIME uses native curl, RUNTIME uses npm

        Returns:
            List of command arrays for docker exec
        """
        if method == DeployMethod.BUILD_TIME:
            # Native installation (Dockerfile context — prereqs in separate RUN layer)
            return [
                ['bash', '-c', f'curl -fsSL {self.NATIVE_INSTALL_URL} | bash'],
            ]
        else:
            # Runtime installation — must self-provision prereqs first
            # Container image is python:3.11-slim with no curl/npm/nodejs
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
        """Quick check if Claude is installed via which lookup.

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


# Convenience functions for common operations
def deploy_claude_native(container_name: str, timeout: int = 300) -> DeployResult:
    """Deploy Claude using native installer.

    Args:
        container_name: Target container name
        timeout: Installation timeout in seconds

    Returns:
        DeployResult with status
    """
    deployer = ClaudeDeployer()
    return deployer.deploy_runtime(
        container_name,
        method=DeployMethod.BUILD_TIME,  # Uses curl installer
        timeout=timeout,
    )


def deploy_claude_npm(container_name: str, timeout: int = 300) -> DeployResult:
    """Deploy Claude using NPM.

    Args:
        container_name: Target container name
        timeout: Installation timeout in seconds

    Returns:
        DeployResult with status
    """
    deployer = ClaudeDeployer()
    return deployer.deploy_runtime(
        container_name,
        method=DeployMethod.RUNTIME,  # Uses npm install
        timeout=timeout,
    )


def verify_claude(container_name: str) -> DeployResult:
    """Verify Claude is installed and get version.

    Args:
        container_name: Target container name

    Returns:
        DeployResult with version if installed
    """
    deployer = ClaudeDeployer()
    return deployer.verify(container_name)
