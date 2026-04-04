# Pathspec-Native State Computation

## Problem Statement

The 3-stage visibility pipeline in `core/node_state.py` uses tree walks (ancestor chain traversals) for Stages 2 and 3. This creates:

1. **Stage 3 bug:** `find_paths_with_direct_visible_children()` checks `s.revealed or s.pushed` but not `s.visibility == "virtual"`. Virtual children (upgraded by Stage 2) don't propagate `has_direct_visible_child` to parents. Result: parents of virtual folders get `FOLDER_VIRTUAL` instead of `FOLDER_VIRTUAL_REVEALED`.

2. **Unnecessary tree walks:** Stages 2 and 3 walk ancestor chains to compute `virtual` visibility, `has_pushed_descendant`, and `has_direct_visible_child`. These could be answered directly from pattern structure and config data.

3. **Duplicated logic:** GUI maintains independent Stage 2 copies:
   - `gui/mount_data_tree.py:237-255` — calls `hierarchy.compute_mirrored_intermediate_paths()` before CORE's `apply_node_states_from_scope()`
   - `gui/export_structure.py:49-78` — independent `_has_revealed_descendant()` + `_get_effective_visibility()`

## Success Criteria

**Primary:** Zero tree walks for state computation. All visibility and descendant flags derived from config-level pattern/path queries.

- `has_exception_descendant(path)` on `MountSpecPath` replaces tree walk for virtual detection
- `has_pushed_descendant(path)` on `LocalMountConfig` replaces tree walk for pushed ancestor detection
- `has_direct_visible_child(path)` derived from config queries, not tree iteration
- GUI duplicate Stage 2 logic eliminated — CORE is single authority for virtual visibility
- Stage 3 bug resolved (subsumed by refactor)

## User Stories

1. As a developer maintaining the state pipeline, I want visibility to derive from pattern structure so that flag propagation bugs (like the Stage 3 virtual gap) are structurally impossible.
2. As a user with deeply nested mask/reveal structures, I want correct `FOLDER_VIRTUAL_REVEALED` styling on direct parents of revealed content within virtual chains.

## Acceptance Criteria

- [ ] `MountSpecPath.has_exception_descendant(path)` returns True when any `!`-prefixed pattern exists under the given path
- [ ] `LocalMountConfig.has_pushed_descendant(path)` returns True when any pushed file path starts with the given path prefix
- [ ] `apply_node_states_from_scope()` produces identical results without tree walks (ancestor chain traversal removed from Stages 2+3)
- [ ] Stage 1 reviewed for consolidation opportunities with pattern-native approach
- [ ] GUI `mount_data_tree.py` no longer calls `hierarchy.compute_mirrored_intermediate_paths()` independently
- [ ] GUI `export_structure.py` uses CORE state instead of independent `_has_revealed_descendant()`
- [ ] `FOLDER_VIRTUAL_REVEALED` state correctly assigned to direct parents of revealed children in virtual chains
- [ ] Comprehensive unit tests for all new config query methods
- [ ] Exhaustive truth table regression tests for all 14 folder+file states
- [ ] No performance regression for typical project sizes (hundreds of paths, tens of patterns)

## Out of Scope

- `host_orphaned` implementation (DEFERRED — separate feature)
- `container_only` scan diff logic (unchanged by this refactor)
- GUI cosmetic changes (gradients, colors — unchanged, consumes same NodeState fields)
- CLI changes (CLI doesn't interact with Stage 2/3 currently)
- `hierarchy.compute_mirrored_intermediate_paths()` removal — evaluate whether it's still needed for compose/container_ops consumers after CORE refactor

## Open Questions

1. **hierarchy.py consumers:** `compute_mirrored_intermediate_paths()` is also used by `mirrored_intermediate_container_paths()` for Docker mkdir operations. After the CORE refactor, should those callers switch to the new config queries, or keep the hierarchy function for container-path-specific work?
2. **Stage 1 consolidation:** Review may reveal that `compute_node_state()` can absorb the new descendant queries inline, collapsing to a single-pass pipeline. Decide during implementation.
3. **GUI `_recompute_states()` simplification:** With the GUI Stage 2 duplicate eliminated, `_recompute_states()` may simplify significantly. How much cleanup is warranted vs. deferring to a GUI-focused feature?