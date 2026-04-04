# STATE_REFACTOR — Pathspec-Native Visibility Computation

## Status: TODO

## Problem

The 3-stage visibility pipeline (Stage 1: per-node flags, Stage 2: tree walk for virtual, Stage 3: tree walk for descendant flags) has gaps:

1. **Stage 3 doesn't see Stage 2 results:** `find_paths_with_direct_visible_children()` checks `s.revealed or s.pushed` but not `s.visibility == "virtual"`. A virtual child (upgraded by Stage 2) doesn't propagate to its parent's `has_direct_visible_child` flag.

2. **Descendant info requires tree walks:** Two O(n) passes walk ancestor chains to compute `has_pushed_descendant` and `has_direct_visible_child`. These could be answered directly from the pattern list.

## Proposed Fix

### Immediate (targeted)

Add `has_exception_descendant(path)` to `MountSpecPath`:
```python
def has_exception_descendant(self, path: Path) -> bool:
    """Check if any exception pattern exists under this path."""
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

Use in Stage 3 or directly in `compute_node_state()` to set descendant flags without tree walks.

### Larger Refactor (future)

Replace the 3-stage pipeline with pathspec-native computation:
- Stage 1: Keep — `compute_node_state()` already uses pathspec for masked/revealed
- Stage 2: Replace tree walk with pattern scan — `has_exception_descendant()` answers "should this be virtual?" directly
- Stage 3: Replace tree walk with pattern scan — descendant flags derived from pattern structure

Benefits:
- No tree walks needed (O(paths × patterns) instead of O(paths × depth))
- Pattern list is the single source of truth — no flag propagation bugs
- Simpler code — fewer stages, fewer intermediate states

### Stage 3 Bug (has_direct_visible_child)

`find_paths_with_direct_visible_children()` at `core/node_state.py:243-246`:
```python
# Current:
if s.revealed or s.pushed

# Should also include:
if s.revealed or s.pushed or s.visibility == "virtual"
```

This is the immediate fix for "folder nodes not showing revealed descendant info." Virtual children should propagate upward the same as revealed children.

## Files Affected

- `core/mount_spec_path.py` — add `has_exception_descendant()`
- `core/node_state.py` — fix Stage 3 `find_paths_with_direct_visible_children()`, potentially replace Stages 2+3
- `gui/display_config.py` — truth table may need new entries for pattern-derived descendant states

## Dependencies

- MountSpecPath pattern list is the source of truth
- `has_exception_descendant()` works on pattern strings, no filesystem access needed
- Pushed files are NOT in mount_specs (separate `pushed_files` set) — pushed descendant detection still needs the existing tree walk or a separate mechanism
