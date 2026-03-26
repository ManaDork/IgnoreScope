"""Local mount configuration for container filesystem visibility.

This module defines the LocalMountConfig dataclass for managing what
the container can see at the Docker volume level.

Four-layer system:
  1. Mounts: Bind mounts that make host folders visible
  2. Masked: Named volumes that hide host folders from the container
  3. Revealed: Punch-through mounts that re-expose within masked areas
  4. Isolated: Named volumes that overlay everything with persistent container-owned content
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..utils.paths import is_descendant, to_absolute_paths, to_relative_posix


@dataclass
class LocalMountConfig:
    """Container filesystem configuration.

    Manages path sets and visibility flags:
      - mounts: Folders explicitly mounted (visible to container)
      - masked: Folders hidden by named mask volumes
      - revealed: Folders re-exposed within masked areas (punch-through)
      - pushed_files: Files pushed to container via docker cp
      - mirrored: Enable intermediate directory creation in masked areas

    All paths are stored as absolute Path objects internally.
    Serialization converts to relative paths for portability.
    """

    # Explicit mounts (bind mounts to host paths)
    mounts: set[Path] = field(default_factory=set)

    # Masked directories (hidden by named mask volumes)
    masked: set[Path] = field(default_factory=set)

    # Revealed directories (punch-through within masked areas)
    revealed: set[Path] = field(default_factory=set)

    # Files pushed to container via docker cp
    pushed_files: set[Path] = field(default_factory=set)

    # Enable mirrored intermediate directory creation in masked areas
    mirrored: bool = True

    # Lifecycle state for extension-managed configs
    # Values: "" (not managed), "deploy", "installed", "remove"
    state: str = ""

    def _is_descendant(self, path: Path, ancestor: Path) -> bool:
        """Check if path is a descendant of ancestor."""
        return is_descendant(path, ancestor)

    def is_mounted(self, path: Path) -> bool:
        """Check if path is mounted or under a mount."""
        if path in self.mounts:
            return True
        return any(self._is_descendant(path, m) for m in self.mounts)

    def is_masked(self, path: Path) -> bool:
        """Check if path is masked or under a masked directory."""
        if path in self.masked:
            return True
        return any(self._is_descendant(path, s) for s in self.masked)

    def is_revealed(self, path: Path) -> bool:
        """Check if path is revealed or under a revealed directory."""
        if path in self.revealed:
            return True
        return any(self._is_descendant(path, r) for r in self.revealed)

    def has_masked_ancestor(self, path: Path) -> bool:
        """Check if any ancestor of path is masked."""
        return any(self._is_descendant(path, s) for s in self.masked)

    def has_mount_ancestor(self, path: Path) -> bool:
        """Check if any ancestor of path is mounted."""
        return any(self._is_descendant(path, m) for m in self.mounts)

    # --- Mount operations ---

    def add_mount(self, path: Path) -> bool:
        """Add a mount point.

        Returns:
            True if added, False if already mounted
        """
        if path in self.mounts:
            return False
        self.mounts.add(path)
        return True

    def remove_mount(self, path: Path) -> bool:
        """Remove a mount point.

        Returns:
            True if removed, False if not mounted
        """
        if path not in self.mounts:
            return False
        self.mounts.discard(path)
        return True

    # --- Mask operations ---

    def add_mask(self, path: Path) -> bool:
        """Add a masked directory.

        Returns:
            True if added, False if already masked
        """
        if path in self.masked:
            return False
        self.masked.add(path)
        return True

    def remove_mask(self, path: Path) -> bool:
        """Remove a masked directory.

        Returns:
            True if removed, False if not masked
        """
        if path not in self.masked:
            return False
        self.masked.discard(path)
        return True

    # --- Reveal operations ---

    def add_reveal(self, path: Path) -> bool:
        """Add a revealed directory (punch-through).

        Returns:
            True if added, False if already revealed
        """
        if path in self.revealed:
            return False
        self.revealed.add(path)
        return True

    def remove_reveal(self, path: Path) -> bool:
        """Remove a revealed directory.

        Returns:
            True if removed, False if not revealed
        """
        if path not in self.revealed:
            return False
        self.revealed.discard(path)
        return True

    # --- Validation ---

    def validate(self) -> list[str]:
        """Validate configuration consistency.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Masked dirs must be under a mount
        for mask in self.masked:
            if not self.has_mount_ancestor(mask) and mask not in self.mounts:
                # Mask is on a mounted path (could be the mount itself)
                if not any(mask == m or self._is_descendant(mask, m) for m in self.mounts):
                    errors.append(f"Masked '{mask.name}' has no parent mount")

        # Revealed dirs must be under a masked dir
        for reveal in self.revealed:
            if not self.has_masked_ancestor(reveal):
                errors.append(f"Revealed '{reveal.name}' has no parent mask")

        return errors

    # --- Serialization ---

    def to_dict(self, host_project_root: Path) -> dict:
        """Convert to dictionary with relative paths.

        Args:
            host_project_root: Base path for relative conversion

        Returns:
            Dict suitable for JSON serialization
        """
        def to_relative(paths: set[Path]) -> list[str]:
            return [to_relative_posix(p, host_project_root) for p in sorted(paths)]

        result = {
            'mounts': to_relative(self.mounts),
            'masked': to_relative(self.masked),
            'revealed': to_relative(self.revealed),
        }
        if self.pushed_files:
            result['pushed_files'] = to_relative(self.pushed_files)
        if self.state:
            result['state'] = self.state
        return result

    @classmethod
    def from_dict(cls, data: dict, host_project_root: Path) -> 'LocalMountConfig':
        """Create from dictionary with relative paths.

        Args:
            data: Dict from JSON deserialization
            host_project_root: Base path for absolute conversion

        Returns:
            LocalMountConfig instance
        """
        return cls(
            mounts=to_absolute_paths(data.get('mounts', []), host_project_root),
            masked=to_absolute_paths(data.get('masked', []), host_project_root),
            revealed=to_absolute_paths(data.get('revealed', []), host_project_root),
            pushed_files=to_absolute_paths(data.get('pushed_files', []), host_project_root),
            state=data.get('state', ''),
        )

    def __bool__(self) -> bool:
        """Config is truthy if any paths are configured."""
        return bool(self.mounts or self.masked or self.revealed or self.pushed_files)

    def clear(self) -> None:
        """Clear all configuration."""
        self.mounts.clear()
        self.masked.clear()
        self.revealed.clear()
        self.pushed_files.clear()


