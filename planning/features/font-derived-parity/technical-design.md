# Font Derived Parity — Technical Design

## Overview

Replace hand-coded file state font assignments with a formulaic `derive_file_style()` function, add pushed font key placeholders, and bring test coverage to parity with folder derivation.

## Architecture

### Current Flow (files)
```
Hand-coded _FILE_STATE_DEFS dict
    → 8 entries: (GradientClass | None, font_key_str)
    → _TREE_STATE_DEFS (union with folders)
    → _build_state_styles() → StateStyleClass
```

### Target Flow (files)
```
_FILE_STYLE_INPUTS dict (property dicts per state)
    → derive_file_style(**inputs) per entry
    → _FILE_STATE_DEFS (derived, same shape)
    → _TREE_STATE_DEFS (union with folders, unchanged)
    → _build_state_styles() → StateStyleClass (unchanged)
```

Parallel to existing folder flow:
```
_FOLDER_STATE_INPUTS → derive_gradient() → _FOLDER_STATE_DEFS
```

## Dependencies

### Internal
- `display_config.py` — primary change target
- `tree_state_font.json` — add placeholder keys
- `theme.json` — add placeholder text colors
- `style_engine.py` — no changes (FontStyleClass unchanged)
- `delegates.py` — no changes (paint pipeline unchanged)
- `GUI_STATE_STYLES.md` — documentation update

### External
- None

### Ordering
1. JSON placeholders first (font keys + theme colors)
2. `derive_file_style()` function
3. `_FILE_STYLE_INPUTS` dict + comprehension
4. Tests
5. Architecture doc update

## Key Changes

### New Files
None.

### Modified Files

#### `IgnoreScope/gui/display_config.py`

**New function: `derive_file_style()`**

```python
def derive_file_style(
    visibility: str,
    is_pushed: bool = False,
    container_orphaned: bool = False,
    container_only: bool = False,
) -> tuple[Optional[GradientClass], str]:
    """Derive file gradient + font key from node properties.

    Parallel to derive_gradient() for folders. Files use a simplified
    gradient model: P1 = visibility, P2/P3 = background (no descendant
    tracking), P4 = config overlay.
    """
```

**Derivation formula:**

| Property | P1 | P2 | P3 | P4 | Font |
|----------|----|----|----|----|------|
| visibility=hidden | vis.hidden | vis.bg | vis.bg | vis.bg | "muted" |
| visibility=visible | vis.visible | vis.bg | vis.bg | vis.bg | "default" |
| visibility=masked | vis.hidden | vis.bg | vis.bg | vis.bg | "muted" |
| visibility=revealed | vis.visible | vis.bg | vis.bg | vis.bg | "default" |
| is_pushed=True | vis.hidden | vis.bg | vis.bg | config.pushed | "default" |
| container_orphaned=True | vis.hidden | vis.bg | vis.bg | status.warning | "italic" |
| container_only=True | vis.container_only | vis.bg | vis.bg | vis.bg | "italic" |
| visibility=orphaned (host) | None | None | None | None | "italic" |

P1 mapping:
- `hidden`, `masked`, `orphaned` (pushed), `container_orphaned` → `"visibility.hidden"`
- `visible`, `revealed` → `"visibility.visible"`
- `container_only` → `"visibility.container_only"`
- `orphaned` (host) → gradient deferred (`None`)

P4 mapping:
- `is_pushed` → `"config.pushed"`
- `container_orphaned` → `"status.warning"`
- default → falls back to P1

Font mapping:
- `container_only` or `container_orphaned` or host orphan → `"italic"`
- visibility in (`hidden`, `masked`) and not pushed → `"muted"`
- else → `"default"`

**New dict: `_FILE_STYLE_INPUTS`**

```python
_FILE_STYLE_INPUTS: dict[str, dict] = {
    "FILE_HIDDEN":            {"visibility": "hidden"},
    "FILE_VISIBLE":           {"visibility": "visible"},
    "FILE_MASKED":            {"visibility": "masked"},
    "FILE_REVEALED":          {"visibility": "revealed"},
    "FILE_PUSHED":            {"visibility": "hidden", "is_pushed": True},
    "FILE_HOST_ORPHAN":       {"visibility": "orphaned"},
    "FILE_CONTAINER_ORPHAN":  {"visibility": "hidden", "container_orphaned": True},
    "FILE_CONTAINER_ONLY":    {"visibility": "container_only", "container_only": True},
}
```

**Replaced comprehension:**
```python
_FILE_STATE_DEFS: dict[str, tuple[Optional[GradientClass], str]] = {
    name: derive_file_style(**inputs) for name, inputs in _FILE_STYLE_INPUTS.items()
}
```

**Class attribute additions (TreeDisplayConfig):**
```python
# Unused placeholders — pushed sync/nosync font colors (future wiring)
text_pushed_sync: str = "#BDA4FF"
text_pushed_nosync: str = "#8B7BBF"
```

