# Technical Design — Pathspec-Native State Computation

## Overview

Replace the tree-walk-based Stages 2+3 in `apply_node_states_from_scope()` with config-level queries that derive descendant information directly from pattern strings and pushed file paths. Eliminate GUI duplicate Stage 2 logic. Review Stage 1 for consolidation.

## Architecture

### Current Pipeline (3 stages)

```
Stage 1: Per-node MatrixState
  compute_node_state() → pathspec eval → (mounted, masked, revealed, pushed, visibility)
  
Stage 2: Tree walk for virtual
  find_mirrored_paths() → walk UP from showable paths → upgrade masked/hidden → "virtual"
  
Stage 3: Tree walk for descendant flags  
  find_paths_with_pushed_descendants() → walk UP from pushed paths
  find_paths_with_direct_visible_children() → collect parents of revealed/pushed [BUG: misses virtual]
```

### Target Pipeline (config-native)

```
Stage 1: Per-node MatrixState (reviewed for consolidation)
  compute_node_state() → pathspec eval → (mounted, masked, revealed, pushed, visibility)

Stage 2: Config-native virtual detection (no tree walks)
  FOR EACH path with visibility in ("masked", "hidden"):
    Check 1 (within-mount):  owning_spec.has_exception_descendant(path)
    Check 2 (any path):      config.has_pushed_descendant(path)
    Check 3 (above-mount):   any mount_root is descendant of path
    IF any check true → visibility = "virtual"

Stage 3: Config-native descendant flags (no tree walks)
  FOR EACH path:
    has_pushed_descendant = config.has_pushed_descendant(path)
    has_direct_visible_child = derived from states pass (see below)
```

### Stage 2b — Above-Mount Structural Paths (from MIRRORED_ALGORITHM.md)

Paths between project root and mount boundary get visibility="hidden" in Stage 1.
The current pipeline upgrades them to "virtual" via tree walk in `find_mirrored_paths()`.

**Config-native replacement:** Check 3 asks "is any mount_root a descendant of this path?"
Mount roots always get visibility="visible" in Stage 1, so any hidden ancestor above a
mount should become virtual to show the structural path down to visible content.

This check is O(mount_specs) per path — config-native, no tree walk.

**GUI path inclusion unchanged:** `compute_mirrored_intermediate_paths()` is still needed
to add structural intermediate paths to `all_paths` (they must exist in the states dict
to be evaluated). The refactor eliminates tree walks for virtual *detection*, not path
*collection*.

### has_direct_visible_child — Preserved Check, Corrected Understanding

The check uses Stage 1 flags (`s.revealed or s.pushed`), NOT visibility. Virtual children
are structural intermediates and must NOT propagate this flag — otherwise the F5/F6
distinction collapses (every virtual ancestor becomes FOLDER_VIRTUAL_REVEALED).

The original TODO described this as a bug, but testing confirmed the existing behavior
is correct: `has_direct_visible_child` means "immediate child has revealed=True or pushed=True."
Virtual children don't qualify because they are structural, not content-bearing.

The function still runs after Stage 2 for correct sequencing, but the predicate is unchanged.

## Dependencies

### Internal

| Module | Dependency | Type |
|--------|-----------|------|
| `core/mount_spec_path.py` | Pattern list structure | **Add** `has_exception_descendant()` |
| `core/local_mount_config.py` | `pushed_files` set | **Add** `has_pushed_descendant()` |
| `core/node_state.py` | Stages 2+3 functions | **Modify** pipeline orchestration |
| `gui/mount_data_tree.py` | `_recompute_states()` | **Simplify** — remove independent Stage 2 |
| `gui/export_structure.py` | `_has_revealed_descendant()`, `_get_effective_visibility()` | **Eliminate** — use CORE state |
| `core/hierarchy.py` | `compute_mirrored_intermediate_paths()` | **Evaluate** — may still be needed for compose |

### External

