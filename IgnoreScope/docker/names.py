"""Docker naming and volume management.

Provides DockerNames class for consistent naming of Docker resources
across containers, images, and volumes.
"""

from dataclasses import dataclass
from pathlib import Path


# Re-exported from utils.strings — canonical location for pure string sanitizers.
# Kept here for backward compatibility (tests, external consumers).
from ..utils.strings import sanitize_volume_name  # noqa: F401


# TODO Make Nice Name (2-28-2026)
def sanitize_scope_name(name: str) -> str:
    """Sanitize a user-entered scope name for Docker + filesystem safety.

    Keeps case (Docker container names allow mixed case).
    Replaces spaces/slashes with underscores.
    Strips characters invalid in Docker names or filesystem paths.
    """
    result = []
    for char in name:
        if char.isalnum() or char in '_.-':
            result.append(char)
        elif char in '/\\ ':
            result.append('_')
    sanitized = ''.join(result)
    if sanitized and not sanitized[0].isalnum():
        sanitized = 'v' + sanitized
    return sanitized or 'default'


def build_docker_name(host_project_root: Path, scope_name: str) -> str:
    """Build the Docker container name from project root and scope name.

    Single source of truth for Docker container naming.
    Format: {sanitized_project}__{sanitized_scope}

    Args:
        host_project_root: Project root directory (uses .name for project name)
        scope_name: Scope name (e.g. 'dev', 'default')

    Returns:
        Docker-safe container name, e.g. 'mygame__dev'
    """
    project = sanitize_volume_name(host_project_root.name)
    scope = sanitize_volume_name(scope_name)
    return f"{project}__{scope}"


@dataclass
class DockerNames:
    """Superseded Docker naming API — kept for reference.

    Uses old ``claude-{name}`` convention. Active convention is
    ``build_docker_name()`` → ``{project}__{scope}``.
    Do not use for new code.

    All Docker resources (container, image, volume) derive from the same
    sanitized project name to ensure consistency across all operations.

    Usage:
        names = DockerNames.from_host_project_root(host_project_root)
        print(names.container)  # claude-my_project
        print(names.image)      # claude-my_project:latest
        print(names.volume)     # my_project-claude-auth
    """
    project_name: str  # Original project name
    sanitized: str     # Sanitized for Docker use

    @classmethod
    def from_host_project_root(cls, host_project_root: Path, scope_name: str) -> "DockerNames":
        """Create DockerNames from a project root path.

        Args:
            host_project_root: Path to project root directory
            scope_name: Scope configuration name

        Returns:
            DockerNames with project-scope composite naming
        """
        name = f"{host_project_root.name}-{scope_name}"
        sanitized = sanitize_volume_name(name)
        return cls(project_name=name, sanitized=sanitized)

    @classmethod
    def from_name(cls, name: str) -> "DockerNames":
        """Create DockerNames from a project name string."""
        sanitized = sanitize_volume_name(name)
        return cls(project_name=name, sanitized=sanitized)

    @property
    def container(self) -> str:
        """Container name: claude-{sanitized}"""
        return f"claude-{self.sanitized}"

    @property
    def image(self) -> str:
        """Image name: claude-{sanitized}:latest"""
        return f"{self.container}:latest"

    @property
    def volume(self) -> str:
        """Auth volume name: {sanitized}-claude-auth"""
        return f"{self.sanitized}-claude-auth"

    @property
    def compose_project(self) -> str:
        """Docker Compose project name (same as sanitized)."""
        return self.sanitized
