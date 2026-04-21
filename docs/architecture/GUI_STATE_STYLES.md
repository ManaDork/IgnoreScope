# GUI State Styles Reference

> **Companion to:** `GUI_LAYOUT_SPECS.md` — all state visual definitions live here.

---

## 1. GradientClass

### 4-Position Universal Model

GradientClass replaces the three legacy gradient types (`standard`, `dual_state`, `virtual`) with a single universal model. Every gradient has exactly 4 positions with blended transitions:

```
GradientClass(pos1, pos2, pos3, pos4)

Position layout:
|── pos1 (0.0) ──|── pos2 (0.25) ──|── pos3 (0.50) ──|── pos4 (0.75) ──|
```

Each argument is a **variable name** (string) resolved from a style JSON file at paint time. Variables resolve to hex colors via the color variable table (Section 5).

### Variable Name Resolution

```
GradientClass("visibility.virtual", "visibility.virtual", "inherited.masked", "config.revealed")
                  │                   │                     │                    │
                  ▼                   ▼                     ▼                    ▼
              *_theme.json → local_host.state_colors lookup
              (scope panel uses _scope_resolved.state_colors)
                  │                   │                     │                    │
                  ▼                   ▼                     ▼                    ▼
              #2E2448             #2E2448               #582A2E              #DD9B4C
                  │         │         │          │
                  ▼         ▼         ▼          ▼
              QLinearGradient(0.0, 0.25, 0.50, 0.75)
```

### Legacy Migration Table

| Legacy Type | Stop Count | Position Model | GradientClass Equivalent |
|-------------|-----------|----------------|--------------------------|
| `standard` | 2 (0.0→0.6-1.0) | left, right | `GradientClass(left, left, right, right)` — pos1=pos2, pos3=pos4 |
| `dual_state` | 3 (0.0-0.25, 0.35-0.65, 0.75-1.0) | mounted, visibility, masked | `GradientClass(mounted, mounted, vis_or_state, masked)` — 4-arg, distinct per-state |
| `virtual` | 3 (0.0-0.3, 0.5, 0.7-1.0) | state, visibility, revealed | `GradientClass(state, state, visibility, revealed)` — pos3≠pos4 |

The universal model eliminates gradient type branching. Each state declares its 4 variables explicitly. The old `standard` pattern reappears as `pos1=pos2, pos3=pos4`. The old `virtual`/`dual_state` patterns use distinct values at pos3 and pos4.

---

## 2. StateStyleClass + FontStyleClass

### Composition Pattern

```
StateStyleClass:
    gradient: GradientClass(pos1, pos2, pos3, pos4)
    font:     FontStyleClass(font_var)
```

**StateStyleClass** is the complete visual recipe for one node state. It composes a GradientClass (background gradient) with a FontStyleClass (text properties). Each of the 22 tree states and 5 list states maps to exactly one StateStyleClass.

### FontStyleClass

```
FontStyleClass(font_var)
```

`font_var` is a variable name resolved from the consolidated theme's `local_host.fonts` section (or `_scope_resolved.fonts` for the scope panel). Defines text weight, italic, and text color. See Section 6 for variable tables.

### Selected State Override Mechanism

When a node is selected, the base StateStyleClass is modified — NOT replaced. Only **pos2** and **pos3** are overridden with the `selected` color variable. pos1 and pos4 retain the base state's values.

```
Base:     GradientClass(masked, masked, hidden, revealed)
Selected: GradientClass(masked, selected, selected, revealed)
                              ▲          ▲
                        pos2 override   pos3 override
```

This preserves the node's identity (pos1 state color, pos4 visibility/state color) while indicating selection in the center of the gradient.

Two selected overrides:

- **FOLDER_SELECTED**: applied to any folder state — overrides pos2, pos3 with `selected`
- **FILE_SELECTED**: applied to any file state — overrides pos2, pos3 with `selected`

These are not independent states — they modify the node's current StateStyleClass.

---

## 3. State Enumeration — Tree Panels

