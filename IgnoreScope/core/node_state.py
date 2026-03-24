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
        visibility: Aggregate state — "visible"|"masked"|"mirrored"|"revealed"|"hidden"|"orphaned"|"container_only"
        has_pushed_descendant: Any descendant has pushed=True (folders only)
        has_direct_visible_child: Immediate child has revealed=True or pushed=True (folders only)
    """

    mounted: bool = False
    masked: bool = False
    revealed: bool = False
    pushed: bool = False
    container_orphaned: bool = False
    container_only: bool = False
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


def has_revealed_descendant(
    path: Path,
    states: dict[Path, NodeState],
) -> bool:
    """Check if any descendant path has revealed=True in the states dict.

    Used by Stage 2 visibility to detect mirrored directories.
    """
    for state_path, state in states.items():
        if state.revealed and state_path != path:
            if is_descendant(state_path, path):
                return True
    return False


def find_mirrored_paths(
    states: dict[Path, NodeState],
) -> set[Path]:
    """Identify paths whose visibility should be upgraded to 'mirrored'.

    MatrixState truth table (per-node):

        visibility    has_showable_descendant  →  upgrade?
        ──────────    ──────────────────────   ─  ────────
        "hidden"      True                        YES → "mirrored"
        "masked"      True                        YES → "mirrored"
        otherwise     *                           NO

    A "showable descendant" is any descendant path with:
        visibility in ("visible", "revealed") OR pushed == True

    Returns:
        Set of paths whose visibility should be upgraded to "mirrored"
    """
    mirrored = set()
    for path, state in states.items():
        if state.visibility not in ("hidden", "masked"):
            continue
        if _has_showable_descendant(path, states):
            mirrored.add(path)
    return mirrored


def _has_showable_descendant(
    path: Path,
    states: dict[Path, NodeState],
) -> bool:
    """Check if any descendant is showable (visible, revealed, or pushed)."""
    for desc_path, desc_state in states.items():
        if desc_path == path:
            continue
        if not is_descendant(desc_path, path):
            continue
        if desc_state.visibility in ("visible", "revealed") or desc_state.pushed:
            return True
    return False


def find_paths_with_pushed_descendants(
    states: dict[Path, NodeState],
) -> set[Path]:
    """Identify paths that have any descendant with pushed=True.

    Used to distinguish FOLDER_MOUNTED_MASKED (no pushed content)
    from FOLDER_MOUNTED_MASKED_PUSHED (has pushed content inside).

    Returns:
        Set of ancestor paths that have at least one pushed descendant.
    """
    pushed_paths = {p for p, s in states.items() if s.pushed}
    if not pushed_paths:
        return set()
    result = set()
    for path in states:
        if path in pushed_paths:
            continue
        for pp in pushed_paths:
            if is_descendant(pp, path):
                result.add(path)
                break
    return result


def find_paths_with_direct_visible_children(
    states: dict[Path, NodeState],
) -> set[Path]:
    """Identify paths whose immediate children include revealed or pushed nodes.

    Used to distinguish FOLDER_MASKED_REVEALED (direct parent of visible content)
    from FOLDER_MASKED_MIRRORED (structural intermediate only).

    An "immediate child" is a path whose parent directory equals the candidate path.

    Returns:
        Set of paths that have at least one direct visible child.
    """
    result = set()
    for path in states:
        for child_path, child_state in states.items():
            if child_path.parent == path and (child_state.revealed or child_state.pushed):
                result.add(path)
                break
    return result


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
    mounts: set[Path],
    masked: set[Path],
    revealed: set[Path],
    pushed_files: set[Path],
) -> NodeState:
    """Compute the full NodeState for a single path.

    Pure function — examines path against all config sets to determine
    each boolean flag, then derives aggregate visibility.

    Tree-context fields (has_pushed_descendant, has_direct_visible_child)
    are NOT set here — they require batch context. See apply_node_states_from_scope().

    Args:
        path: The path to evaluate
        mounts: Active bind mount paths
        masked: Active mask volume paths
        revealed: Active punch-through paths
        pushed_files: Files currently pushed to the container

    Returns:
        NodeState with per-node fields computed
    """
    is_mounted = path in mounts or any(
        is_descendant(path, m) for m in mounts
    )
    is_masked = path in masked or any(
        is_descendant(path, m) for m in masked
    )
    is_revealed = (
        path in revealed or any(is_descendant(path, r) for r in revealed)
    ) and is_masked
    is_pushed = path in pushed_files

    # Container orphan check — explicit 4-condition matrix:
    #   pushed  masked  mounted  revealed  ->  container_orphaned
    #     T       T       F        F           T  (stranded in mask volume)
    #   all other combinations                 F
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
        visibility=vis,
    )


def apply_node_states_from_scope(
    config: 'ScopeDockerConfig',
    paths: Iterable[Path],
) -> dict[Path, NodeState]:
    """Batch-compute NodeState for every path given a ScopeDockerConfig.

    This is the COREFLOWCHART Phase 3 prescribed function:
    ApplyNodeStateFromScope().

    Stage 1: Per-node MatrixState (5 values)
    Stage 2: Tree-aware mirrored detection (when config.mirrored=True)
    Stage 3: Tree-context folder fields (has_pushed_descendant, has_direct_visible_child)

    Args:
        config: Full container configuration (mounts, masked, revealed, pushed_files)
        paths: Iterable of paths to evaluate

    Returns:
        Mapping from each path to its computed NodeState
    """
    from dataclasses import replace

    # Stage 1: per-node computation
    states = {
        p: compute_node_state(
            path=p,
            mounts=config.mounts,
            masked=config.masked,
            revealed=config.revealed,
            pushed_files=config.pushed_files,
        )
        for p in paths
    }

    # Stage 2: mirrored detection (requires tree context)
    if getattr(config, 'mirrored', True):
        for mp in find_mirrored_paths(states):
            states[mp] = replace(states[mp], visibility="mirrored")

    # Stage 3: tree-context folder fields
    for path in find_paths_with_pushed_descendants(states):
        states[path] = replace(states[path], has_pushed_descendant=True)
    for path in find_paths_with_direct_visible_children(states):
        states[path] = replace(states[path], has_direct_visible_child=True)

    return states