None — all changes are internal to the state pipeline. Docker Engine, Perforce, GitHub unaffected.

### Ordering

1. Add config query methods first (MountSpecPath, LocalMountConfig)
2. Refactor node_state.py pipeline
3. Eliminate GUI duplicates (depends on CORE refactor being correct)

## Key Changes

### New Methods

**`MountSpecPath.has_exception_descendant(path: Path) -> bool`** — per-path query
```python
def has_exception_descendant(self, path: Path) -> bool:
    """Check if any exception pattern exists under this path.
    
    Scans pattern strings directly — no tree walk, no filesystem access.
    Complexity: O(patterns) per call.
    """
    rel = self._to_relative(path)
    if rel is None:
        return False
    rel_prefix = rel.rstrip("/")
    for pattern in self.patterns:
        if pattern.startswith("!"):
            exc_folder = pattern[1:].rstrip("/")
            if exc_folder.startswith(rel_prefix + "/"):
                return True
    return False
```

**`MountSpecPath.get_virtual_paths() -> set[Path]`** — inverse pattern derivation (cross-reference)
```python
def get_virtual_paths(self) -> set[Path]:
    """Derive virtual paths from pattern structure (inverse pathspec).
    
    For each exception pattern, walks UP to its covering deny pattern.
    All intermediate paths between deny and exception are virtual.
    
    Used as cross-reference against config-query virtual detection.
    Discrepancies indicate malformed patterns or detection bugs.
    
    Complexity: O(patterns x pattern_depth), computed once per spec.
    """
    virtual = set()
    for pattern in self.patterns:
        if not pattern.startswith("!"):
            continue
        exc = pattern[1:].rstrip("/")
        parts = exc.split("/")
        for i in range(len(parts) - 1, 0, -1):
            ancestor = "/".join(parts[:i])
            if f"{ancestor}/" in self.patterns:
                for j in range(i, len(parts)):
                    mid = "/".join(parts[:j])
                    virtual.add(self.mount_root / mid)
                break
    return virtual
```

**`LocalMountConfig.has_pushed_descendant(path: Path) -> bool`**
```python
def has_pushed_descendant(self, path: Path) -> bool:
    """Check if any pushed file exists under this path.
    
    Scans pushed_files set by path prefix — no tree walk.
    Complexity: O(pushed_files) per call.
    """
    for pf in self.pushed_files:
        if pf != path and is_descendant(pf, path):
            return True
    return False
```

### Virtual Detection: Dual Computation + Discrepancy Logging

The refactored Stage 2 runs TWO independent virtual detection methods:

1. **Config queries** (primary) — Checks 1/2/3 per path
2. **Inverse pattern derivation** (cross-reference) — `get_virtual_paths()` pre-computed

After both run, compare results and log discrepancies:
- Path marked virtual by queries but NOT by inverse → likely above-mount path (expected) or pushed-only virtual
- Path marked virtual by inverse but NOT by queries → potential bug in query logic or path not in states dict
- Both agree → high confidence

Discrepancy logging catches malformed patterns (exception without proper deny coverage) and
detection bugs during the transition period. Can be removed once stable.

### Modified Files

| File | Change |
|------|--------|
| `core/mount_spec_path.py` | Add `has_exception_descendant()`, `get_virtual_paths()` |
| `core/local_mount_config.py` | Add `has_pushed_descendant()` |
| `core/node_state.py` | Refactor `apply_node_states_from_scope()` — replace `find_mirrored_paths()` with config queries, fix `find_paths_with_direct_visible_children()` sequencing, replace `find_paths_with_pushed_descendants()` with config query |
| `gui/mount_data_tree.py` | Remove `compute_mirrored_intermediate_paths()` call from `_recompute_states()` |
| `gui/export_structure.py` | Remove `_has_revealed_descendant()`, `_get_effective_visibility()` — use CORE NodeState |

### Functions to Remove/Deprecate

