"""Consolidated container hierarchy logic.

Single source of truth for all container visibility computation.
Consumers: compose.py, file_ops.py, validation, future UI.

Volume generation follows pattern order within each MountSpecPath:
  For each mount: bind mount root, then interleaved mask/reveal per pattern.
  Docker applies volumes in declaration order (last-writer-wins).
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
    from .mount_spec_path import MountSpecPath


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
    hierarchy, computed from mount_specs and pushed files.

    Attributes:
        ordered_volumes: Layer 1-3 + sibling volume entries (project content) for docker-compose.yml
        mask_volume_names: Named mask volumes for compose volumes section
        isolation_volume_entries: Layer 4 volume entries (container-owned, delivery-mode-independent)
        isolation_volume_names: Named isolation volumes for compose volumes section (Layer 4)
        revealed_parents: Container paths needing mkdir -p before docker cp (pushed files)
        validation_errors: Configuration problems found during computation
        visible_paths: All visible container paths (for UI/debugging)
        masked_paths: All hidden container paths (for UI/debugging)
    """

    # For docker-compose.yml generation — Layer 1-3 + siblings (bind-delivery
    # project content only; detached-delivery specs emit nothing here).
    # L4 isolation entries live in isolation_volume_entries and are emitted
    # regardless of any spec's delivery.
    ordered_volumes: list[str] = field(default_factory=list)

    # Named mask volumes declared in docker-compose.yml volumes section
    mask_volume_names: list[str] = field(default_factory=list)

    # Layer 4 volume entries (e.g. "iso_foo_root_local:/root/.local")
    isolation_volume_entries: list[str] = field(default_factory=list)

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
      ceiling=None  -> per-mask ceiling (walks up to each reveal's mask, exclusive)
      ceiling=Path  -> fixed ceiling (exclusive), walks above mount boundary

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
    mount_specs: list['MountSpecPath'],
    container_root: str,
    host_container_root: Path,
) -> tuple[list[str], list[str], set[str], set[str]]:
    """Compute ordered volume entries from mount_specs in pattern order.

    For each mount_spec with ``delivery == "bind"``:
      1. Bind mount for mount_root (Layer 1)
      2. For each pattern in order:
         - Non-negated: named mask volume (Layer 2)
         - Negated (!): bind mount punch-through (Layer 3)

    For each mount_spec with ``delivery == "detached"``:
      - No Docker volume emitted. Content reaches the container via
        ``docker cp`` at lifecycle-init time (see ``_detached_init`` in
        ``container_lifecycle.py``). Masks become post-cp ``rm -rf``.
        Reveals are included in the cp walk.

    Docker applies volumes in declaration order (last-writer-wins),
    so pattern order = correct nested layering.

    The ``visible_paths`` / ``masked_paths`` sets are populated for ALL
    specs regardless of delivery — they describe container-side state
    for UI consumption, not Docker volume layout.

    Args:
        mount_specs: List of MountSpecPath with ordered patterns
        container_root: Container root path (e.g., '/{HCR.name}')
        host_container_root: Host container root path (relative_to base)

    Returns:
        Tuple of (volume_entries, mask_volume_names, visible_paths, masked_paths)
    """
    entries = []
    mask_names = []
    visible = set()
    hidden = set()
    seen_names: set[str] = set()

    for ms in mount_specs:
        emit_volumes = (ms.delivery == "bind")

        # Layer 1: Bind mount for mount_root (bind delivery only).
        cpath = to_container_path(ms.mount_root, container_root, host_container_root)
        if emit_volumes:
            entries.append(f"{ms.mount_root.as_posix()}:{cpath}")
        visible.add(cpath)

        # Interleaved layers: iterate patterns in order
        for pattern in ms.patterns:
            is_exception = pattern.startswith("!")
            folder = pattern.lstrip("!").rstrip("/")
            # Strip trailing glob suffixes — Docker volumes use folder paths
            if folder.endswith("/**"):
                folder = folder[:-3]
            elif folder.endswith("/*"):
                folder = folder[:-2]
            if not folder:
                continue
            abs_path = ms.mount_root / folder
            cpath = to_container_path(abs_path, container_root, host_container_root)

            if is_exception:
                # Reveal: bind punch-through for bind delivery; included in cp
                # walk for detached delivery.
                if emit_volumes:
                    entries.append(f"{abs_path.as_posix()}:{cpath}")
                visible.add(cpath)
            else:
                # Mask: named volume for bind delivery; post-cp rm for detached.
                if emit_volumes:
                    rel_path = to_relative_posix_or_name(abs_path, host_container_root)
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

    return entries, mask_names, visible, hidden