22 tree states (14 folder + 8 file) + 2 selected overrides.

Visibility is pure STATE (`accessible`, `restricted`, `virtual`). METHOD flags (`is_masked`, `is_revealed`, `is_mount_root`, etc.) from NodeState drive accent positions (P3/P4) in the gradient. GUI reads CORE-computed NodeState fields via if/elif resolution — no tree walking in the GUI.

### 3.1 Folder States (14)

14 states derived from CORE visibility STATE + boolean METHOD flags + tree-context fields. Resolved by `_resolve_folder_state()` in `display_config.py`.

| ID | State Name | Resolution Path | GradientClass(pos1, pos2, pos3, pos4) | FontStyleClass |
|----|-----------|-----------------|---------------------------------------|---------------|
| F1 | `FOLDER_HIDDEN` | vis=restricted, not masked, no descendants | `(restricted, restricted, restricted, restricted)` | `muted` |
| F2 | `FOLDER_VISIBLE` | vis=accessible, not revealed, not mount_root | `(accessible, accessible, accessible, accessible)` | `default` |
| F3 | `FOLDER_MOUNTED` | vis=accessible, is_mount_root, no vis descendants | `(accessible, accessible, accessible, config.mount)` | `default` |
| F4 | `FOLDER_MOUNTED_REVEALED` | vis=accessible, is_mount_root, has_vis_desc | `(accessible, accessible, accessible, config.mount)` | `default` |
| F5 | `FOLDER_MASKED` | vis=restricted, masked=T | `(restricted, restricted, restricted, inherited.masked)` | `muted` |
| F6 | `FOLDER_MASKED_REVEALED` | vis=virtual, masked=T, has_vis_desc | `(virtual, virtual, inherited.masked, config.revealed)` | `default` |
| F7 | `FOLDER_MASKED_MIRRORED` | vis=virtual, masked=T, no vis descendants | `(virtual, virtual, inherited.masked, inherited.masked)` | `default` |
| F8 | `FOLDER_REVEALED` | vis=accessible, revealed=T | `(accessible, restricted, restricted, config.revealed)` | `default` |
| F9 | `FOLDER_MIRRORED` | vis=virtual, not masked, no vis descendants | `(virtual, virtual, virtual, virtual)` | `stencil_mirrored` |
| F10 | `FOLDER_MIRRORED_REVEALED` | vis=virtual, not masked, has_vis_desc | `(virtual, virtual, virtual, ancestor.visible)` | `stencil_mirrored` |
| F11 | `FOLDER_STENCIL_VOLUME` | vis=virtual, stencil_tier=volume | `(virtual, virtual, virtual, stencil.volume)` | `stencil_volume` |
| F12 | `FOLDER_STENCIL_AUTH` | vis=virtual, stencil_tier=auth | `(virtual, virtual, virtual, stencil.auth)` | `stencil_auth` |
| F13 | `FOLDER_PUSHED_ANCESTOR` | vis=restricted, not masked, has_vis_desc | `(restricted, restricted, restricted, ancestor.visible)` | `default` |
| F14 | `FOLDER_CONTAINER_ONLY` | vis=virtual, container_only=T | `(virtual, virtual, virtual, virtual)` | `italic` |

**Folder resolution** (if/elif chain in `_resolve_folder_state()`, first match wins):

