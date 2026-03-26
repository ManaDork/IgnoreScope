"""Consolidated container hierarchy logic.

Single source of truth for all container visibility computation.
Consumers: compose.py, file_ops.py, validation, future UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ..utils.paths import is_descendant, to_relative_posix_or_name
from ..utils.strings import sanitize_volume_name
from .config import get_container_path

if TYPE_CHECKING:
    from .config import SiblingMount


def to_container_path(
    host_path: Path, container_root: str, host_container_root: Path,
) -> str:
    """Convert host path to container-side path via path formula.

    Uses to_relative_posix_or_name which falls back to .name on ValueError
    (unreachable for valid configs — validated upstream by _validate_hierarchy).

    Normalizes container_root (strips trailing slash) and handles rel=="."
    (path equals root) to prevent double-slash or trailing-dot artifacts.
    """
    container_root = container_root.rstrip('/')
    rel = to_relative_posix_or_name(host_path, host_container_root)
    if rel == '.':
        return container_root
    return get_container_path(container_root, rel)


@dataclass
class ContainerHierarchy:
    """Computed container visibility state.

    This dataclass represents the fully resolved container filesystem
    hierarchy, computed from mounts, masked, revealed, and pushed files.

    Attributes:
        ordered_volumes: Volume entries in correct layering order for docker-compose.yml
        mask_volume_names: Named mask volumes for compose volumes section
        isolation_volume_names: Named isolation volumes for compose volumes section (Layer 4)
        revealed_parents: Container paths needing mkdir -p before docker cp (pushed files)
        validation_errors: Configuration problems found during computation
        visible_paths: All visible container paths (for UI/debugging)
        masked_paths: All hidden container paths (for UI/debugging)
    """

    # For docker-compose.yml generation
    ordered_volumes: list[str] = field(default_factory=list)

    # Named mask volumes declared in docker-compose.yml volumes section
    mask_volume_names: list[str] = field(default_factory=list)

    # Named isolation volumes declared in docker-compose.yml volumes section (Layer 4)
    isolation_volume_names: list[str] = field(default_factory=list)

    # For mkdir -p before pushing revealed/pushed files
    revealed_parents: set[str] = field(default_factory=set)

    # Configuration validation errors
    validation_errors: list[str] = field(default_factory=list)

    # For UI consumption / debugging
    visible_paths: set[str] = field(default_factory=set)
    masked_paths: set[str] = field(default_factory=set)


def _compute_revealed_parents(
    pushed_files: set[Path],
    masked: set[Path],
    container_root: str,
    host_container_root: Path,
) -> set[str]:
    """Compute container paths needing mkdir -p for pushed files.

    Only creates directories for pushed files that are within masked volumes.
    Docker handles directory creation for bind mounts and revealed dirs automatically.

    Args:
        pushed_files: Set of absolute paths to pushed files
        masked: Set of absolute paths to masked directories
        container_root: Container root path (e.g., '/{HCR.name}')
        host_container_root: Host container root path (relative_to base)

    Returns:
        Set of container directory paths needing creation (POSIX format)
    """
    parents = set()

    for exc_file in pushed_files:
        # Check if this pushed file is within a masked dir
        in_masked = any(is_descendant(exc_file, m) for m in masked)
        if not in_masked:
            continue

        # Get container path and its parent directory
        container_path = to_container_path(exc_file, container_root, host_container_root)
        from pathlib import PurePosixPath
        parent_dir = str(PurePosixPath(container_path).parent)

        if parent_dir and parent_dir != container_root and parent_dir != '/':
            parents.add(parent_dir)

    return parents


def _walk_mirrored_intermediates(
    masked: set[Path],
    revealed: set[Path],
    mounts: set[Path],
    ceiling: Path | None = None,
) -> set[Path]:
    """Walk ancestor directories between reveals and their ceiling boundary.

    Unified walk logic for mirrored intermediate computation.
    Two ceiling modes:
      ceiling=None  → per-mask ceiling (walks up to each reveal's mask, exclusive)
      ceiling=Path  → fixed ceiling (exclusive), walks above mount boundary

    Two walk loops:
      1. Reveal-to-ceiling (mask-to-reveal intermediates)
      2. Mount-parent-to-ceiling (structural ancestors, GUI mode only)

    Args:
        masked: Active mask volume paths
        revealed: Active punch-through paths
        mounts: Active bind mount paths
        ceiling: Fixed ceiling path (exclusive). None uses per-mask ceiling.

    Returns:
        Set of host paths that are mirrored intermediates.
    """
    result: set[Path] = set()

    # Walk 1: Reveal-to-ceiling (existing)
    for reveal in revealed:
        for mask in masked:
            if not is_descendant(reveal, mask):
                continue
            # Verify mask is under a mount (valid config)
            if not any(mask == m or is_descendant(mask, m) for m in mounts):
                continue
            # Walk from reveal.parent up to effective ceiling (exclusive)
            effective_ceiling = ceiling if ceiling is not None else mask
            current = reveal.parent
            while current != effective_ceiling and is_descendant(current, effective_ceiling):
                result.add(current)
                current = current.parent
            break  # Found the mask for this reveal

    # Walk 2: Mount parents to ceiling (structural ancestors of bind mounts).
    # Only in GUI-ceiling mode — container mkdir-p doesn't need mount parents
    # because Docker auto-creates bind mount targets.
    if ceiling is not None:
        for mount in mounts:
            current = mount.parent
            while current != ceiling and is_descendant(current, ceiling):
                result.add(current)
                current = current.parent

    return result


def _compute_mirrored_parents(
    masked: set[Path],
    revealed: set[Path],
    mounts: set[Path],
    container_root: str,
    host_container_root: Path,
) -> set[str]:
    """Compute container paths for mirrored intermediate directories.

    When mirrored is enabled, ancestor directories between each mask
    and its revealed descendants need mkdir -p to mirror the host's
    directory structure. Delegates to _walk_mirrored_intermediates
    with per-mask ceiling (ceiling=None).
    """
    host_paths = _walk_mirrored_intermediates(masked, revealed, mounts)
    return {to_container_path(p, container_root, host_container_root) for p in host_paths}


def compute_mirrored_intermediate_paths(
    masked: set[Path],
    revealed: set[Path],
    mounts: set[Path],
    ceiling: Path | None = None,
) -> set[Path]:
    """Host paths for mirrored intermediate directories.

    When mirrored is enabled, ancestor directories between each mask
    and its revealed descendants are mirrored intermediates.

    Args:
        masked: Active mask volume paths
        revealed: Active punch-through paths
        mounts: Active bind mount paths
        ceiling: Optional fixed ceiling (exclusive). None uses per-mask ceiling.

    Returns:
        Set of host paths that are mirrored intermediates.
    """
    return _walk_mirrored_intermediates(
        masked, revealed, mounts, ceiling=ceiling,
    )


def _compute_volume_entries(
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    container_root: str,
    host_container_root: Path,
) -> tuple[list[str], list[str], set[str], set[str]]:
    """Compute ordered volume entries and visibility in a single pass.

    Volume order is CRITICAL for layering:
      1. Base mounts (bind mounts to host paths)
      2. Masked volumes (named volumes that hide directories)
      3. Revealed mounts (re-expose specific folders within masked areas)

    Also computes visibility sets (visible/masked container paths) as a
    side-effect — both iterate the same mounts/masked/revealed sets.

    Args:
        mounts: Set of absolute paths to mount
        masked: Set of absolute paths to mask (hide)
        revealed: Set of absolute paths to reveal (punch-through)
        container_root: Container root path (e.g., '/{HCR.name}')
        host_container_root: Host container root path (relative_to base)

    Returns:
        Tuple of (volume_entries, mask_volume_names, visible_paths, masked_paths)
    """
    entries = []
    mask_names = []
    visible = set()
    hidden = set()

    # Layer 1: Base mounts
    for mount in sorted(mounts):
        cpath = to_container_path(mount, container_root, host_container_root)
        entries.append(f"{mount.as_posix()}:{cpath}")
        visible.add(cpath)

    # Layer 2: Masked volumes (named volumes that hide bind-mounted content)
    # sorted() ensures determinism: first alphabetically gets clean name,
    # collisions get _2, _3, etc.
    seen_names: set[str] = set()
    for mask in sorted(masked):
        cpath = to_container_path(mask, container_root, host_container_root)
        rel_path = to_relative_posix_or_name(mask, host_container_root)
        base_name = f"mask_{sanitize_volume_name(rel_path.replace('/', '_'))}"
        vol_name = base_name
        counter = 2
        while vol_name in seen_names:
            vol_name = f"{base_name}_{counter}"
            counter += 1
        seen_names.add(vol_name)
        mask_names.append(vol_name)
        entries.append(f"{vol_name}:{cpath}")
        hidden.add(cpath)

    # Layer 3: Revealed (punch-through bind mounts)
    for reveal in sorted(revealed):
        cpath = to_container_path(reveal, container_root, host_container_root)
        entries.append(f"{reveal.as_posix()}:{cpath}")
        visible.add(cpath)

    return entries, mask_names, visible, hidden


def _validate_hierarchy(
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    host_container_root: Path | None = None,
) -> list[str]:
    """Validate hierarchy configuration.

    Args:
        mounts: Set of mount paths
        masked: Set of masked paths
        revealed: Set of revealed paths
        host_container_root: When provided, all paths must be under this root.
            Catches the condition that inline ValueError handlers were trying to handle.

    Returns:
        List of validation error messages
    """
    errors = []

    # All paths must be under host_container_root (when provided)
    if host_container_root is not None:
        for label, paths in [("Mount", mounts), ("Masked", masked), ("Revealed", revealed)]:
            for p in paths:
                try:
                    p.relative_to(host_container_root)
                except ValueError:
                    errors.append(f"{label} '{p.name}' is not under host container root")

    # Masked dirs must be under a mount
    for mask in masked:
        has_mount_parent = any(
            mask == m or is_descendant(mask, m) for m in mounts
        )
        if not has_mount_parent:
            errors.append(f"Masked '{mask.name}' has no parent mount")

    # Revealed dirs must be under a masked dir
    for reveal in revealed:
        has_masked_parent = any(is_descendant(reveal, m) for m in masked)
        if not has_masked_parent:
            errors.append(f"Revealed '{reveal.name}' has no parent mask")

    return errors


def _process_root(
    container_root: str,
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    pushed_files: set[Path],
    host_container_root: Path,
    mirrored: bool,
) -> tuple[list[str], list[str], set[str], set[str], set[str], list[str]]:
    """Process one root through validate -> volumes -> revealed_parents -> mirrored.

    Shared logic for both primary and sibling roots.

    Returns:
        Tuple of (volume_entries, mask_volume_names, visible_paths,
                  masked_paths, revealed_parents, validation_errors)
    """
    errors = _validate_hierarchy(mounts, masked, revealed, host_container_root)

    vol_entries, mask_names, visible, hidden = _compute_volume_entries(
        mounts, masked, revealed, container_root, host_container_root,
    )

    exc_parents = _compute_revealed_parents(
        pushed_files, masked, container_root, host_container_root,
    )

    if mirrored:
        mirrored_parents = _compute_mirrored_parents(
            masked, revealed, mounts, container_root, host_container_root,
        )
        exc_parents.update(mirrored_parents)

    return vol_entries, mask_names, visible, hidden, exc_parents, errors


def compute_container_hierarchy(
    container_root: str,
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    pushed_files: set[Path],
    host_project_root: Path,
    host_container_root: Path | None = None,
    siblings: list[SiblingMount] | None = None,
    mirrored: bool = True,
    isolation_paths: list[tuple[str, str]] | None = None,
) -> ContainerHierarchy:
    """Compute complete container hierarchy from configuration.

    Single function computing ALL hierarchy logic. Used by:
    - compose.py: uses ordered_volumes, mask_volume_names, isolation_volume_names
    - validation: checks validation_errors
    - file_ops.py: uses revealed_parents
    - Future UI: uses visible_paths, masked_paths

    Args:
        container_root: Container root path (e.g., '/{HCR.name}')
        mounts: Set of absolute paths to mount
        masked: Set of absolute paths to mask (hide)
        revealed: Set of absolute paths to reveal (punch-through)
        pushed_files: Set of absolute paths to pushed files
        host_project_root: Host project root path
        host_container_root: Host container root (relative_to base). Defaults to host_project_root.parent
        siblings: Optional list of sibling mounts for external directories
        mirrored: Enable intermediate directory creation in masked areas
        isolation_paths: Optional list of (extension_name, container_path) tuples for Layer 4 volumes

    Returns:
        ContainerHierarchy with all computed values
    """
    if host_container_root is None:
        host_container_root = host_project_root.parent

    hierarchy = ContainerHierarchy()

    # Primary root
    vols, masks, vis, hid, parents, errs = _process_root(
        container_root, mounts, masked, revealed, pushed_files,
        host_container_root, mirrored,
    )
    hierarchy.ordered_volumes = vols
    hierarchy.mask_volume_names = list(masks)
    hierarchy.visible_paths = vis
    hierarchy.masked_paths = hid
    hierarchy.revealed_parents = parents
    hierarchy.validation_errors = errs

    # Siblings
    if siblings:
        for sibling in siblings:
            s_vols, s_masks, s_vis, s_hid, s_parents, s_errs = _process_root(
                sibling.container_path, sibling.mounts, sibling.masked,
                sibling.revealed, sibling.pushed_files, sibling.host_path, mirrored,
            )
            hierarchy.ordered_volumes.extend(s_vols)
            hierarchy.mask_volume_names.extend(s_masks)
            hierarchy.visible_paths.update(s_vis)
            hierarchy.masked_paths.update(s_hid)
            hierarchy.revealed_parents.update(s_parents)
            # Prefix sibling errors with sibling path
            for err in s_errs:
                hierarchy.validation_errors.append(f"[{sibling.container_path}] {err}")

    # Layer 4: Isolation volumes (persistent, container-owned, final overlay)
    if isolation_paths:
        for ext_name, container_path in isolation_paths:
            vol_name = f"iso_{sanitize_volume_name(ext_name)}_{sanitize_volume_name(container_path.strip('/').replace('/', '_'))}"
            hierarchy.ordered_volumes.append(f"{vol_name}:{container_path}")
            hierarchy.isolation_volume_names.append(vol_name)

    return hierarchy
