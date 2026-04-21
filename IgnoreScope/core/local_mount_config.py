"""Local mount configuration for container filesystem visibility.

This module defines the LocalMountConfig dataclass for managing what
the container can see at the Docker volume level.

Mount-centric architecture:
  Each MountSpecPath represents a bind mount root with ordered gitignore-style
  patterns controlling which subdirectories are masked or unmasked.

  Pattern syntax (gitignore native):
    "vendor/"            - mask (deny) the vendor directory
    "!vendor/public/"    - unmask (exception) vendor/public
    "vendor/public/tmp/" - re-mask vendor/public/tmp

  Docker volume mapping:
    Non-negated pattern -> named mask volume (Layer 2)
    Negated (!) pattern -> bind mount punch-through (Layer 3)
    Pattern order = volume declaration order (last-writer-wins)

  Layer 4 (Isolation) is handled by ExtensionConfig.isolation_paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from ..utils.paths import is_descendant, to_absolute_paths, to_relative_posix
from .mount_spec_path import MountSpecPath


@dataclass
class LocalMountConfig:
    """Container filesystem configuration.

    Manages mount specifications and visibility:
      - mount_specs: List of MountSpecPath, each a bind mount with mask/unmask patterns
      - pushed_files: Files pushed to container via docker cp
      - mirrored: Enable intermediate directory creation in masked areas

    Backward-compatible properties (mounts, masked, revealed) are computed
    from mount_specs for downstream consumers during transition.
    """

    # Mount specifications — each is a bind mount root with patterns
    mount_specs: list[MountSpecPath] = field(default_factory=list)

    # Files pushed to container via docker cp
    pushed_files: set[Path] = field(default_factory=set)

    # Enable mirrored intermediate directory creation in masked areas
    mirrored: bool = True

    # Lifecycle state for extension-managed configs
    # Values: "" (not managed), "deploy", "installed", "remove"
    state: str = ""

    # --- Backward-compatible computed properties ---

    @property
    def mounts(self) -> set[Path]:
        """Set of all mount roots (backward compat)."""
        return {ms.mount_root for ms in self.mount_specs}

    @property
    def masked(self) -> set[Path]:
        """Union of all masked paths across all mount specs (backward compat)."""
        result: set[Path] = set()
        for ms in self.mount_specs:
            result.update(ms.get_masked_paths())
        return result

    @property
    def revealed(self) -> set[Path]:
        """Union of all revealed paths across all mount specs (backward compat)."""
        result: set[Path] = set()
        for ms in self.mount_specs:
            result.update(ms.get_revealed_paths())
        return result

    # --- Mount spec lookup ---

    def _find_spec_for_path(self, path: Path) -> MountSpecPath | None:
        """Find the mount spec whose root contains this path."""
        for ms in self.mount_specs:
            if path == ms.mount_root or is_descendant(path, ms.mount_root):
                return ms
        return None

    # --- Descendant queries ---

    def has_pushed_descendant(self, path: Path) -> bool:
        """Check if any pushed file exists under this path.

        Scans pushed_files set by path containment — no tree walk.

        Args:
            path: Absolute path to check.

        Returns:
            True if any pushed file is a strict descendant of this path.
        """
        for pf in self.pushed_files:
            if pf != path and is_descendant(pf, path):
                return True
        return False

    # --- Mount operations ---

    def add_mount(self, path: Path) -> bool:
        """Add a mount point (creates new MountSpecPath with empty patterns).

        Hard-blocks if path overlaps with existing mount roots.

        Returns:
            True if added, False if already mounted or overlap detected.
        """
        return self._add_mount_with_delivery(path, delivery="bind")

    def add_detached_mount(self, path: Path) -> bool:
        """Add a detached mount point (UX: "Virtual Mount").

        Creates a MountSpecPath with delivery="detached". Content is delivered
        via docker cp at container create time; no host live-link. Overlap
        rules are identical to add_mount — the two delivery modes share one
        mount_specs namespace.

        Returns:
            True if added, False if already mounted or overlap detected.
        """
        return self._add_mount_with_delivery(path, delivery="detached")

    def _add_mount_with_delivery(
        self,
        path: Path,
        delivery: Literal["bind", "detached"],
    ) -> bool:
        """Shared add_mount / add_detached_mount body — overlap guard + append.

        Both gestures originate from LocalHost (host-backed) so host_path mirrors
        mount_root; content_seed defaults to "tree" (Phase 1 behavior).
        """
        if any(ms.mount_root == path for ms in self.mount_specs):
            return False
        for ms in self.mount_specs:
            if is_descendant(path, ms.mount_root) or is_descendant(ms.mount_root, path):
                return False
        self.mount_specs.append(
            MountSpecPath(mount_root=path, delivery=delivery, host_path=path)
        )
        return True

    def add_stencil_folder(
        self,
        container_path: Path,
        *,
        preserve_on_update: bool = False,
    ) -> bool:
        """Add a container-only folder spec (UX: "Make Folder" / "Make Permanent Folder → No Recreate").

        Creates a MountSpecPath with ``delivery="detached"``, ``content_seed="folder"``,
        and ``host_path=None`` — the folder lives only in the container and is
        mkdir'd at container create. ``preserve_on_update=True`` flips it to
        the "No Recreate" soft-permanent variant.

        Returns:
            True if added, False if already mounted or overlap detected.
        """
        return self._add_stencil_spec(
            container_path,
            delivery="detached",
            content_seed="folder",
            preserve_on_update=preserve_on_update,
        )

    def add_stencil_volume(self, container_path: Path) -> bool:
        """Add a container-only named-volume spec (UX: "Make Permanent Folder → Volume Mount").

        Creates a MountSpecPath with ``delivery="volume"``, ``content_seed="folder"``,
        and ``host_path=None``. A Docker named volume will be emitted in compose;
        contents survive ordinary ``docker compose up`` and are destroyed only
        via explicit ``docker compose down -v``.

        Returns:
            True if added, False if already mounted or overlap detected.
        """
        return self._add_stencil_spec(
            container_path,
            delivery="volume",
            content_seed="folder",
            preserve_on_update=False,
        )

    def _add_stencil_spec(
        self,
        container_path: Path,
        *,
        delivery: Literal["detached", "volume"],
        content_seed: Literal["tree", "folder"],
        preserve_on_update: bool,
    ) -> bool:
        """Shared body for container-only constructors (host_path=None)."""
        if any(ms.mount_root == container_path for ms in self.mount_specs):
            return False
        for ms in self.mount_specs:
            if is_descendant(container_path, ms.mount_root) or is_descendant(
                ms.mount_root, container_path
            ):
                return False
        self.mount_specs.append(
            MountSpecPath(
                mount_root=container_path,
                delivery=delivery,
                host_path=None,
                content_seed=content_seed,
                preserve_on_update=preserve_on_update,
            )
        )
        return True

    def mark_permanent(self, path: Path) -> bool:
        """Flip preserve_on_update False→True on the detached-folder spec at ``path``.

        No-op (returns False) if no exact-match spec, if already permanent, or
        if the spec is not ``delivery="detached"`` + ``content_seed="folder"``.
        """
        for ms in self.mount_specs:
            if ms.mount_root != path:
                continue
            if ms.preserve_on_update:
                return False
            if ms.delivery != "detached" or ms.content_seed != "folder":
                return False
            ms.preserve_on_update = True
            return True
        return False

    def unmark_permanent(self, path: Path) -> bool:
        """Flip preserve_on_update True→False on the spec at ``path``.

        No-op (returns False) if no exact-match spec or flag already False.
        """
        for ms in self.mount_specs:
            if ms.mount_root != path:
                continue
            if not ms.preserve_on_update:
                return False
            ms.preserve_on_update = False
            return True
        return False

    def is_detached_mounted(self, path: Path) -> bool:
        """True iff path is the mount_root of a delivery="detached" spec.

        UX term: "Virtual Mount". Does not match descendants or bind-delivered
        mount_roots — the gesture state machine only cares about exact-match
        at mount_root boundaries.
        """
        for ms in self.mount_specs:
            if ms.mount_root == path and ms.delivery == "detached":
                return True
        return False

    def convert_delivery(
        self,
        path: Path,
        target: Literal["bind", "detached"],
    ) -> bool:
        """Flip delivery on the spec whose mount_root is ``path``.

        No-op (returns False) if no exact-match spec is found or delivery
        already matches target. Caller triggers recreate pipeline — this
        method mutates config only.

        Returns:
            True if delivery flipped, False if already at target or no match.
        """
        for ms in self.mount_specs:
            if ms.mount_root == path:
                if ms.delivery == target:
                    return False
                ms.delivery = target
                return True
        return False

    def remove_but_keep_children(self, path: Path) -> bool:
        """Replace a parent mount spec with N explicit child specs.

        Enumerates immediate host-filesystem children of ``path``, creates
        one new MountSpecPath per child (inheriting delivery + a subset of
        the parent's patterns where the pattern falls under the child), and
        removes the parent entry. Patterns that do not fall under any child
        are dropped.

        Use case: user mounts a parent folder, then wants finer-grained
        per-child tracking without retyping each child's mount.

        Returns:
            True if the parent was replaced, False if no matching mount
            spec or the host path has no enumerable children.
        """
        parent = None
        for ms in self.mount_specs:
            if ms.mount_root == path:
                parent = ms
                break
        if parent is None:
            return False
        if not path.is_dir():
            return False

        try:
            children = sorted(
                c for c in path.iterdir() if c.is_dir()
            )
        except OSError:
            return False
        if not children:
            return False

        new_specs: list[MountSpecPath] = []
        for child in children:
            child_rel = str(child.relative_to(parent.mount_root)).replace("\\", "/") + "/"
            child_patterns: list[str] = []
            for pat in parent.patterns:
                stripped = pat.lstrip("!")
                if stripped.startswith(child_rel) or stripped == child_rel.rstrip("/") + "/":
                    # Rewrite pattern to be relative to the new child mount_root.
                    prefix = "!" if pat.startswith("!") else ""
                    suffix = stripped[len(child_rel):]
                    if suffix:
                        child_patterns.append(f"{prefix}{suffix}")
            new_specs.append(
                MountSpecPath(
                    mount_root=child,
                    patterns=child_patterns,
                    delivery=parent.delivery,
                )
            )

        idx = self.mount_specs.index(parent)
        self.mount_specs.pop(idx)
        for offset, ns in enumerate(new_specs):
            self.mount_specs.insert(idx + offset, ns)
        return True

    # --- Mask operations (delegate to mount spec) ---

    def add_mask(self, path: Path) -> bool:
        """Add a masked directory (appends deny pattern to owning mount spec).

        Returns:
            True if added, False if already masked or no owning mount found.
        """
        ms = self._find_spec_for_path(path)
        if ms is None:
            return False
        rel = str(path.relative_to(ms.mount_root)).replace("\\", "/")
        pattern = f"{rel}/"
        return ms.add_pattern(pattern)

    # --- Reveal operations (delegate to mount spec) ---

    def add_reveal(self, path: Path) -> bool:
        """Add a revealed directory (appends exception pattern to owning mount spec).

        Returns:
            True if added, False if already revealed or no owning mount found.
        """
        ms = self._find_spec_for_path(path)
        if ms is None:
            return False
        rel = str(path.relative_to(ms.mount_root)).replace("\\", "/")
        pattern = f"!{rel}/"
        return ms.add_pattern(pattern)

    # --- Validation ---

    def validate(self) -> list[str]:
        """Validate configuration consistency.

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check mount overlap
        errors.extend(MountSpecPath.validate_no_overlap(self.mount_specs))

        # Validate each mount spec's patterns
        for ms in self.mount_specs:
            spec_errors = ms.validate()
            for err in spec_errors:
                errors.append(f"Mount '{ms.mount_root.name}': {err}")

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

        result: dict = {
            'mount_specs': [ms.to_dict(host_project_root) for ms in self.mount_specs],
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
        mount_specs = [
            MountSpecPath.from_dict(ms_data, host_project_root)
            for ms_data in data.get('mount_specs', [])
        ]
        return cls(
            mount_specs=mount_specs,
            pushed_files=to_absolute_paths(data.get('pushed_files', []), host_project_root),
            state=data.get('state', ''),
        )

    def __bool__(self) -> bool:
        """Config is truthy if any mount specs or pushed files are configured."""
        return bool(self.mount_specs or self.pushed_files)

    def clear(self) -> None:
        """Clear all configuration."""
        self.mount_specs.clear()
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
            mount_specs=base.mount_specs,
            pushed_files=base.pushed_files,
            state=base.state,
            name=data.get('name', ''),
            installer_class=data.get('installer_class', ''),
            isolation_paths=data.get('isolation_paths', []),
            seed_method=data.get('seed_method', 'empty'),
        )