```
visibility | masked | revealed | mount_root | stencil_tier | has_vis_desc | -> State Name              | Font
---------- | ------ | -------- | ---------- | ------------ | ------------ | -------------------------- | -------
virtual    | -      | -        | -          | volume       | -            | FOLDER_STENCIL_VOLUME      | stencil_volume
virtual    | -      | -        | -          | auth         | -            | FOLDER_STENCIL_AUTH        | stencil_auth
virtual    | T      | -        | -          | -            | T            | FOLDER_MASKED_REVEALED     | default
virtual    | T      | -        | -          | -            | F            | FOLDER_MASKED_MIRRORED     | default
virtual    | F      | -        | -          | -            | T            | FOLDER_MIRRORED_REVEALED   | stencil_mirrored
virtual    | F      | -        | -          | -            | F            | FOLDER_MIRRORED            | stencil_mirrored
accessible | -      | T        | -          | -            | -            | FOLDER_REVEALED            | default
accessible | -      | F        | T          | -            | T            | FOLDER_MOUNTED_REVEALED    | default
accessible | -      | F        | T          | -            | F            | FOLDER_MOUNTED             | default
accessible | -      | F        | F          | -            | -            | FOLDER_VISIBLE             | default
restricted | -      | -        | -          | -            | -            | (check masked)             |
 ↳ masked  | T      | -        | -          | -            | -            | FOLDER_MASKED              | muted
 ↳ !masked | -      | -        | -          | -            | T            | FOLDER_PUSHED_ANCESTOR     | default
 ↳ !masked | -      | -        | -          | -            | F            | FOLDER_HIDDEN              | muted
```

"-" = field not checked for this state (any value matches).

**Notes:**

- **FOLDER_VISIBLE** = "accessible" in CORE. vis=accessible is produced when mounted=T or revealed=T. The mount_root boolean and revealed boolean disambiguate within accessible.
- **FOLDER_PUSHED_ANCESTOR** = restricted folder (not under any mount, not masked) with a visible descendant. Distinct from F5 (FOLDER_MASKED) which is a masked folder inside a mount.
- **FOLDER_MASKED_REVEALED** vs **FOLDER_MASKED_MIRRORED**: Both vis=virtual with masked=T. Visible descendant presence distinguishes "parent of visible content" from "structural mkdir-p intermediate."
- **FOLDER_MIRRORED** vs **FOLDER_MIRRORED_REVEALED**: Both vis=virtual without masked. These are structural paths above mount boundaries.
- **FOLDER_CONTAINER_ONLY**: vis=virtual with container_only=T. Container-only nodes that aren't masked get virtual visibility in Stage 1.
- New states vs prior spec: FOLDER_MOUNTED, FOLDER_MOUNTED_REVEALED, FOLDER_MIRRORED, FOLDER_MIRRORED_REVEALED, FOLDER_STENCIL_VOLUME, FOLDER_STENCIL_AUTH, FOLDER_CONTAINER_ONLY are new. Old F3 (FOLDER_MOUNTED_MASKED) and F4 (FOLDER_MOUNTED_MASKED_PUSHED) consolidated into F5 (FOLDER_MASKED) — mount_root distinction now handled by FOLDER_MOUNTED/FOLDER_MOUNTED_REVEALED.

### 3.2 File States (8)

8 states derived from CORE visibility STATE + boolean METHOD flags. Resolved by `_resolve_file_state()` in `display_config.py`. File gradients use P1=visibility state, P2/P3=always `visibility.restricted`, P4=config accent or fallback.

| ID | State Name | Resolution Path | GradientClass(pos1, pos2, pos3, pos4) | FontStyleClass |
|----|-----------|-----------------|---------------------------------------|---------------|
| FI1 | `FILE_HIDDEN` | vis=restricted, not pushed, not masked | `(visibility.restricted, visibility.restricted, visibility.restricted, visibility.restricted)` | `muted` |
| FI2 | `FILE_VISIBLE` | vis=accessible, not revealed | `(visibility.accessible, visibility.restricted, visibility.restricted, visibility.accessible)` | `default` |
| FI3 | `FILE_MASKED` | vis=restricted, masked=T, not pushed | `(visibility.restricted, visibility.restricted, visibility.restricted, visibility.restricted)` | `muted` |
| FI4 | `FILE_REVEALED` | vis=accessible, revealed=T | `(visibility.accessible, visibility.restricted, visibility.restricted, config.revealed)` | `default` |
| FI5 | `FILE_PUSHED` | vis=restricted, pushed=T, host_orphaned=F | `(visibility.restricted, visibility.restricted, visibility.restricted, config.pushed)` | `default` |
| FI6 | `FILE_HOST_ORPHAN` | vis=restricted, pushed=T, host_orphaned=T | *(DEFERRED — gradient TBD)* | `italic` |
| FI7 | `FILE_CONTAINER_ORPHAN` | container_orphaned=T | `(visibility.restricted, visibility.restricted, visibility.restricted, status.warning)` | `italic` |
| FI8 | `FILE_CONTAINER_ONLY` | container_only=T | `(visibility.virtual, visibility.restricted, visibility.restricted, visibility.virtual)` | `italic` |