def _validate_hierarchy(
    mount_specs: list['MountSpecPath'],
    host_container_root: Path | None = None,
) -> list[str]:
    """Validate hierarchy configuration.

    Delegates pattern validation to MountSpecPath.validate() and overlap
    checking to MountSpecPath.validate_no_overlap(). Adds host_container_root
    boundary check.

    Args:
        mount_specs: List of MountSpecPath to validate
        host_container_root: When provided, all mount roots must be under this root.

    Returns:
        List of validation error messages
    """
    from .mount_spec_path import MountSpecPath as MSP

    errors = []

    # Mount overlap check
    errors.extend(MSP.validate_no_overlap(mount_specs))

    # Per-mount pattern validation
    for ms in mount_specs:
        for err in ms.validate():
            errors.append(f"Mount '{ms.mount_root.name}': {err}")

    # All mount roots must be under host_container_root (when provided)
    if host_container_root is not None:
        for ms in mount_specs:
            try:
                ms.mount_root.relative_to(host_container_root)
            except ValueError:
                errors.append(
                    f"Mount '{ms.mount_root.name}' is not under host container root"
                )

    return errors


def _process_root(
    container_root: str,
    mount_specs: list['MountSpecPath'],
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
    errors = _validate_hierarchy(mount_specs, host_container_root)

    vol_entries, mask_names, visible, hidden = _compute_volume_entries(
        mount_specs, container_root, host_container_root,
    )

    # Extract flat sets for revealed_parents and mirrored_parents
    # (these functions operate on sets, not mount_specs)
    masked_set: set[Path] = set()
    revealed_set: set[Path] = set()
    mounts_set: set[Path] = set()
    for ms in mount_specs:
        mounts_set.add(ms.mount_root)
        masked_set.update(ms.get_masked_paths())
        revealed_set.update(ms.get_revealed_paths())

    exc_parents = _compute_revealed_parents(
        pushed_files, masked_set, container_root, host_container_root,
    )

    if mirrored:
        mirrored_parents = _compute_mirrored_parents(
            masked_set, revealed_set, mounts_set, container_root, host_container_root,
        )
        exc_parents.update(mirrored_parents)

    return vol_entries, mask_names, visible, hidden, exc_parents, errors


def compute_container_hierarchy(
    container_root: str,
    mount_specs: list['MountSpecPath'],
    pushed_files: set[Path],
    host_project_root: Path,
    host_container_root: Path | None = None,
    siblings: list['SiblingMount'] | None = None,
    mirrored: bool = True,
    isolation_paths: list[tuple[str, str]] | None = None,
) -> ContainerHierarchy:
    """Compute complete container hierarchy from configuration.

    Single function computing ALL hierarchy logic. Used by:
    - compose.py: uses ordered_volumes, mask_volume_names, isolation_volume_entries, isolation_volume_names
    - validation: checks validation_errors
    - file_ops.py: uses revealed_parents
    - Future UI: uses visible_paths, masked_paths

    Args:
        container_root: Container root path (e.g., '/{HCR.name}')
        mount_specs: List of MountSpecPath with ordered patterns
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
        container_root, mount_specs, pushed_files,
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
                sibling.container_path, sibling.mount_specs, sibling.pushed_files,
                sibling.host_path, mirrored,
            )
            hierarchy.ordered_volumes.extend(s_vols)
            hierarchy.mask_volume_names.extend(s_masks)
            hierarchy.visible_paths.update(s_vis)
            hierarchy.masked_paths.update(s_hid)
            hierarchy.revealed_parents.update(s_parents)
            # Prefix sibling errors with sibling path
            for err in s_errs:
                hierarchy.validation_errors.append(f"[{sibling.container_path}] {err}")

    # Layer 4: Isolation volumes (persistent, container-owned, final overlay).
    # Kept separate from ordered_volumes because L4 is emitted regardless of
    # any spec's delivery — ordered_volumes carries only bind-delivery content.
    if isolation_paths:
        for ext_name, container_path in isolation_paths:
            vol_name = f"iso_{sanitize_volume_name(ext_name)}_{sanitize_volume_name(container_path.strip('/').replace('/', '_'))}"
            hierarchy.isolation_volume_entries.append(f"{vol_name}:{container_path}")
            hierarchy.isolation_volume_names.append(vol_name)

    return hierarchy
