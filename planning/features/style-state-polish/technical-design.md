# Technical Design: Style State Polish

## Overview

Split `"mirrored"` visibility into `"virtual"` (mkdir structural path) and keep existing states for explicitly masked/revealed nodes. Fix file state truth table gaps. Establish and document gradient frameworks for both folder and file states.

## Architecture

### Visibility Value Change

```
CURRENT compute_visibility() returns:
  orphaned → revealed → masked → visible → container_only → hidden

Stage 2 upgrades masked → "mirrored" (when has revealed descendant)

PROPOSED:
  orphaned → revealed → masked → visible → container_only → hidden  (unchanged)

Stage 2 upgrades masked → "virtual" (structural mkdir path)
  "mirrored" value REMOVED from visibility vocabulary
```

### Folder State Truth Table (revised)

```
(visibility, has_pushed_descendant, has_direct_visible_child) → State

("hidden",         True,  None)  → FOLDER_PUSHED_ANCESTOR
("hidden",         None,  None)  → FOLDER_HIDDEN
("visible",        None,  None)  → FOLDER_VISIBLE
("masked",         False, None)  → FOLDER_MOUNTED_MASKED
("masked",         True,  None)  → FOLDER_MOUNTED_MASKED_PUSHED
("virtual",        None,  True)  → FOLDER_VIRTUAL_REVEALED     (was MASKED_REVEALED)
("virtual",        None,  False) → FOLDER_VIRTUAL_MIRRORED     (was MASKED_MIRRORED)
("revealed",       None,  None)  → FOLDER_REVEALED
("container_only", None,  None)  → FOLDER_CONTAINER_ONLY
```

### Folder Gradient Framework

```
| P1              | P2              | P3                      | P4                        |
| visibility      | visibility      | descendant influence    | self config action        |
|                 | (inherited)     | (uses P4 color)         | or inheritance type       |
```

**P1 values:** `visible`, `hidden`, `virtual` (from visibility)
**P4 values:** `masked`, `revealed`, `mounted`, or muted version of these
**P3 rule:** If descendant affects this node, P3 = P4's color. Otherwise P3 = P1's color.

### Folder Gradient Map

| State | P1 (vis) | P2 (vis) | P3 (desc→P4) | P4 (self/inherit) |
|-------|----------|----------|---------------|-------------------|
| HIDDEN | background | background | background | background |
| VISIBLE | visible | visible | visible | visible |
| MOUNTED_MASKED | mounted | mounted | masked | masked |
| MOUNTED_MASKED_PUSHED | mounted | mounted | pushed | pushed |
| VIRTUAL_REVEALED | virtual | virtual | revealed | revealed |
| VIRTUAL_MIRRORED | virtual | virtual | mirrored | mirrored |
| REVEALED | revealed | revealed | visible | visible |
| PUSHED_ANCESTOR | background | background | pushed | pushed |
| CONTAINER_ONLY | container_only | container_only | container_only | container_only |

### Folder Font Map

| Visibility | Font |
|------------|------|
| visible | default |
| hidden | muted |
| virtual | muted (structural path, content hidden) |
| revealed | default |
| masked | muted |
| mounted | default |

### File State Truth Table (revised — gaps filled)

```
(visibility, pushed, host_orphaned) → State

("hidden",         False, None)  → FILE_HIDDEN
("hidden",         True,  False) → FILE_PUSHED
("hidden",         True,  True)  → FILE_HOST_ORPHAN (deferred gradient)
("visible",        False, None)  → FILE_VISIBLE
("visible",        True,  False) → FILE_VISIBLE             ← NEW: redundant push
("visible",        True,  True)  → FILE_VISIBLE             ← NEW: redundant push
("masked",         False, None)  → FILE_MASKED
("masked",         True,  False) → FILE_PUSHED
("masked",         True,  True)  → FILE_HOST_ORPHAN
("revealed",       False, None)  → FILE_REVEALED
("revealed",       True,  False) → FILE_REVEALED            ← NEW: redundant push
("revealed",       True,  True)  → FILE_REVEALED            ← NEW: redundant push
("orphaned",       None,  None)  → FILE_CONTAINER_ORPHAN
("container_only", None,  None)  → FILE_CONTAINER_ONLY
```

### File Gradient Framework

```
| F1              | F2              | F3              | F4              |
| visibility      | background      | sync (deferred) | pushed state    |
```

**F3 sync:** Reserved slot. Shows `background` until container scan diff is implemented.
**F4 pushed:** `pushed` color if pushed, `background` if not.

## Dependencies

### Internal
- `core/node_state.py` — `compute_visibility()`, `find_mirrored_paths()`, Stage 2 in `apply_node_states_from_scope()`
- `gui/display_config.py` — state defs, truth tables, resolve_tree_state()
- `gui/style_engine.py` — build_gradient()
- `docs/architecture/GUI_STATE_STYLES.md`
- `docs/architecture/ARCHITECTUREGLOSSARY.md`

### Ordering
1. `compute_visibility()` — add "virtual" return value (or rename mirrored→virtual in Stage 2)
2. Truth tables — update keys
3. State defs — update gradient tuples
4. Architecture docs — update

## Key Changes

### Modified
- `core/node_state.py` — Stage 2: `"mirrored"` → `"virtual"` in `find_mirrored_paths()` / `apply_node_states_from_scope()`
- `gui/display_config.py` — State defs, truth tables, state names (MASKED_REVEALED → VIRTUAL_REVEALED, MASKED_MIRRORED → VIRTUAL_MIRRORED)
- `gui/tree_state_style.json` — Add `"virtual"` color variable (between hidden and visible)
- `docs/architecture/GUI_STATE_STYLES.md` — Full update
- `docs/architecture/ARCHITECTUREGLOSSARY.md` — visibility entry

### Unchanged
- `gui/style_engine.py` — build_gradient() stays (framework works)
- `gui/delegates.py` — painting pipeline stays
- `core/hierarchy.py` — volume generation unaffected
- `core/mount_spec_path.py` — pattern matching unaffected

## Risks

- **Rename "mirrored" → "virtual"** touches every test that checks `visibility == "mirrored"`. Mechanical but wide.
- **File truth table additions** may surface edge cases not currently tested.

## Architecture Doc Impact

- **GUI_STATE_STYLES.md** — Full rewrite of state table, gradient framework documentation
- **ARCHITECTUREGLOSSARY.md** — "visibility" entry: add "virtual", document deprecation of "mirrored"
- **COREFLOWCHART.md** — Stage 2 description: "mirrored" → "virtual"