**File resolution** (if/elif chain in `_resolve_file_state()`, first match wins):

```
container_only | container_orphaned | visibility  | revealed | pushed | host_orph | -> State Name         | Font
-------------- | ------------------ | ----------- | -------- | ------ | --------- | --------------------- | ------
T              | -                  | -           | -        | -      | -         | FILE_CONTAINER_ONLY   | italic
-              | T                  | -           | -        | -      | -         | FILE_CONTAINER_ORPHAN | italic
-              | -                  | accessible  | T        | -      | -         | FILE_REVEALED         | default
-              | -                  | accessible  | F        | -      | -         | FILE_VISIBLE          | default
-              | -                  | restricted  | -        | T      | T         | FILE_HOST_ORPHAN      | italic (DEFERRED)
-              | -                  | restricted  | -        | T      | F         | FILE_PUSHED           | default
-              | -                  | restricted  | -        | F      | -         | (check masked)        |
 ↳ masked=T    | -                  | -           | -        | -      | -         | FILE_MASKED           | muted
 ↳ masked=F    | -                  | -           | -        | -      | -         | FILE_HIDDEN           | muted
```

"-" = field not checked (any value).

**Notes:**

- **FILE_CONTAINER_ONLY** is new. container_only=T nodes get vis=virtual in Stage 1, resolved first in the if/elif chain.
- **FILE_CONTAINER_ORPHAN** resolved via `container_orphaned` boolean flag, not the visibility string (vis=restricted for orphaned nodes).
- **FILE_HOST_ORPHAN** is DEFERRED. The state exists in the design model but requires scoping decisions about scan coverage before implementation.
- **Pushed redundancy rule:** When pushed=T AND visibility=accessible, the push is redundant. `_resolve_file_state()` checks `vis == "accessible"` before pushed, so these resolve as FILE_VISIBLE or FILE_REVEALED.
- File resolver was converted from FILE_STATE_TABLE lookup to if/elif chain, matching folder pattern.

### 3.3 Selected State Overrides

| Override | Applies To | Mechanism |
|----------|-----------|-----------|
| FOLDER_SELECTED | Any F1–F14 state | pos2 -> `selected`, pos3 -> `selected` |
| FILE_SELECTED | Any FI1–FI8 state | pos2 -> `selected`, pos3 -> `selected` |

Selected overrides are applied at paint time. They do not create new StateStyleClass entries — they modify the base state's GradientClass positions. See Section 2 for the override mechanism.

---

## 4. State Enumeration — List Panels

### 4.1 History Entry States (5 states)

Session History panel states, derived from `entry_type` (HistoryEntryType enum) + `is_current` (undo cursor) + cursor position.

| ID | State Name | GradientClass(pos1, pos2, pos3, pos4) | FontStyleClass | When |
|----|-----------|---------------------------------------|---------------|------|
| H1 | `HISTORY_NORMAL` | `(background, background, background, background)` | `default` | Entry outside undo range, or no undos |
| H2 | `HISTORY_UNDO_CURRENT` | `(selected, selected, background, background)` | `default` | Non-destructive entry at undo cursor |
| H3 | `HISTORY_REDO_AVAILABLE` | `(warning, background, background, background)` | `default` | Entry above cursor (available for redo) |
| H4 | `HISTORY_DESTRUCTIVE` | `(background, background, destructive, destructive)` | `default` | Destructive action, not at cursor |
| H5 | `HISTORY_DESTRUCTIVE_SELECTED` | `(selected, background, destructive, destructive)` | `default` | Destructive action at undo cursor |

