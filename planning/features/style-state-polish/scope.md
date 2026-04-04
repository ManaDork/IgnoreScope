# Scope: Style State Polish

## Phases

### Phase 1: Visibility Split + Truth Table Fix
Rename `"mirrored"` → `"virtual"` in compute path. Fix file state gaps. No gradient changes yet.
- [ ] `node_state.py`: Stage 2 produces `"virtual"` instead of `"mirrored"`
- [ ] `display_config.py`: Truth table keys updated
- [ ] `display_config.py`: State names updated (MASKED_REVEALED → VIRTUAL_REVEALED, etc.)
- [ ] File truth table: add explicit entries for (visible/revealed, True, *)
- [ ] `resolve_tree_state()`: add warning log on fallback
- [ ] Tests: update all `visibility == "mirrored"` assertions

### Phase 2: Gradient Framework Application
Apply the folder/file gradient frameworks to all state definitions.
- [ ] `tree_state_style.json`: add `"virtual"` color variable
- [ ] Folder gradient defs: apply P1/P2/P3/P4 framework
- [ ] File gradient defs: apply F1/F2/F3/F4 framework
- [ ] Font assignments: 3-tier (visible/hidden/virtual)

### Phase 3: Architecture Docs
- [ ] GUI_STATE_STYLES.md: full rewrite with gradient frameworks
- [ ] ARCHITECTUREGLOSSARY.md: visibility entry updated
- [ ] COREFLOWCHART.md: Stage 2 description updated

## Task Breakdown

| # | Task | Depends On | Complexity | Zone |
|---|------|-----------|------------|------|
| 1 | Rename mirrored→virtual in node_state.py | — | S | Core |
| 2 | Update truth tables + state names in display_config.py | 1 | M | GUI |
| 3 | Add file state gap entries | 2 | S | GUI |
| 4 | Add fallback warning to resolve_tree_state() | 2 | S | GUI |
| 5 | Add virtual color variable | 2 | S | GUI |
| 6 | Apply folder gradient framework | 5 | M | GUI |
| 7 | Apply file gradient framework | 5 | M | GUI |
| 8 | Update font assignments | 6 | S | GUI |
| 9 | Update tests | 1-8 | M | Tests |
| 10 | Update architecture docs | 1-8 | S | Docs |

## Testing Strategy

- **Unit:** resolve_tree_state() returns correct state for every reachable combination
- **Unit:** compute_visibility() returns "virtual" for Stage 2 paths
- **Integration:** Full pipeline: mount → mask → reveal → verify all node states display correctly
- **Manual:** Visual inspection of all 17+ states in both LocalHostView and ScopeView