| Function | File | Replacement |
|----------|------|-------------|
| `find_mirrored_paths()` | `core/node_state.py` | Config-native virtual detection in pipeline |
| `has_revealed_descendant()` | `core/node_state.py` | `MountSpecPath.has_exception_descendant()` |
| `find_paths_with_pushed_descendants()` | `core/node_state.py` | `LocalMountConfig.has_pushed_descendant()` |
| `_has_revealed_descendant()` | `gui/export_structure.py` | CORE NodeState |
| `_get_effective_visibility()` | `gui/export_structure.py` | CORE NodeState |

### Functions to Keep (reviewed)

| Function | File | Reason |
|----------|------|--------|
| `compute_visibility()` | `core/node_state.py` | Stage 1 MatrixState — already correct |
| `compute_node_state()` | `core/node_state.py` | Stage 1 per-node — review for consolidation |
| `find_paths_with_direct_visible_children()` | `core/node_state.py` | Keep but fix sequencing (run after virtual assignment) |
| `find_container_orphaned_paths()` | `core/node_state.py` | Unrelated to Stages 2+3 |
| `detect_orphan_creating_removals()` | `core/node_state.py` | Unrelated to Stages 2+3 |

## Complexity Analysis

### Current

- Stage 2 `find_mirrored_paths()`: O(showable_count x tree_depth)
- Stage 3 `find_paths_with_pushed_descendants()`: O(pushed_count x tree_depth)
- Stage 3 `find_paths_with_direct_visible_children()`: O(n) — already efficient but sequencing bug

### Target

- Virtual detection: O(paths x patterns) — for each masked/hidden path, scan patterns
- Pushed descendant: O(paths x pushed_files) — for each path, scan pushed set
- Direct visible child: O(n) — single pass after virtual assignment (sequencing fixed)

**Trade-off:** Pattern scan is O(paths x patterns) vs tree walk O(paths x depth). For typical projects (hundreds of paths, tens of patterns), both are fast. Pattern scan has better locality and no tree structure dependency.

## Alternatives Considered

### 1. Fix Stage 3 Bug Only
Quick fix: add `or s.visibility == "virtual"` to `find_paths_with_direct_visible_children()`. Rejected because it perpetuates the tree-walk architecture and doesn't address the root cause (stage sequencing and unnecessary tree dependency).

### 2. Pre-index Pattern Prefixes
Build a prefix trie from patterns for O(depth) descendant lookups instead of O(patterns). Deferred — premature optimization for typical pattern counts (<50).

### 3. Keep Tree Walks, Fix Sequencing Only
Move Stage 3 after Stage 2 to fix the bug. Rejected — doesn't achieve the "zero tree walks" goal or eliminate GUI duplicates.

## Risks

1. **GUI `_recompute_states()` has other callers of mirrored intermediates.** Mitigated by: audit GUI usage of `compute_mirrored_intermediate_paths()` before elimination (per user decision).
2. **`hierarchy.compute_mirrored_intermediate_paths()` used by container_ops for mkdir.** Mitigated by: evaluate whether compose/container_ops consumers can switch to new config queries. If not, keep hierarchy function for that specific use case.
3. **Pattern scan complexity.** Mitigated by: O(paths x patterns) is acceptable for typical sizes. If patterns grow large, prefix trie optimization is a known next step.

## Architecture Doc Impact

| Document | Section | Change |
|----------|---------|--------|
| `COREFLOWCHART.md` | Phase 3 pipeline description | Update Stage 2+3 descriptions to config-native |
| `COREFLOWCHART.md` | Rule 1 | Remove "GUI retains independent copy" caveat |
| `ARCHITECTUREGLOSSARY.md` | `visibility` → Implementation status | Update Stage 2 description |
| `ARCHITECTUREGLOSSARY.md` | `NodeState` | Update Stage 3 source description |
| `MIRRORED_ALGORITHM.md` | Full document | Review — may need significant update or replacement |