**Variable resolution:** History states use `list_style.json` for color variables and `list_font.json` for font variables (separate files — not yet consolidated into `*_theme.json`; deferred until session history panel is wired).

### 4.2 MatrixState Resolution Table

| entry_type | is_current | above_cursor | → State |
|------------|-----------|-------------|---------|
| normal | False | False | `HISTORY_NORMAL` |
| normal | True | — | `HISTORY_UNDO_CURRENT` |
| normal | False | True | `HISTORY_REDO_AVAILABLE` |
| destructive | False | False | `HISTORY_DESTRUCTIVE` |
| destructive | True | — | `HISTORY_DESTRUCTIVE_SELECTED` |
| destructive | False | True | `HISTORY_REDO_AVAILABLE` |

**Source panel mapping:**

- Folder Configuration entries (`undo_scope=full`): produce `normal` entry_type → HISTORY_NORMAL, HISTORY_UNDO_CURRENT, HISTORY_REDO_AVAILABLE
- Scope Configuration entries (`undo_scope=selection_history`): produce `destructive` entry_type → HISTORY_DESTRUCTIVE, HISTORY_DESTRUCTIVE_SELECTED, HISTORY_REDO_AVAILABLE

---

## 5. Color Variable Reference

### 5.1 Consolidated Theme — `local_host.state_colors`

**Source:** `*_theme.json` → `local_host.state_colors` section

Color variables for tree panel GradientClass resolution. Uses categorical dot-notation naming. The scope panel inherits these values via deep-merge (see Section 5.3).

| Variable | Hex (local_host) | Hex (scope) | Color Group |
|----------|-------------------|-------------|-------------|
| `visibility.accessible` | `#44368B` | `#3A2E78` | State — content accessible to container |
| `visibility.restricted` | `#23283B` | `#1E1A30` | State — content restricted from container |
| `visibility.virtual` | `#2E2448` | `#281E40` | State — structural intermediate / container-only |
| `config.mount` | `#DC6888` | `#C85878` | Pink — mount root / active mount |
| `config.masked` | `#6C3439` | `#5A2B30` | Dark red — content excluded from container |
| `config.revealed` | `#DD9B4C` | `#C88840` | Orange — content restored under mask |
| `config.pushed` | `#F17149` | `#D06040` | Red-orange — docker cp'd content |
| `inherited.masked` | `#582A2E` | `#4A2228` | Dark red (dim) — inherited mask from ancestor |
| `inherited.revealed` | `#B88040` | `#A07035` | Orange (dim) — inherited reveal from ancestor |
| `inherited.stencil_auth` | `#501E60` | `#441A55` | Purple — inherited stencil auth path |
| `inherited.stencil_volume` | `#501E60` | `#441A55` | Purple — inherited stencil volume path |
| `ancestor.visible` | `#DD9B4C` | `#C88840` | Orange — ancestor has visible descendants |
| `stencil.volume` | `#662477` | `#581E68` | Purple — volume stencil node |
| `stencil.auth` | `#662477` | `#581E68` | Purple — auth stencil node |
| `status.warning` | `#DD9B4C` | `#C88840` | Orange — attention-required state |
| `ui.selected` | `#6366F1` | `#5558E0` | Indigo — delegate selection overlay |

**Color groups** (semantic families):

- **Pink/Red** (mount/mask): `config.mount`, `config.masked`, `inherited.masked` — mount root and content excluded from container
- **Purple** (stencil): `stencil.*`, `inherited.stencil_*` — stencil (synthetic intermediate) path content
- **Red-orange** (push): `config.pushed` — docker cp'd content
- **Orange** (reveal/warning): `config.revealed`, `inherited.revealed`, `ancestor.visible`, `status.warning` — restored or attention-required
- **State** (visibility): `visibility.*` — 3 pure state keys mapping directly to visibility field values

