"""Base extension installer interface.

Defines the protocol for extension deployment into containers.
Implementations provide specific installation and verification logic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Tuple


class DeployMethod(Enum):
    """Extension deployment method.

    MINIMAL: Single command, assumes deps (curl, ca-certificates) present.
    FULL: Provisions deps first, then installs.
    """

    MINIMAL = auto()
    FULL = auto()


@dataclass
class DeployResult:
    """Result of an extension deployment operation.

    Attributes:
        success: Whether deployment succeeded
        message: Human-readable status message
        version: Extension version string if available
        method: Deployment method used
        details: Additional deployment details
    """

    success: bool
    message: str
    version: str = ""
    method: DeployMethod | None = None
    details: dict = field(default_factory=dict)


class ExtensionInstaller(ABC):
    """Abstract base class for container extension deployment.

    Implementations provide:
    - Dockerfile snippets for build-time installation
    - Runtime installation commands
    - Verification and version detection
    - Entrypoint script generation
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the extension (e.g., 'Claude Code')."""
        ...

    @property
    @abstractmethod
    def binary_name(self) -> str:
        """Binary/command name (e.g., 'claude')."""
        ...

    @property
    @abstractmethod
    def supported_methods(self) -> list[DeployMethod]:
        """List of supported deployment methods."""
        ...

    # =========================================================================
    # Build-time deployment (Dockerfile generation)
    # =========================================================================

    def get_dockerfile_snippets(self) -> dict[str, str]:
        """Get Dockerfile snippets for build-time installation.

        Returns:
            Dict with keys:
            - 'packages': System packages to install (apt-get)
            - 'install': RUN commands for installation
            - 'env': ENV declarations

        Default: empty dict. Override in subclasses that need build-time support.
        """
        return {}

    def get_entrypoint_script(self, workspace_dir: str = "/workspace") -> str:
        """Generate entrypoint script content.

        The entrypoint handles:
        - Environment setup
        - Optional auto-launch
        - Fallback to shell if not installed

        Args:
            workspace_dir: Container workspace directory

        Returns:
            Shell script content for entrypoint.sh

        Default: empty string. Override in subclasses that need entrypoint support.
        """
        return ""

    # =========================================================================
    # Runtime deployment (docker exec)
    # =========================================================================

    @abstractmethod
    def get_install_commands(self, method: DeployMethod) -> list[list[str]]:
        """Get installation commands for runtime deployment.

        Args:
            method: Deployment method (affects command selection)

        Returns:
            List of command arrays to execute via docker exec.
            Each inner list is a single command with arguments.
        """
        ...

    # =========================================================================
    # Verification
    # =========================================================================

    @abstractmethod
    def get_version_command(self) -> list[str]:
        """Get command to check extension version.

        Returns:
            Command array to execute via docker exec.
            Should output version string on success.
        """
        ...

    @abstractmethod
    def parse_version_output(self, output: str) -> str | None:
        """Parse version from command output.

        Args:
            output: Raw output from version command

        Returns:
            Version string or None if parsing failed
        """
        ...

    def get_verify_command(self) -> list[str]:
        """Get command to verify extension is functional.

        Default implementation uses version command.

        Returns:
            Command array to execute via docker exec.
        """
        return self.get_version_command()

    # =========================================================================
    # High-level operations (use docker module)
    # =========================================================================

    def deploy_runtime(
        self,
        container_name: str,
        method: DeployMethod = DeployMethod.FULL,
        timeout: int = 300,
    ) -> DeployResult:
        """Deploy extension to running container.

        Args:
            container_name: Name of target container
            method: Deployment method
            timeout: Command timeout in seconds

        Returns:
            DeployResult with success status and details
        """
        from ..docker import ensure_container_running, exec_in_container

        # Ensure container is running
        success, msg = ensure_container_running(container_name)
        if not success:
            return DeployResult(
                success=False,
                message=f"Container not available: {msg}",
                method=method,
            )

        # Get installation commands
        commands = self.get_install_commands(method)
        if not commands:
            return DeployResult(
                success=False,
                message=f"No installation commands for method: {method.name}",
                method=method,
            )

        # Execute installation commands
        for cmd in commands:
            success, stdout, stderr = exec_in_container(container_name, cmd, timeout)
            if not success:
                return DeployResult(
                    success=False,
                    message=f"Installation failed: {stderr or stdout or 'Unknown error'}",
                    method=method,
                    details={'command': cmd},
                )

        # Verify installation
        verify_result = self.verify(container_name)
        if not verify_result.success:
            return DeployResult(
                success=False,
                message=f"Installation completed but verification failed: {verify_result.message}",
                method=method,
            )

        return DeployResult(
            success=True,
            message=f"{self.name} deployed successfully",
            version=verify_result.version,
            method=method,
        )

    def verify(self, container_name: str, timeout: int = 30) -> DeployResult:
        """Verify extension is installed and functional.

        Args:
            container_name: Name of target container
            timeout: Command timeout in seconds

        Returns:
            DeployResult with version if successful
        """
        from ..docker import exec_in_container

        success, stdout, stderr = exec_in_container(
            container_name, self.get_version_command(), timeout
        )

        if success:
            version = self.parse_version_output(stdout)
            return DeployResult(
                success=True,
                message=f"{self.name} is installed",
                version=version or "unknown",
            )
        else:
            return DeployResult(
                success=False,
                message=f"{self.name} not found or not functional",
            )