#### `IgnoreScope/gui/tree_state_font.json`

Add two entries (unused placeholders):

```json
{
    "default":          { "weight": "normal", "italic": false, "text_color": "text_primary" },
    "muted":            { "weight": "normal", "italic": false, "text_color": "text_dim" },
    "italic":           { "weight": "normal", "italic": true,  "text_color": "text_warning" },
    "virtual_mirrored": { "weight": "normal", "italic": false, "text_color": "text_primary" },
    "virtual_volume":   { "weight": "normal", "italic": true,  "text_color": "text_virtual_purple" },
    "virtual_auth":     { "weight": "normal", "italic": true,  "text_color": "text_virtual_purple" },
    "pushed_sync":      { "weight": "normal", "italic": false, "text_color": "text_pushed_sync" },
    "pushed_nosync":    { "weight": "normal", "italic": false, "text_color": "text_pushed_nosync" }
}
```

Note: JSON has no comment syntax. Placeholder status documented in Python code and this spec.

#### `IgnoreScope/gui/theme.json`

Add to `"text"` section:

```json
"text": {
    "text_primary": "#F0E5FF",
    "text_dim": "#BEB2D5",
    "text_warning": "#FFB15D",
    "text_virtual_purple": "#BDA4FF",
    "text_pushed_sync": "#BDA4FF",
    "text_pushed_nosync": "#8B7BBF"
}
```

Placeholder hex values: `text_pushed_sync` matches existing pushed accent (`#BDA4FF`), `text_pushed_nosync` is a dimmed variant.

#### `IgnoreScope/tests/test_gui/test_display_config.py`

New tests:

1. **`test_derive_file_style_all_states`** — parametrized over all 8 `_FILE_STYLE_INPUTS` entries, asserts output matches expected `(GradientClass, font_key)` tuples
2. **`test_derive_file_style_gradient_positions`** — validates P1/P2/P3/P4 variable names for each file state
3. **`test_derive_file_style_host_orphan_deferred`** — asserts `FILE_HOST_ORPHAN` returns `(None, "italic")`
4. **`test_pushed_font_keys_exist`** — validates `pushed_sync` and `pushed_nosync` exist in `_font_vars`
5. **`test_pushed_text_color_vars_resolve`** — validates `text_pushed_sync` and `text_pushed_nosync` resolve to hex strings
6. **`test_font_vars_count`** — update expected count from 6 → 8
7. **`test_font_vars_keys`** — update expected key set

#### `docs/architecture/GUI_STATE_STYLES.md`

Updates:
- Add `derive_file_style()` documentation parallel to `derive_gradient()` section
- Add file derivation formula table
- Update font variable reference (Section 6.1) to include `pushed_sync`, `pushed_nosync`
- Update one-off color variables (Section 6.3) to include `text_pushed_sync`, `text_pushed_nosync`
- Note placeholder status of pushed font keys

## Interfaces & Data

### `derive_file_style()` Signature
```python
def derive_file_style(
    visibility: str,
    is_pushed: bool = False,
    container_orphaned: bool = False,
    container_only: bool = False,
) -> tuple[Optional[GradientClass], str]:
```

**Input**: Node visibility string + boolean property flags (subset of NodeState fields relevant to files).

**Output**: Same shape as `derive_gradient()` — `(GradientClass | None, font_key_string)`. Consumed by `_build_state_styles()` unchanged.

### No new classes or dataclasses required.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Extend `derive_gradient()` with `is_file` param | Mixes folder/file concerns in one function; files don't need P3 ancestor tracking or virtual_type |
| Position-based FontGradientClass | Over-engineered for current needs; only 3 font properties vs 4 gradient positions |
| Hybrid tuple return from `derive_gradient()` | Breaks separation — files shouldn't route through folder formula |
| Keep hand-coded file defs | Structural asymmetry persists; adding pushed states means more magic strings |

## Risks

| Risk | Mitigation |
|------|-----------|
| `derive_file_style()` output diverges from current hand-coded values | Parametrized test asserts exact match for all 8 states |
| Pushed placeholder hex values clash with future palette shift | Values intentionally match existing accent colors; palette shift will update all hex values uniformly |
| `_build_state_styles()` breaks with new font keys | Already validated — function is generic, handles any font key string |

## Architecture Doc Impact

| Document | Update Required |
|----------|----------------|
| `GUI_STATE_STYLES.md` | Add file derivation section, update font variable tables, document pushed placeholders |
| `ARCHITECTUREGLOSSARY.md` | No change — `derive_file_style` is a GUI implementation detail, not a domain term |
| `DATAFLOWCHART.md` | No change — data flow shape unchanged (still state_defs → _build_state_styles → StateStyleClass) |
