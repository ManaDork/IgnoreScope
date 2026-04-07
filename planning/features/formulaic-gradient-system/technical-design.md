# Technical Design — Formulaic Gradient System

## Overview

Replace hand-built folder state definitions with a `derive_gradient()` function that computes gradient positions from node properties. Remove MOUNTED_MASKED. Add FOLDER_MOUNTED.

## derive_gradient()

```python
def derive_gradient(
    visibility: str,
    is_mount_root: bool = False,
    is_masked: bool = False,
    is_revealed: bool = False,
    has_visible_descendant: bool = False,
    virtual_type: str = "mirrored",
    container_only: bool = False,
) -> tuple[GradientClass, str]:
    """Derive gradient + font var from node properties."""

    # P1: visibility
    if container_only:
        p1 = "co"
    elif visibility == "virtual":
        p1 = "mirrored"
    elif visibility in ("visible", "revealed"):
        p1 = "visible"
    else:
        p1 = "hidden"

    # P2: context
    if p1 == "visible" and is_revealed:
        p2 = "hidden"
    else:
        p2 = {"visible": "visible", "hidden": "hidden",
               "mirrored": "hidden", "co": "co"}[p1]

    # P4: config (computed before P3 — P3 may fallback to it)
    if is_mount_root:
        p4 = "mount"
    elif is_revealed:
        p4 = "reveal"
    elif is_masked:
        p4 = "masked"
    elif virtual_type in ("volume", "auth"):
        p4 = f"virtual_{virtual_type}"
    else:
        p4 = None

    # P3: ancestor (overrides P4 position when present)
    if has_visible_descendant and p4 != "reveal":
        p3 = "anc_visible"
    else:
        p3 = None

    # Resolve to color variable names with fallback chain
    p1_var = f"visibility.{p1}"
    p2_var = f"visibility.{p2}"
    p3_var = "ancestor.visible" if p3 else (f"config.{p4}" if p4 else p1_var)
    p4_var = f"config.{p4}" if p4 else p1_var

    # Font
    if container_only:
        font = "italic"
    elif p1 == "mirrored" and virtual_type in ("volume", "auth"):
        font = f"virtual_{virtual_type}"
    elif p1 == "mirrored":
        font = "virtual_mirrored"
    elif p1 == "hidden" and not has_visible_descendant:
        font = "muted"
    else:
        font = "default"

    return GradientClass(p1_var, p2_var, p3_var, p4_var), font
```

## resolve_tree_state() replacement

```python
def resolve_folder_style(node_state, virtual_type="mirrored"):
    """Derive folder gradient from NodeState — no lookup table."""
    has_vis_desc = (node_state.has_pushed_descendant or
                    node_state.has_direct_visible_child)
    return derive_gradient(
        visibility=node_state.visibility,
        is_mount_root=node_state.is_mount_root,
        is_masked=node_state.masked,
        is_revealed=node_state.revealed,
        has_visible_descendant=has_vis_desc,
        virtual_type=virtual_type,
        container_only=node_state.container_only,
    )
```

File states: keep current `resolve_tree_state()` path with `FILE_STATE_TABLE` for now. Only folder states use the formula.

## Files to modify

| File | Change |
|------|--------|
| `core/mount_spec_path.py` | Remove `mount_root_masked` field + serialization |
| `core/node_state.py` | Remove `has_mount_masks` field + computation. Keep `is_mount_root`. |
| `gui/display_config.py` | Replace `_FOLDER_STATE_DEFS` + `FOLDER_STATE_TABLE` with `derive_gradient()`. Keep `_FILE_STATE_DEFS` + `FILE_STATE_TABLE`. Split `resolve_tree_state` into folder (formula) + file (table) paths. |
| `gui/tree_state_style.json` | Replace `ancestor.pushed` + `ancestor.revealed` with unified `ancestor.visible`. Remove `config.mount` rename if needed. |
| `gui/local_host_view.py` | Remove Mask/Unmask from `_show_header_context_menu()` |
| `gui/mount_data_tree.py` | Remove `toggle_mount_root_masked()` |
| `tests/test_core/test_node_state.py` | Remove `has_mount_masks` tests |
| `tests/test_gui/test_display_config.py` | Rewrite folder tests for `derive_gradient()`. Keep file tests. |

## What stays

- `is_mount_root: bool` on NodeState — used by formula for FOLDER_MOUNTED
- `_FILE_STATE_DEFS` + `FILE_STATE_TABLE` — file states keep hand-built layout
- `BaseDisplayConfig`, `TreeDisplayConfig` class hierarchy — unchanged
- `style_engine.py` `build_gradient()` — unchanged, receives GradientClass as before
- `tree_state_font.json` — unchanged
- `GradientClass`, `FontStyleClass`, `StateStyleClass` — unchanged

## state_styles dict

Currently `TreeDisplayConfig.state_styles` is a `dict[str, StateStyleClass]` built from `_TREE_STATE_DEFS` at init. With the formulaic system, folder styles are generated at init:

```python
# In TreeDisplayConfig.__init__:
# File styles from hand-built defs (unchanged)
file_styles = self._build_state_styles(_FILE_STATE_DEFS)

# Folder styles from formula — generate all known states
folder_styles = {}
for name, inputs in FOLDER_STATE_INPUTS.items():
    gradient, font_var = derive_gradient(**inputs)
    font_data = self._font_vars[font_var]
    font = FontStyleClass(...)
    folder_styles[name] = StateStyleClass(gradient=gradient, font=font)

self.state_styles = {**folder_styles, **file_styles}
```

`FOLDER_STATE_INPUTS` is the declarative tuple table — still a table, but only of inputs to the formula, not hand-built outputs.

## Architecture Doc Impact

| Document | Change |
|----------|--------|
| `ARCHITECTUREGLOSSARY.md` | Remove MOUNTED_MASKED. Update display state table. |
| `GUI_STATE_STYLES.md` | Document formula. Replace hand-built state tables. |
| `COREFLOWCHART.md` | Remove has_mount_masks from Phase 3. |
