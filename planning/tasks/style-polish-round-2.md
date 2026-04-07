# Task: Style Polish Round 2

**Feature:** `planning/features/style-polish-round-2/`
**Branch:** `refactor/style-polish-round-2`
**Status:** COMPLETE

## Goal

Categorical color variable system, correct MOUNTED_MASKED classification, three virtual subtypes, inherited/ancestor color support.

## Execution Plan

### Batch A — NodeState Changes (1 commit)

| Task | File | Change |
|------|------|--------|
| 8 | `core/node_state.py` | Add `is_mount_root: bool` to NodeState, compute in `compute_node_state()` |
| 9 | `gui/mount_data_tree.py` | Add `virtual_type` field to MountDataNode (mirrored/volume/auth) |

**Commit:** `[AI] Add is_mount_root and virtual_type to state model`

---

### Batch B — Color System + State Split (1 commit)

| Task | File | Change |
|------|------|--------|
| 1 | `gui/tree_state_style.json` | Rename variables to `visibility.*`, `config.*` system + add new entries |
| 2 | `gui/tree_state_font.json` | Add text entries for virtual subtypes |
| 3 | `gui/display_config.py` | Rewrite `_FOLDER_STATE_DEFS` with new variable names + new states |
| 4 | `gui/display_config.py` | Update `_FILE_STATE_DEFS` with new variable names |
| 5 | `gui/display_config.py` | Rewrite `FOLDER_STATE_TABLE` — add FOLDER_MASKED, split VIRTUAL types, wire is_mount_root + virtual_type |
| 12 | `gui/style_engine.py` | Verify dotted variable name resolution |

**Commit:** `[AI] Categorical color system and state classification split`

---

### Batch C — Inherited + Ancestor Colors (1 commit)

| Task | File | Change |
|------|------|--------|
| 6 | `gui/tree_state_style.json` | Add `inherited.*`, `ancestor.*` color values (dimmer, less saturated) |
| 7 | `gui/display_config.py` | Wire inherited/ancestor colors into FOLDER_MASKED, FOLDER_PUSHED_ANCESTOR, FOLDER_VIRTUAL_MIRRORED_REVEALED gradients |

**Commit:** `[AI] Add inherited and ancestor color variables`

---

### Batch D — Architecture Docs (1 commit)

| Task | File | Change |
|------|------|--------|
| 13 | `ARCHITECTUREGLOSSARY.md` | Correct MOUNTED_MASKED definition, add MASKED, add virtual subtypes |
| 14 | `GUI_STATE_STYLES.md` | Update color variable tables, gradient assignments, full state list |
| 15 | `COREFLOWCHART.md` | Update visibility table with virtual subtypes |

**Commit:** `[AI] Update architecture docs for style polish round 2`

## Testing

Run `test_display_config.py` and `test_style_engine.py` between batches. Core/docker tests unaffected (display-only changes).

## Open Questions (resolve during implementation)

1. Purple hex value for virtual_auth/virtual_volume
2. Exact dimming formula for inherited.* colors
3. style_engine.py — does JSON key lookup handle dotted names or need adaptation?
4. FOLDER_STATE_TABLE — how to key on is_mount_root and virtual_type (extend condition tuple?)

## Drift: Hardcoded Hex in Python Files

Color hex values should be consolidated into JSON files. Currently scattered:

**display_config.py** — 5 hardcoded hex values (class attributes):
```
line 322: text_primary       #ECEFF4   → move to tree_state_font.json or theme.json
line 374: text_dim           #616E88   → move to tree_state_font.json or theme.json
line 375: text_warning       #D08770   → move to tree_state_font.json or theme.json
line 376: text_virtual_purple #B48EAD  → move to tree_state_font.json or theme.json
line 377: hover_color        #4C566A   → move to theme.json
```

**style_engine.py** — 2 fallback defaults (not palette):
```
line 136: #FFFFFF fallback for palette lookup miss
line 140: #FFFFFF fallback for ui lookup miss
```

**Goal:** All palette hex values live in JSON. Python class attributes resolve from JSON at init. Fallback defaults acceptable in style_engine.py (safety net, not palette choice).

**JSON files that already own colors:**
- `gui/tree_state_style.json` — gradient variables (20 entries)
- `gui/theme.json` — app-wide palette, ui, sections
- `gui/list_style.json` — history panel (4 entries)
- `gui/tree_state_font.json` — no hex (var name references only)
- `gui/list_font.json` — no hex (var name references only)