**Variable naming convention:** Dot-notation groups variables by **semantic origin** (visibility, config, inherited, stencil, status, ui). The same group prefix may resolve to different hex values per panel — the scope panel can override any variable via `scope.state_colors` deep-merge.

### 5.2 list_style.json (not yet consolidated)

Color variables for list panel (Session History) GradientClass resolution. Still stored in separate `list_style.json` — will be consolidated as a `session_history` section when the list panel is wired.

| Variable | Hex | Source |
|----------|-----|--------|
| `background` | `#231745` | `ui.panel_bg` |
| `selected` | `#6366F1` | `ui.accent_secondary` |
| `warning` | `#FFCE5D` | `palette.accent_yellow` |
| `destructive` | `#FF7069` | `palette.accent_red` |

### 5.3 Per-Panel Deep-Merge (Scope Override)

At load time, `_load_consolidated_theme()` deep-merges `scope.state_colors` over a copy of `local_host.state_colors` (same for fonts). The result is stored in `_scope_resolved`.

```
local_host.state_colors  ──copy──→  merged dict
scope.state_colors       ──update→  merged dict  →  _scope_resolved.state_colors
```

- **Empty scope sections** = scope panel is visually identical to local_host
- **Scope overrides** only need to declare keys that differ — all others inherit from local_host
- `TreeDisplayConfig(panel="scope")` reads from `_scope_resolved`; `TreeDisplayConfig(panel="local_host")` reads from `local_host` directly

---

## 6. Font Variable Reference

### 6.1 Consolidated Theme — `local_host.fonts`

**Source:** `*_theme.json` → `local_host.fonts` section

Font variables for tree panel FontStyleClass resolution. All values use **variable indirection** — `text_color` references a variable name resolved against `base.text` at construction time, not a direct hex value. Scope panel inherits via deep-merge (same pattern as state_colors).

| Variable | Weight | Italic | text_color (variable) | Used By |
|----------|--------|--------|----------------------|---------|
| `default` | normal | false | `text_primary` | F2–F4, F6–F8, F10, F13, FI2, FI4–FI5 |
| `muted` | normal | false | `text_dim` | F1, F5, FI1, FI3 |
| `italic` | normal | true | `text_warning` | F14, FI6–FI8 |
| `stencil_mirrored` | normal | false | `text_primary` | F9 (FOLDER_MIRRORED), F10 (FOLDER_MIRRORED_REVEALED) |
| `stencil_volume` | normal | true | `text_stencil_purple` | F11 (FOLDER_STENCIL_VOLUME) |
| `stencil_auth` | normal | true | `text_stencil_purple` | F12 (FOLDER_STENCIL_AUTH) |
| `pushed_sync` | normal | false | `text_pushed_sync` | Pushed files (synced) |
| `pushed_nosync` | normal | false | `text_pushed_nosync` | Pushed files (not synced) |

**Note:** Text color is included in FontStyleClass to unify text rendering. The old TreeContext-based text color axis is absorbed: all tree contexts share the same font variables via their respective display configs.

### 6.2 list_font.json (not yet consolidated)

Font variables for list panel (Session History) FontStyleClass resolution. Same variable indirection pattern. Still stored in separate `list_font.json` — will be consolidated when the list panel is wired.

| Variable | Weight | Italic | text_color (variable) |
|----------|--------|--------|----------------------|
| `default` | normal | false | `text_primary` |

### 6.3 Text Colors + Delegate Overlays (Injected from Theme)

The following values are used in rendering but don't correspond to gradient state variables. All are injected from the consolidated theme at construction time — **no class-level hex defaults** remain in Python.

**TreeDisplayConfig** — injected from `base.text` section:

| Variable | Hex | Purpose | Theme Source |
|----------|-----|---------|--------------|
| `text_primary` | `#E8DEFF` | Bright text for accessible/active states | `base.text.text_primary` |
| `text_dim` | `#A89BC8` | Muted text for restricted states | `base.text.text_dim` |
| `text_warning` | `#DD9B4C` | Orange text for orphaned files | `base.text.text_warning` |
| `text_stencil_purple` | `#9040B0` | Purple text for stencil paths | `base.text.text_stencil_purple` |
| `text_pushed_sync` | `#F17149` | Red-orange text for synced pushes | `base.text.text_pushed_sync` |
| `text_pushed_nosync` | `#C05838` | Dim red-orange for unsynced pushes | `base.text.text_pushed_nosync` |

