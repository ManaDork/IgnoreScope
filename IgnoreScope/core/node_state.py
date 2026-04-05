"""Per-node state model for container filesystem visibility.

Defines the canonical NodeState dataclass and pure functions for
computing per-node visibility from mount/mask/reveal/push configuration.

This module is the CORE owner of per-node state (COREFLOWCHART Phase 3).
All functions are pure — no GUI imports, no side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from ..utils.paths import is_descendant

if TYPE_CHECKING:
    from .config import ScopeDockerConfig
    from .mount_spec_path import MountSpecPath


def compute_visibility(
    mounted: bool,
    masked: bool,
    revealed: bool,
    pushed: bool,
    container_orphaned: bool,
    container_only: bool = False,
) -> str:
    """Derive aggregate visibility from per-node boolean flags.

    MatrixState truth table (first match wins):

        container_orphaned  revealed  masked  mounted  container_only  ->  visibility
        ------------------  --------  ------  -------  --------------  |   ----------
              T               *         *       *            *         |   "orphaned"
              F               T         *       *            *         |   "revealed"
              F               F         T       T            *         |   "masked"
              F               F         F       T            *         |   "visible"
              *               F         F       F            T         |   "container_only"
              F               F         *       F            F         |   "hidden"

    Note: masked requires mounted=T to produce "masked" visibility.
    When masked=T but mounted=F (stale config), falls through to "hidden".
    container_only is lowest priority — overridden by any host config flag.

    Args:
        mounted: Node is under a bind mount
        masked: Node is hidden by a mask volume
        revealed: Node is a punch-through within a masked area
        pushed: Node has been pushed via docker cp
        container_orphaned: Node exists in mask volume but has no parent mount
        container_only: Node exists in container but not on host (scan diff)

    Returns:
        One of: "orphaned", "revealed", "masked", "visible", "container_only", "hidden"
    """
    if container_orphaned:
        return "orphaned"
    if revealed:
        return "revealed"
    if masked and mounted:
        return "masked"
    if mounted:
        return "visible"
    if container_only and not masked:
        return "container_only"
    return "hidden"


@dataclass(frozen=True)
class NodeState:
    """Per-node state describing container filesystem visibility.

    Frozen dataclass — instances are immutable after creation.
    The visibility field is an aggregate derived from the boolean flags.

    Attributes:
        mounted: Node is under a bind mount
        masked: Node is hidden by a mask volume
        revealed: Node is a punch-through within a masked area
        pushed: Node has been pushed via docker cp
        container_orphaned: Pushed file stranded in mask volume, mount removed (TTFF matrix)
        container_only: Exists in container but not on host (scan diff discovered)
        is_mount_root: Node IS a mount root declaration
        has_mount_masks: Mount root whose spec has deny patterns (content masked)
        visibility: Aggregate state — "visible"|"masked"|"virtual"|"revealed"|"hidden"|"orphaned"|"container_only"
        has_pushed_descendant: Any descendant has pushed=True (folders only)
        has_direct_visible_child: Immediate child has revealed=True or pushed=True (folders only)
    """

    mounted: bool = False
    masked: bool = False
    revealed: bool = False
    pushed: bool = False
    container_orphaned: bool = False
    container_only: bool = False
    is_mount_root: bool = False
    has_mount_masks: bool = False
    visibility: str = "hidden"
    has_pushed_descendant: bool = False
    has_direct_visible_child: bool = False


def find_container_orphaned_paths(
    pushed_files: set[Path],
    mounts: set[Path],
    masked: set[Path],
) -> set[Path]:
    """Identify pushed files whose parent mount no longer exists.

    A pushed file is container-orphaned when:
    - It is under a masked directory, AND
    - No active mount covers it

    Args:
        pushed_files: Files currently in the container (pushed via docker cp)
        mounts: Active bind mount paths
        masked: Active mask volume paths

    Returns:
        Set of paths that are container-orphaned
    """
    orphaned = set()
    for pf in pushed_files:
        under_mask = any(
            pf == m or is_descendant(pf, m) for m in masked
        )
        if not under_mask:
            continue
        under_mount = any(
            pf == m or is_descendant(pf, m) for m in mounts
        )
        if not under_mount:
            orphaned.add(pf)
    return orphaned




def find_paths_with_direct_visible_children(
    states: dict[Path, NodeState],
) -> set[Path]:
    """Identify paths whose immediate children include revealed or pushed nodes.

    Used to distinguish FOLDER_VIRTUAL_REVEALED (direct parent of visible content)
    from FOLDER_VIRTUAL (structural intermediate only).

    Checks Stage 1 flags (revealed, pushed) — NOT visibility. Virtual children
    are structural intermediates and should NOT propagate this flag, otherwise
    the F5/F6 distinction collapses (all virtual ancestors become F5).

    Algorithm: Single pass — collect parents of revealed/pushed nodes.
    Complexity: O(n).

    Returns:
        Set of paths that have at least one direct visible child.
    """
    return {
        p.parent for p, s in states.items()
        if s.revealed or s.pushed
    } & set(states.keys())


def detect_orphan_creating_removals(
    pushed_files: set[Path],
    current_mounts: set[Path],
    current_masked: set[Path],
    removing_mounts: set[Path],
) -> set[Path]:
    """Detect pushed files that would become container-orphaned by mount removal.

    Call before executing a mount removal to check if any pushed files
    would be stranded. Returns the set of files that would transition to
    container-orphaned state.

    Args:
        pushed_files: Currently pushed files
        current_mounts: Current mount set (before removal)
        current_masked: Current mask set
        removing_mounts: Mounts being removed

    Returns:
        Set of pushed file paths that would become container-orphaned
    """
    if not pushed_files or not removing_mounts:
        return set()

    proposed_mounts = current_mounts - removing_mounts

    would_orphan = set()
    for pf in pushed_files:
        under_mask = any(pf == m or is_descendant(pf, m) for m in current_masked)
        if not under_mask:
            continue
        # Currently has mount coverage?
        has_current_mount = any(
            pf == m or is_descendant(pf, m) for m in current_mounts
        )
        if not has_current_mount:
            continue  # Already orphaned
        # Would lose mount coverage?
        has_proposed_mount = any(
            pf == m or is_descendant(pf, m) for m in proposed_mounts
        )
        if not has_proposed_mount:
            would_orphan.add(pf)

    return would_orphan


def compute_node_state(
    path: Path,
    mount_specs: list['MountSpecPath'],
    pushed_files: set[Path],
) -> NodeState:
    """Compute per-node state using pathspec evaluation (last-match-wins).

    Evaluates gitignore-style patterns in order via MountSpecPath,
    enabling nested mask/reveal layering (mask → reveal → re-mask).

    Args:
        path: The path to evaluate
        mount_specs: List of MountSpecPath with ordered patterns
        pushed_files: Files currently pushed to the container

    Returns:
        NodeState with per-node fields computed via pathspec
    """
    is_mounted = False
    is_masked = False
    is_revealed = False
    is_mount_root = False
    has_mount_masks = False

    for ms in mount_specs:
        if path == ms.mount_root or is_descendant(path, ms.mount_root):
            is_mounted = True
            is_mount_root = (path == ms.mount_root)
            has_mount_masks = is_mount_root and any(
                not p.startswith("!") for p in ms.patterns
            )
            is_masked = ms.is_masked(path)
            is_revealed = ms.is_unmasked(path)
            break  # path belongs to first matching mount

    is_pushed = path in pushed_files

    is_container_orphaned = (
        is_pushed and is_masked and not is_mounted and not is_revealed
    )

    vis = compute_visibility(
        mounted=is_mounted,
        masked=is_masked,
        revealed=is_revealed,
        pushed=is_pushed,
        container_orphaned=is_container_orphaned,
    )

    return NodeState(
        mounted=is_mounted,
        masked=is_masked,
        revealed=is_revealed,
        pushed=is_pushed,
        container_orphaned=is_container_orphaned,
        is_mount_root=is_mount_root,
        has_mount_masks=has_mount_masks,
        visibility=vis,
    )


def _find_owning_spec(
    path: Path,
    mount_specs: list['MountSpecPath'],
) -> 'MountSpecPath | None':
    """Find the mount spec whose root contains this path."""
    for ms in mount_specs:
        if path == ms.mount_root or is_descendant(path, ms.mount_root):
            return ms
    return None


def _compute_virtual_paths_from_config(
    states: dict[Path, NodeState],
    config: 'ScopeDockerConfig',
) -> set[Path]:
    """Config-native virtual detection (no tree walks).

    For each masked/hidden path, checks three conditions:
      Check 1 (within-mount): owning spec has exception descendant
      Check 2 (any path):     config has pushed file descendant
      Check 3 (above-mount):  any mount_root is a descendant of this path

    Returns:
        Set of paths whose visibility should be upgraded to "virtual".
    """
    virtual: set[Path] = set()
    for path, state in states.items():
        if state.visibility not in ("masked", "hidden"):
            continue

        # Check 1: owning spec has exception pattern below this path
        owning_spec = _find_owning_spec(path, config.mount_specs)
        if owning_spec and owning_spec.has_exception_descendant(path):
            virtual.add(path)
            continue

        # Check 2: pushed file exists below this path
        if config.has_pushed_descendant(path):
            virtual.add(path)
            continue

        # Check 3: mount root below this path (above-mount structural paths)
        # Mount roots get visibility="visible" in Stage 1, so any hidden
        # ancestor above a mount should become virtual.
        if state.visibility == "hidden":
            for ms in config.mount_specs:
                if ms.mount_root != path and is_descendant(ms.mount_root, path):
                    virtual.add(path)
                    break

    return virtual


def _cross_reference_virtual(
    query_virtual: set[Path],
    config: 'ScopeDockerConfig',
    states: dict[Path, NodeState],
) -> None:
    """Cross-reference config-query virtual results against inverse pattern derivation.

    Logs discrepancies between the two independent methods. Expected differences:
      - Above-mount paths: in query_virtual but not inverse (inverse only covers within-mount)
      - Pushed-only virtual: in query_virtual but not inverse (inverse only covers patterns)

    Unexpected differences indicate malformed patterns or detection bugs.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Collect inverse-derived virtual paths from all mount specs
    inverse_virtual: set[Path] = set()
    for ms in config.mount_specs:
        inverse_virtual.update(ms.get_virtual_paths())

    # Filter inverse to only paths in states dict (inverse may produce paths not in scope)
    inverse_in_scope = inverse_virtual & set(states.keys())

    # Paths in inverse but not in query result — potential detection bug
    missed_by_query = inverse_in_scope - query_virtual
    for path in missed_by_query:
        st = states.get(path)
        if st and st.visibility in ("masked", "hidden"):
            logger.warning(
                "Virtual cross-ref: path %s is virtual by inverse pattern derivation "
                "but NOT by config query (vis=%s). Possible detection bug.",
                path, st.visibility,
            )

    # Paths in query but not in inverse — expected for above-mount and pushed-only
    extra_in_query = query_virtual - inverse_in_scope
    for path in extra_in_query:
        st = states.get(path)
        if st and st.visibility == "masked":
            # Masked path virtual by query but not inverse — pushed-only or detection gap
            logger.debug(
                "Virtual cross-ref: path %s virtual by query but not inverse (pushed descendant).",
                path,
            )