@dataclass
class ExtensionConfig(LocalMountConfig):
    """Extension-managed mount configuration with isolation volume tracking.

    Extends LocalMountConfig with extension identity and isolation paths.
    Each installed extension creates one ExtensionConfig entry in
    ScopeDockerConfig.extensions.

    Isolation volumes are Layer 4 — named Docker volumes that overlay
    all other mounts with persistent, container-owned content.

    Lifecycle state (inherited from LocalMountConfig.state):
      "deploy"    — user requested install, pending execution
      "installed" — successfully deployed, binary verified
      "remove"    — user requested uninstall, pending execution
    """

    # Extension identity
    name: str = ""                  # Human-readable: "Claude Code", "Git", "P4 MCP Server"
    installer_class: str = ""       # Class name: "ClaudeInstaller", "GitInstaller", "P4McpInstaller"

    # Container paths needing persistent isolation volumes (Layer 4)
    isolation_paths: list[str] = field(default_factory=list)

    # How isolation volumes are initialized: "empty" or "clone" (from host)
    seed_method: str = "empty"

    def to_dict(self, host_project_root: Path) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = super().to_dict(host_project_root)
        result['name'] = self.name
        result['installer_class'] = self.installer_class
        if self.isolation_paths:
            result['isolation_paths'] = self.isolation_paths
        if self.seed_method != "empty":
            result['seed_method'] = self.seed_method
        return result

    @classmethod
    def from_dict(cls, data: dict, host_project_root: Path) -> 'ExtensionConfig':
        """Create from dictionary with relative paths."""
        base = LocalMountConfig.from_dict(data, host_project_root)
        return cls(
            mounts=base.mounts,
            masked=base.masked,
            revealed=base.revealed,
            pushed_files=base.pushed_files,
            state=base.state,
            name=data.get('name', ''),
            installer_class=data.get('installer_class', ''),
            isolation_paths=data.get('isolation_paths', []),
            seed_method=data.get('seed_method', 'empty'),
        )