**TreeDisplayConfig** — injected from `base.delegate` section:

| Variable | Value | Purpose | Theme Source |
|----------|-------|---------|--------------|
| `hover_color` | `#333A52` | Delegate hover overlay | `base.delegate.hover_color` |
| `hover_alpha` | 60 | Delegate hover overlay alpha | `base.delegate.hover_alpha` |
| `selection_alpha` | 100 | Delegate selection overlay alpha | `base.delegate.selection_alpha` |

**ListDisplayConfig** — injected from `base.text` section:

| Variable | Hex | Purpose |
|----------|-----|---------|
| `text_primary` | `#E8DEFF` | Bright text for all history entries |

---

## 7. Variable Resolution Flow

### Paint-Time Pipeline

```
┌──────────────────┐
│    NodeState      │  (from CORE Phase 3)
│                   │  Per-node: mounted, masked, revealed, pushed,
│                   │            container_orphaned, visibility
│                   │  Tree-context: has_pushed_descendant,
│                   │                has_direct_visible_child
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  Truth Table     │  Flat lookup: NodeState fields → state name
│  Resolution      │  Folders: visibility + has_pushed_desc + has_direct_vis
│  (no tree walk)  │  Files:   visibility + pushed + host_orphaned
└────────┬─────────┘
       │
       ▼
┌─────────────┐
│ state_styles │  TreeDisplayConfig.state_styles[state_name]
│  dict lookup │  → StateStyleClass(GradientClass, FontStyleClass)
└──────┬──────┘
       │
       ├──────────────────────────────────┐
       ▼                                  ▼
┌──────────────┐                   ┌──────────────┐
│ GradientClass│                   │FontStyleClass│
│ (pos1–pos4   │                   │ (font_var)   │
│  var names)  │                   └──────┬───────┘
└──────┬───────┘                          │
       │                                  ▼
       ▼                           ┌──────────────┐
┌──────────────────┐                │  Font lookup │
│ *_theme.json      │                │  local_host  │
│ local_host.       │                │  .fonts (or  │
│  state_colors     │                │  _scope_     │
│ (or _scope_       │                │  resolved)   │
│  resolved for     │                │  → weight,   │
│  scope panel)     │                │    italic,   │
│ var → hex         │                │    text_color│
└──────┬────────────┘                └──────┬───────┘
       ▼                                  │
┌──────────────┐                          │
│ QLinearGrad  │                          │
│ (4 QColors   │                          │
│  at 0.0,     │                          │
│  0.25, 0.50, │                          │
│  0.75)       │                          │
└──────┬───────┘                          │
       │                                  │
       ▼                                  ▼
┌──────────────────────────────────────────────┐
│  Delegate.paint()                             │
│  fillRect(gradient) + setText(font props)     │
└──────────────────────────────────────────────┘
```

### Selected State Application

```
After StateStyleClass lookup, before gradient construction:

IF node is selected:
    gradient.pos2 → "selected"
    gradient.pos3 → "selected"
    (pos1 and pos4 unchanged — preserves state identity)
```

---

## 8. Focus & Selection Suppression

Three mechanisms work together to prevent Windows accent color bleed on tree selection:

### QPalette.Highlight Override

`gui/__init__.py` overrides `QPalette.Highlight` for both `Active` and `Inactive` color groups to `#6366F1` (indigo) immediately after `setStyle("Fusion")`. This prevents the Windows system accent color from leaking through any Qt widget that reads the palette highlight role.

### QSS Branch Indicator Transparency