def apply_node_states_from_scope(
    config: 'ScopeDockerConfig',
    paths: Iterable[Path],
) -> dict[Path, NodeState]:
    """Batch-compute NodeState for every path given a ScopeDockerConfig.

    This is the COREFLOWCHART Phase 3 prescribed function:
    ApplyNodeStateFromScope().

    Stage 1: Per-node MatrixState (5 values)
    Stage 2: Config-native virtual detection (when config.mirrored=True)
    Stage 3: Descendant folder fields (has_pushed_descendant, has_direct_visible_child)

    Args:
        config: Full container configuration (mounts, masked, revealed, pushed_files)
        paths: Iterable of paths to evaluate

    Returns:
        Mapping from each path to its computed NodeState
    """
    from dataclasses import replace

    # Stage 1: per-node computation via pathspec
    states = {
        p: compute_node_state(
            path=p,
            mount_specs=config.mount_specs,
            pushed_files=config.pushed_files,
        )
        for p in paths
    }

    # Stage 2: config-native virtual detection (no tree walks)
    # Upgrades masked/hidden paths that have revealed or pushed descendants
    if getattr(config, 'mirrored', True):
        virtual_paths = _compute_virtual_paths_from_config(states, config)
        _cross_reference_virtual(virtual_paths, config, states)
        for vp in virtual_paths:
            states[vp] = replace(states[vp], visibility="virtual")

    # Stage 3: descendant folder fields
    # has_pushed_descendant via config query (no tree walk)
    for path in states:
        if config.has_pushed_descendant(path):
            states[path] = replace(states[path], has_pushed_descendant=True)

    # has_direct_visible_child — runs AFTER virtual assignment
    # so virtual children propagate to their parents
    for path in find_paths_with_direct_visible_children(states):
        states[path] = replace(states[path], has_direct_visible_child=True)

    return states
