"""ScopeDockerConfig: Extended LocalMountConfig with file tracking.

Manages Docker container configuration including:
- mount_specs: Mount-centric pathspec configuration (inherited from LocalMountConfig)
- pushed_files: Files currently in container (pushed via docker cp)
- container_files: Files created inside container (discovered via scan)
- dev_mode: Safe mode (./Pulled/) vs production mode (overwrite)
- container_root: Configurable container root path (default: /workspace)
- siblings: External directories mounted as sibling paths in container
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from .local_mount_config import LocalMountConfig, ExtensionConfig
from ..utils.paths import to_absolute_paths, to_relative_posix
from .._version import __version__, check_version_mismatch


# Default container root path
DEFAULT_CONTAINER_ROOT = "/workspace"

# Config directory and file names
IGSC_DIR_NAME = ".ignore_scope"
CONFIG_FILENAME = "scope_docker_desktop.json"


def get_container_path(container_root: str, rel_path: str) -> str:
    """Build a container-absolute path from root and relative path.

    Single source of truth for the container path formula.
    rel_path is relative to host_container_root (includes project name naturally).

    Args:
        container_root: Container root path (e.g., '/{HCR.name}')
        rel_path: POSIX relative path from host_container_root (may be empty)

    Returns:
        Container-absolute POSIX path (e.g., '/Projects/MyProject/src/api')
    """
    if rel_path:
        return f"{container_root}/{rel_path}"
    return container_root


@dataclass
class SiblingMount(LocalMountConfig):
    """Configuration for mounting external directories as container siblings.

    Inherits mount_specs/pushed_files/mirrored from LocalMountConfig.
    Adds host_path and container_path for sibling-specific routing.

    Siblings are directories outside the project root that get mounted
    at sibling paths in the container (e.g., /shared/, /tools/).

    Each sibling can have its own mount_specs and pushed_files,
    providing the same visibility control as the primary project root.

    Attributes:
        host_path: Absolute path to directory on host (e.g., E:\\SharedLibs\\)
        container_path: Mount path in container (e.g., /shared/)
    """

    host_path: Path = field(kw_only=True)
    container_path: str = field(kw_only=True)

    def to_dict(self) -> dict:
        """Convert to dictionary with paths relative to host_path.

        Chains to super().to_dict() for mount_specs/pushed_files,
        then adds host_path and container_path.

        Returns:
            Dict suitable for JSON serialization
        """
        base_dict = super().to_dict(self.host_path)
        return {
            'host_path': str(self.host_path),
            'container_path': self.container_path,
            **base_dict,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SiblingMount':
        """Create from dictionary.

        Parses host_path/container_path, delegates path fields to super().

        Args:
            data: Dict from JSON deserialization

        Returns:
            SiblingMount instance
        """
        host_path = Path(data['host_path'])
        base = LocalMountConfig.from_dict(data, host_path)
        return cls(
            mount_specs=base.mount_specs,
            pushed_files=base.pushed_files,
            host_path=host_path,
            container_path=data['container_path'],
        )


@dataclass
class ScopeDockerConfig(LocalMountConfig):
    """Extended LocalMountConfig with file tracking and dev mode.

    Inherits mount_specs, pushed_files, mirrored from LocalMountConfig.

    Attributes:
        container_files: Set of files created inside the container (discovered via scan)
        scope_name: Scope configuration name (e.g., 'dev', 'default')
        host_project_root: Project root path for relative path resolution
        dev_mode: If True, pull to ./Pulled/{timestamp}/ (safe)
                 If False, pull overwrites original files (production)
        container_root: Container root path (default: /workspace)
        siblings: List of external directories mounted as container siblings
        extensions: List of installed extension configs with isolation volume tracking
        ports: List of port mappings for docker-compose (e.g., ["3900:3900", "8080:8080"])
    """

    container_files: set[Path] = field(default_factory=set)
    scope_name: str = ""
    host_project_root: Optional[Path] = None
    host_container_root: Optional[Path] = None
    dev_mode: bool = True
    container_root: str = ""
    siblings: list[SiblingMount] = field(default_factory=list)
    extensions: list[ExtensionConfig] = field(default_factory=list)
    ports: list[str] = field(default_factory=list)
    show_hidden: bool = False
    container_mode: Literal["Hybrid", "Isolation"] = "Hybrid"
    init_source: Literal["cp", "clone"] = "cp"

    def __post_init__(self):
        """Derive defaults for host_container_root and container_root."""
        if not self.host_container_root and self.host_project_root:
            self.host_container_root = self.host_project_root.parent
        if not self.container_root:
            if self.mirrored and self.host_container_root:
                self.container_root = f"/{self.host_container_root.name}"
            else:
                self.container_root = DEFAULT_CONTAINER_ROOT

    def to_dict(self, host_project_root: Optional[Path] = None) -> dict:
        """Convert to dictionary with relative paths.

        pushed_files serialized inside 'local' section (via super().to_dict).
        mirrored serialized at top level.

        Args:
            host_project_root: Base path for relative conversion. Uses self.host_project_root if not provided.

        Returns:
            Dict suitable for JSON serialization
        """
        root = host_project_root or self.host_project_root
        if not root:
            raise ValueError("host_project_root must be set or provided")

        # Get base config from parent — includes mounts, masked, revealed, pushed_files
        base_dict = super().to_dict(root)

        result = {
            'version': __version__,
            'scope_name': self.scope_name,
            'dev_mode': self.dev_mode,
            'mirrored': self.mirrored,
            'show_hidden': self.show_hidden,
            'container_mode': self.container_mode,
            'init_source': self.init_source,
            'local': base_dict,
        }

        # Only include ports if configured
        if self.ports:
            result['ports'] = self.ports

        # Serialize container_root as relative ../traversal/mount_name
        if self.host_container_root and root:
            import os
            rel_hcr = os.path.relpath(
                str(self.host_container_root), str(root),
            ).replace('\\', '/')
            mount_name = self.container_root.lstrip('/')
            result['container_root'] = f"{rel_hcr}/{mount_name}"
        elif self.container_root != DEFAULT_CONTAINER_ROOT:
            result['container_root'] = self.container_root

        # Only include siblings if configured
        if self.siblings:
            result['siblings'] = [s.to_dict() for s in self.siblings]

        # Only include extensions if configured
        if self.extensions:
            result['extensions'] = [e.to_dict(root) for e in self.extensions]

        # container_files at top level (discovery artifact, not visibility config)
        if self.container_files:
            def to_relative(paths: set[Path]) -> list[str]:
                return [to_relative_posix(p, root) for p in sorted(paths)]
            result['container_files'] = to_relative(self.container_files)

        return result

    @classmethod
    def from_dict(cls, data: dict, host_project_root: Path) -> ScopeDockerConfig:
        """Create from dictionary with relative paths.

        Handles current v1 schema only. Legacy formats require manual patching.

        Args:
            data: Dict from JSON deserialization (with 'local' and top-level keys)
            host_project_root: Base path for absolute conversion

        Returns:
            ScopeDockerConfig instance
        """
        local_data = data.get('local', {})

        # Delegate path field parsing to LocalMountConfig
        base = LocalMountConfig.from_dict(local_data, host_project_root)

        # Parse container_files (discovery artifact, stays at top level)
        container_files = to_absolute_paths(data.get('container_files', []), host_project_root)

        # Parse siblings
        siblings = [SiblingMount.from_dict(sd) for sd in data.get('siblings', [])]

        # Parse extensions
        extensions = [
            ExtensionConfig.from_dict(ed, host_project_root)
            for ed in data.get('extensions', [])
        ]

        # Parse container_root — relative ../traversal/mount_name syntax (written by to_dict)
        cr_raw = data.get('container_root', '')
        if cr_raw.startswith('..'):
            last_slash = cr_raw.rfind('/')
            traversal = cr_raw[:last_slash]
            mount_name = cr_raw[last_slash + 1:]
            host_container_root = (host_project_root / traversal).resolve()
            container_root = f"/{mount_name}"
        else:
            # No container_root in JSON → derive defaults via __post_init__
            container_root = ''
            host_container_root = None

        return cls(
            mount_specs=base.mount_specs,
            pushed_files=base.pushed_files,
            mirrored=data.get('mirrored', True),
            container_files=container_files,
            scope_name=data.get('scope_name', ''),
            host_project_root=host_project_root,
            host_container_root=host_container_root,
            dev_mode=data.get('dev_mode', True),
            container_root=container_root,
            siblings=siblings,
            extensions=extensions,
            ports=data.get('ports', []),
            show_hidden=data.get('show_hidden', False),
            container_mode=data.get('container_mode', 'Hybrid'),
            init_source=data.get('init_source', 'cp'),
        )

    def track_extension(
        self,
        name: str,
        installer_class: str,
        isolation_paths: list[str],
        state: str = "installed",
    ) -> None:
        """Track an extension after successful deployment.

        Updates existing entry or creates new one. Single place for
        extension state management (DRY — called by CLI and GUI).

        Args:
            name: Extension name (e.g., "Claude Code")
            installer_class: Class name (e.g., "ClaudeInstaller")
            isolation_paths: Container paths needing isolation volumes
            state: Lifecycle state (default: "installed")
        """
        # Update existing entry if found
        for ext in self.extensions:
            if ext.installer_class == installer_class:
                ext.state = state
                ext.isolation_paths = isolation_paths
                return

        # Create new entry
        self.extensions.append(ExtensionConfig(
            name=name,
            installer_class=installer_class,
            isolation_paths=isolation_paths,
            state=state,
        ))

    def get_extension(self, installer_class: str) -> ExtensionConfig | None:
        """Find extension config by installer class name."""
        for ext in self.extensions:
            if ext.installer_class == installer_class:
                return ext
        return None

    def validate(self) -> list[str]:
        """Validate configuration consistency.

        Returns:
            List of error messages (empty if valid)
        """
        errors = super().validate()
        if self.host_container_root and self.host_project_root:
            try:
                if not self.host_project_root.is_relative_to(self.host_container_root):
                    errors.append("host_container_root must be ancestor of host_project_root")
            except (TypeError, ValueError):
                errors.append("host_container_root must be ancestor of host_project_root")
        if self.container_mode not in ("Hybrid", "Isolation"):
            errors.append(
                f"container_mode must be 'Hybrid' or 'Isolation', got {self.container_mode!r}"
            )
        if self.init_source not in ("cp", "clone"):
            errors.append(
                f"init_source must be 'cp' or 'clone', got {self.init_source!r}"
            )
        elif self.init_source == "clone":
            errors.append(
                "init_source='clone' is a Phase 3 feature; Phase 1 only supports 'cp'"
            )
        return errors

def get_igsc_root(host_project_root: Path) -> Path:
    """Get path to IgnoreScope config root (inside project).

    Structure: {project_root}/.ignore_scope/

    Args:
        host_project_root: Project root directory

    Returns:
        Path to in-project igsc directory
    """
    return host_project_root / IGSC_DIR_NAME


def get_container_dir(host_project_root: Path, scope_name: str) -> Path:
    """Get path to specific scope's config directory.

    Structure: {project_root}/.ignore_scope/{scope_name}/

    Args:
        host_project_root: Project root directory
        scope_name: Scope name (e.g., 'dev', 'prod')

    Returns:
        Path to scope config directory
    """
    return get_igsc_root(host_project_root) / scope_name


def get_llm_dir(host_project_root: Path, scope_name: str, llm_name: str = "claude") -> Path:
    """Get path to LLM config directory within a scope.

    Structure: {project_root}/.ignore_scope/{scope_name}/.llm/{llm_name}/

    Args:
        host_project_root: Project root directory
        scope_name: Scope name
        llm_name: LLM identifier (default: 'claude')

    Returns:
        Path to LLM config directory
    """
    return get_container_dir(host_project_root, scope_name) / ".llm" / llm_name


def _get_config_path(host_project_root: Path, scope_name: str) -> Path:
    """Get path to scope_docker_desktop.json configuration file.

    Structure: {project_root}/.ignore_scope/{scope_name}/scope_docker_desktop.json

    Args:
        host_project_root: Project root directory
        scope_name: Scope name

    Returns:
        Path to scope's scope_docker_desktop.json
    """
    return get_container_dir(host_project_root, scope_name) / CONFIG_FILENAME


def list_containers(host_project_root: Path) -> list[str]:
    """List all container names for a project.

    Args:
        host_project_root: Project root directory

    Returns:
        List of container names
    """
    igsc_root = get_igsc_root(host_project_root)
    if not igsc_root.exists():
        return []

    containers = []
    for item in igsc_root.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            containers.append(item.name)
    return sorted(containers)


def load_config(host_project_root: Path, scope_name: str) -> ScopeDockerConfig:
    """Load ScopeDockerConfig from scope_docker.json.

    Args:
        host_project_root: Project root directory
        scope_name: Scope name

    Returns:
        ScopeDockerConfig instance (empty if file doesn't exist)

    Raises:
        json.JSONDecodeError: If JSON is malformed
    """
    config_path = _get_config_path(host_project_root, scope_name)

    if not config_path.exists():
        config = ScopeDockerConfig(host_project_root=host_project_root)
        config.scope_name = scope_name
        return config

    try:
        data = json.loads(config_path.read_text(encoding='utf-8'))
        data = check_version_mismatch(data)
        config = ScopeDockerConfig.from_dict(data, host_project_root)
        # Ensure scope_name is set
        if not config.scope_name:
            config.scope_name = scope_name
        return config
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Failed to load config from {config_path}: {e}") from e


def save_config(config: ScopeDockerConfig) -> None:
    """Save ScopeDockerConfig to scope_docker.json.

    Args:
        config: ScopeDockerConfig instance to save

    Raises:
        ValueError: If host_project_root or scope_name is not set
    """
    if not config.host_project_root:
        raise ValueError("config.host_project_root must be set")
    if not config.scope_name:
        raise ValueError("config.scope_name must be set")

    config_path = _get_config_path(config.host_project_root, config.scope_name)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    config_dict = config.to_dict(config.host_project_root)
    config_path.write_text(json.dumps(config_dict, indent=2), encoding='utf-8')


def delete_scope_config(host_project_root: Path, scope_name: str) -> tuple[bool, str]:
    """Delete a scope's config directory.

    Removes the entire {scope_name}/ directory under .ignore_scope/.
    Does NOT affect the Docker container itself — only the local config files.

    Args:
        host_project_root: Project root directory
        scope_name: Scope/container name whose config to delete

    Returns:
        Tuple of (success, message)
    """
    import shutil

    config_dir = get_container_dir(host_project_root, scope_name)
    if not config_dir.exists():
        return False, f"No settings found for '{scope_name}'"

    try:
        shutil.rmtree(config_dir)
        return True, f"Settings for '{scope_name}' removed: {config_dir}"
    except Exception as e:
        return False, f"Failed to remove settings: {e}"