`gui/style_engine.py` sets `background: transparent` on `QTreeView::branch`, `QTreeView::branch:selected`, and `QTreeView::branch:hover`. Without these rules, the expand/collapse arrow column paints the palette highlight color behind selected/hovered rows.

### Focus Rect Suppression

`gui/delegates.py` — `TreeStyleDelegate.paint()` unconditionally clears `QStyle.StateFlag.State_HasFocus` from the option state before any painting. This prevents Qt from drawing a dotted focus rectangle over tree items. The suppression applies to all columns (name, checkboxes, symbols).

---

## 9. EXCEPTION Legacy Mapping

### Why EXCEPTION Was Eliminated

The old architecture had three separate tree contexts (PROJECT, EXCEPTION, SCOPE) with independent style systems. The EXCEPTION context used unique state names (`exception`, `container`, `pending_push`, `pending_pull`, `pending_remove`) that don't exist in the unified NodeState model.

**Key simplification:** File operations (push/pull/remove) are now **instant** — no staging states. The `exception` flag (intent to push) is replaced by immediate `docker cp` execution.

### Old → New State Correspondence

| Old State | Old Context | New State | Notes |
|-----------|-------------|-----------|-------|
| E1: folder `unmarked` hidden | EXCEPTION | FI1: `FILE_HIDDEN` | Folder/file distinction removed for visual |
| E2: folder `unmarked` visible | EXCEPTION | FI2: `FILE_VISIBLE` | |
| E3: file `unmarked` hidden | EXCEPTION | FI1: `FILE_HIDDEN` | Same visual as E1 |
| E4: file `unmarked` visible | EXCEPTION | FI2: `FILE_VISIBLE` | Same visual as E2 |
| E5: file `exception` hidden | EXCEPTION | — (eliminated) | `exception` flag removed; push is instant |
| E6: file `exception` visible | EXCEPTION | — (eliminated) | `exception` flag removed; push is instant |
| E7: file `pushed` hidden | EXCEPTION | FI5: `FILE_PUSHED` | Direct mapping |
| E8: file `pushed` visible | EXCEPTION | — (collapsed) | Push redundant when visible; renders as FILE_VISIBLE |
| E9: file `container` hidden | EXCEPTION | — (eliminated) | Container discovery removed |
| E10: file `container` visible | EXCEPTION | — (eliminated) | Container discovery removed |
| E11–E16: pending states | EXCEPTION | — (eliminated) | No staging; operations are instant |
| S1: mount_root `mounted` visible | SCOPE | F3: `FOLDER_MOUNTED` | "mounted" IS "accessible" in CORE |
| S2: normal `unmarked` visible | SCOPE | F2: `FOLDER_VISIBLE` | Same gradient colors |
| S3: `revealed` visible | SCOPE | F8: `FOLDER_REVEALED` | Same gradient colors |
| S4: `masked` virtual | SCOPE | F6/F7: `FOLDER_MASKED_REVEALED` or `FOLDER_MASKED_MIRRORED` | Split into 2 states by direct child check |

### Eliminated Concepts

| Old Concept | Replaced By | Reason |
|-------------|-------------|--------|
| `exception` flag | Instant push (`pushed=True`) | No staging needed |
| `container` state | — (removed) | No tool exists to discover container-only files |
| `pending_push/pull/remove` | — (removed) | File operations execute immediately |
| `FileState` enum | `NodeState.pushed` + `NodeState.container_orphaned` | Simplified to boolean flags |
| `bright_text` flag | — (absorbed into FontStyleClass) | Per-context text color variation eliminated |
| `TreeContext.SCOPE` text colors | Shared font variables | ScopeView uses same visual system as LocalHost |

### TreeContext.SCOPE Note

> `TreeContext.SCOPE` — now wired via `TreeDisplayConfig(panel="scope")`. The scope panel reads from `_scope_resolved` (deep-merge of `scope` over `local_host` sections in the consolidated `*_theme.json`). Per-panel differentiation is achieved by overriding keys in the `scope.state_colors` and `scope.fonts` sections — empty sections inherit all values from `local_host`.
