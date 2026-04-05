# Technical Design — Style Polish Round 2

## Overview

Rename color variables to categorical system, correct state classifications, add virtual subtypes, split MASKED from MOUNTED_MASKED. Primarily JSON config + display_config.py changes. Node state computation changes minimal (MOUNTED_MASKED detection needs mount-root check).

## Dependencies

### Internal

| Module | Change |
|--------|--------|
| `gui/tree_state_style.json` | Rename all variables to `visibility.*`, `config.*`, `inherited.*` system |
| `gui/tree_state_font.json` | Add text color entries for virtual subtypes, pushed sync states |
| `gui/display_config.py` | Update `_FOLDER_STATE_DEFS`, `_FILE_STATE_DEFS`, `FOLDER_STATE_TABLE`, `FILE_STATE_TABLE` |
| `gui/style_engine.py` | Verify GradientClass resolves new variable names correctly |
| `core/node_state.py` | Add `is_mount_root` flag or detect dual-declaration for MOUNTED_MASKED |
| `gui/mount_data_tree.py` | Add VIRTUAL_VOLUME and VIRTUAL_AUTH node types |

### Architecture Docs

| Document | Change |
|----------|--------|
| `ARCHITECTUREGLOSSARY.md` | Correct MOUNTED_MASKED definition, add MASKED, add virtual subtypes |
| `GUI_STATE_STYLES.md` | Update color variable tables, gradient assignments, state list |
| `COREFLOWCHART.md` | Update visibility table (add virtual subtypes to Stage 2 output) |

## Key Changes

### 1. Color Variable Rename (tree_state_style.json)

Old → New mapping:
```
"background"     → "visibility.background"
"visible"        → "visibility.visible"
"hidden"         → "visibility.hidden"
"virtual"        → "visibility.virtual"
"mounted"        → "config.mount"
"pushed"         → "config.pushed"
"masked"         → "config.masked"
"revealed"       → "config.revealed"
"container_only" → "visibility.container_only"
"warning"        → "status.warning"
"selected"       → "ui.selected"
```

Plus new entries:
```
"inherited.masked"          → dimmer config.masked
"inherited.revealed"        → dimmer config.revealed
"inherited.virtual_auth"    → new
"inherited.virtual_volume"  → new
"ancestor.pushed"           → new
"ancestor.revealed"         → new
"text.virtual_volume"       → purple (TBD hex)
"text.virtual_auth"         → purple (TBD hex)
```

### 2. State Classification Fix (display_config.py)

**Split MASKED:**
- Current `FOLDER_MOUNTED_MASKED` (vis=masked) → rename to `FOLDER_MASKED`
- New `FOLDER_MOUNTED_MASKED` → only when NodeState indicates mount root + mask

**Detection:** `compute_node_state()` needs to flag when `path == mount_spec.mount_root AND is_masked`. Add `is_mount_root: bool` to NodeState, or derive in truth table from existing flags.

**Split VIRTUAL:**
- Current `FOLDER_VIRTUAL` → `FOLDER_VIRTUAL_MIRRORED`
- Current `FOLDER_VIRTUAL_REVEALED` → `FOLDER_VIRTUAL_MIRRORED_REVEALED`
- New `FOLDER_VIRTUAL_VOLUME` → node.is_virtual and node type = volume
- New `FOLDER_VIRTUAL_AUTH` → node.is_virtual and node type = auth

**Detection:** Virtual nodes already have `is_virtual=True` on MountDataNode. Need to add a `virtual_type` field or similar to distinguish mirrored/volume/auth.

### 3. Font System (tree_state_font.json)

Add font entries:
```
"text.virtual_mirrored": { "weight": normal, "italic": false, "text_color": "text.visible" }
"text.virtual_volume":   { "weight": normal, "italic": true,  "text_color": "purple" }
"text.virtual_auth":     { "weight": normal, "italic": true,  "text_color": "purple" }
"text.pushed_sync":      { "weight": normal, "italic": false, "text_color": TBD }
"text.pushed_nosync":    { "weight": normal, "italic": false, "text_color": TBD }
```

## Risks

1. **Variable rename breaks gradient resolution** — style_engine.py resolves variable names from JSON at paint time. All references must be updated atomically.
2. **MOUNTED_MASKED detection** — adding `is_mount_root` to NodeState is a dataclass change. Verify frozen dataclass implications.
3. **Virtual subtype detection** — MountDataNode needs to carry virtual type info from tree construction through to display.

## Alternatives Considered

1. **Keep flat variable names, just add new ones** — rejected, naming is already confusing and will get worse with inherited/ancestor additions.
2. **Derive MOUNTED_MASKED in display_config only** — possible but means display_config needs config access, violating the "consumers format, never derive" rule.
