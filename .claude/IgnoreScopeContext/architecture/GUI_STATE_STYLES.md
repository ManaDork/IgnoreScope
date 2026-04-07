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
GradientClass("masked", "masked", "hidden", "revealed")
                  │         │         │          │
                  ▼         ▼         ▼          ▼
              *_theme.json local_host.state_colors lookup
                  │         │         │          │
                  ▼         ▼         ▼          ▼
              #4A3B42   #4A3B42   #2E3440    #4A4838
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

**StateStyleClass** is the complete visual recipe for one node state. It composes a GradientClass (background gradient) with a FontStyleClass (text properties). Each of the 15 tree states and 5 list states maps to exactly one StateStyleClass.

### FontStyleClass

```
FontStyleClass(font_var)
```

`font_var` is a variable name resolved from a font JSON file. Defines text weight, italic, and text color. See Section 6 for variable tables.

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

20 tree states (12 folder + 8 file) + 2 selected overrides.

Folder states derived via `derive_gradient()` formula — no hand-built gradients or lookup tables.
File states derived via `derive_file_style()` formula — simplified 4-position model (no ancestor tracking).

### Gradient Formula

```
P1 = visibility     what the container sees     (visible, hidden, mirrored, background, co)
P2 = context         parent/inherited visibility (visible, hidden, background, co)
P3 = ancestor        descendant tracking         (ancestor.visible, or falls to P4)
P4 = config          direct/inherited action     (config.mount, config.revealed, inherited.masked, virtual.*)

Fallback chain: P3 → P4 → P1 (when no ancestor/config, position uses visibility color)
```

**P1-P2 relationship:** P2 mirrors P1 except REVEALED (P1=visible, P2=hidden — visible in hidden context).

### Color Variable System (categorical)

| Category | Variables | Position | Purpose |
|----------|----------|----------|---------|
| `visibility.*` | `.visible`, `.hidden`, `.virtual`, `.background`, `.container_only` | P1, P2 | What the container sees |
| `config.*` | `.mount`, `.revealed`, `.pushed` | P4 | User's direct config action |
| `inherited.*` | `.masked` | P4 | Ancestor pattern covers this node |
| `ancestor.*` | `.visible` | P3 | Has visible descendant (pushed or revealed) |
| `virtual.*` | `.volume`, `.auth` | P4 | Non-filesystem accent |
| `status.*` | `.warning` | P4 | Status indicators |
| `ui.*` | `.selected` | P2, P3 | Selection override |

### 3.1 Folder States (12)

Derived via `derive_gradient()` from node properties:

| State | P1 | P2 | P3 | P4 | Font |
|---|---|---|---|---|---|
| FOLDER_HIDDEN | background | background | — | — | muted |
| FOLDER_VISIBLE | visible | visible | — | — | default |
| FOLDER_MOUNTED | visible | visible | — | config.mount | default |
| FOLDER_MOUNTED_REVEALED | visible | visible | ancestor.visible | config.mount | default |
| FOLDER_MASKED | hidden | hidden | — | inherited.masked | muted |
| FOLDER_REVEALED | visible | hidden | — | config.revealed | default |
| FOLDER_MIRRORED | mirrored(hidden) | hidden | — | — | virtual_mirrored |
| FOLDER_MIRRORED_REVEALED | mirrored(hidden) | hidden | ancestor.visible | — | virtual_mirrored |
| FOLDER_VIRTUAL_VOLUME | mirrored(virtual) | virtual | — | virtual.volume | virtual_volume |
| FOLDER_VIRTUAL_AUTH | mirrored(virtual) | virtual | — | virtual.auth | virtual_auth |
| FOLDER_PUSHED_ANCESTOR | background | background | ancestor.visible | — | default |
| FOLDER_CONTAINER_ONLY | co | co | — | — | italic |

"—" = falls to next in chain (P3→P4→P1).

**Key distinctions:**

- **MOUNTED vs VISIBLE:** Mount root gets config.mount accent (greenish). Non-mount visible folders are neutral.
- **MIRRORED vs VIRTUAL_VOLUME/AUTH:** Mirrored = structural host directory (hidden background, white text). Volume/Auth = non-filesystem entry (virtual accent + purple text).
- **REVEALED P2=hidden:** Visible in hidden context — punch-through shows as visible left fading into hidden context.

### 3.2 File States (8)

Derived via `derive_file_style()` from node properties. Simplified model parallel to `derive_gradient()`:

```
P1 = visibility     what the container sees     (visible, hidden, container_only)
P2 = background     always visibility.background (no parent context for files)
P3 = background     always visibility.background (no ancestor tracking for files)
P4 = config/status  pushed accent or warning     (config.pushed, status.warning, or falls to P2)

Font: container_only/orphaned → "italic", hidden/masked (not pushed) → "muted", else → "default"
Host orphan: gradient=None (DEFERRED — blocked on core orphan detection)
```

| ID | State Name | Condition | GradientClass | Font |
|----|-----------|-----------|---------------|------|
| FI1 | `FILE_HIDDEN` | vis=hidden, pushed=F | `(vis.hidden, vis.bg, vis.bg, vis.bg)` | `muted` |
| FI2 | `FILE_VISIBLE` | vis=visible | `(vis.visible, vis.bg, vis.bg, vis.bg)` | `default` |
| FI3 | `FILE_MASKED` | vis=masked, pushed=F | `(vis.hidden, vis.bg, vis.bg, vis.bg)` | `muted` |
| FI4 | `FILE_REVEALED` | vis=revealed | `(vis.visible, vis.bg, vis.bg, vis.bg)` | `default` |
| FI5 | `FILE_PUSHED` | pushed=T | `(vis.hidden, vis.bg, vis.bg, cfg.pushed)` | `default` |
| FI6 | `FILE_HOST_ORPHAN` | pushed=T, host_orphaned=T | *(DEFERRED)* | `italic` |
| FI7 | `FILE_CONTAINER_ORPHAN` | vis=orphaned | `(vis.hidden, vis.bg, vis.bg, status.warning)` | `italic` |
| FI8 | `FILE_CONTAINER_ONLY` | vis=container_only | `(vis.co, vis.bg, vis.bg, vis.bg)` | `italic` |

FILE_MASKED and FILE_HIDDEN share the same gradient — font color may be the primary differentiator (TBD). FILE_REVEALED and FILE_VISIBLE similarly share gradients. Both kept as separate states for future font color distinction. Pushed file special treatment deferred.

### 3.3 Selected State Overrides

| Override | Applies To | Mechanism |
|----------|-----------|-----------|
| FOLDER_SELECTED | Any folder state | pos2 -> `ui.selected`, pos3 -> `ui.selected` |
| FILE_SELECTED | Any file state | pos2 -> `ui.selected`, pos3 -> `ui.selected` |

Selected overrides modify the base state at paint time — not separate StateStyleClass entries.

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

**Variable resolution:** History states use `list_style.json` for color variables and `list_font.json` for font variables (separate from tree panel JSONs).

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

Color variables for tree panel GradientClass resolution. Stored in the consolidated `*_theme.json` under `local_host.state_colors`. Scope panels inherit these values via deep-merge (scope overrides merge on top of local_host at load time).

| Variable | Hex | Category | Purpose |
|----------|-----|----------|---------|
| `visibility.background` | `#1A1035` | Visibility | Default/background |
| `visibility.visible` | `#2D1F55` | Visibility | Container sees this node |
| `visibility.hidden` | `#0F0A1E` | Visibility | Container cannot see |
| `visibility.virtual` | `#1E1240` | Visibility | Structural/virtual path |
| `visibility.container_only` | `#150E2E` | Visibility | Container-only node |
| `config.mount` | `#00E5CC` | Config | Mount root accent |
| `config.masked` | `#FF6B9D` | Config | Masked by pattern |
| `config.revealed` | `#FFB15D` | Config | Revealed under mask |
| `config.pushed` | `#8B5CF6` | Config | Pushed file accent |
| `inherited.masked` | `#D94A7B` | Inherited | Ancestor pattern covers |
| `inherited.revealed` | `#DE954B` | Inherited | Ancestor reveal |
| `inherited.virtual_auth` | `#7C4DFF` | Inherited | Virtual auth inherited |
| `inherited.virtual_volume` | `#7C4DFF` | Inherited | Virtual volume inherited |
| `ancestor.visible` | `#FFB15D` | Ancestor | Has visible descendant |
| `virtual.volume` | `#8B5CF6` | Virtual | Non-filesystem volume |
| `virtual.auth` | `#8B5CF6` | Virtual | Non-filesystem auth |
| `status.warning` | `#FFB15D` | Status | Attention-required |
| `ui.selected` | `#6366F1` | UI | Selection override |

**Color categories** (semantic families):

- **Config** (mount/mask/reveal/push): direct user actions on nodes
- **Inherited**: ancestor pattern coverage
- **Visibility**: what the container sees
- **Virtual**: non-filesystem entries
- **Status**: attention indicators
- **UI**: selection/interaction overlays

**Per-panel differentiation:** The `scope` section in the consolidated theme can override any `local_host` color. At load time, scope values are deep-merged over local_host. Empty scope = identical to local_host. TreeDisplayConfig accepts a `panel` param ("local_host" or "scope") to select the resolved color set.

### 5.2 list_style.json (standalone)

Color variables for list panel (Session History) GradientClass resolution. Still loaded from a standalone JSON file (list panel section deferred until session_history is wired to UI).

| Variable | Hex | Source |
|----------|-----|--------|
| `background` | `#231745` | `base.palette.base_2` |
| `selected` | `#6366F1` | `base.palette.accent_blue` |
| `warning` | `#FFCE5D` | `base.palette.accent_yellow` |
| `destructive` | `#FF7069` | `base.palette.accent_red` |

---

## 6. Font Variable Reference

### 6.1 Consolidated Theme — `local_host.fonts`

Font variables for tree panel FontStyleClass resolution. Stored in the consolidated `*_theme.json` under `local_host.fonts`. Scope panels inherit via deep-merge (same pattern as state_colors). All values use **variable indirection** — `text_color` references a variable name resolved by TreeDisplayConfig, not a direct hex value.

| Variable | Weight | Italic | text_color (variable) | Used By |
|----------|--------|--------|----------------------|---------|
| `default` | normal | false | `text_primary` | F2, F4–F8, FI2, FI4–FI5 |
| `muted` | normal | false | `text_dim` | F1, F3, FI1, FI3 |
| `italic` | normal | true | `text_warning` | FI6, FI7, FI8 |
| `virtual_mirrored` | normal | false | `text_primary` | F9, F10 |
| `virtual_volume` | normal | true | `text_virtual_purple` | F11 |
| `virtual_auth` | normal | true | `text_virtual_purple` | F12 |
| `pushed_sync` | normal | false | `text_pushed_sync` | *(unused placeholder — future pushed sync wiring)* |
| `pushed_nosync` | normal | false | `text_pushed_nosync` | *(unused placeholder — future pushed nosync wiring)* |

**Note:** Text color is included in FontStyleClass to unify text rendering. The old TreeContext-based text color axis is absorbed: all tree contexts share the same font variables via their respective display configs. `pushed_sync` and `pushed_nosync` are placeholder entries — font keys and theme colors exist but are not wired to any node state. They will be connected when pushed file sync-state tracking lands.

### 6.2 list_font.json

Font variables for list panel (Session History) FontStyleClass resolution. Same variable indirection pattern.

| Variable | Weight | Italic | text_color (variable) |
|----------|--------|--------|----------------------|
| `default` | normal | false | `text_primary` |

### 6.3 Text and Delegate Variables (Injected from Theme)

The following values are used in rendering but don't correspond to gradient state variables. All are injected from the consolidated `*_theme.json` at init time — no hardcoded hex defaults in Python.

**TreeDisplayConfig** (from `base.text` + `base.delegate`):

| Variable | Hex | Purpose | Source |
|----------|-----|---------|--------|
| `text_primary` | `#E8DEFF` | Bright text for visible/active states | `base.text.text_primary` |
| `text_dim` | `#A89BC8` | Muted text for hidden states | `base.text.text_dim` |
| `text_warning` | `#FFB15D` | Orange text for orphaned files | `base.text.text_warning` |
| `text_virtual_purple` | `#8B5CF6` | Purple text for virtual nodes | `base.text.text_virtual_purple` |
| `text_pushed_sync` | `#8B5CF6` | Pushed sync text (placeholder) | `base.text.text_pushed_sync` |
| `text_pushed_nosync` | `#6B4EC4` | Pushed nosync text (placeholder) | `base.text.text_pushed_nosync` |
| `hover_color` | `#2D1F55` | Delegate hover overlay | `base.delegate.hover_color` |
| `hover_alpha` | 60 | Delegate hover overlay alpha | `base.delegate.hover_alpha` |
| `selection_alpha` | 100 | Delegate selection overlay alpha | `base.delegate.selection_alpha` |

**ListDisplayConfig** (from `base.text`):

| Variable | Hex | Purpose |
|----------|-----|---------|
| `text_primary` | `#E8DEFF` | Bright text for all history entries |

**Note:** `ui.selected` (`#6366F1`) is a gradient state variable — only its alpha (100) is injected as `selection_alpha`. `hover_color` shares its hex with `visibility.visible` but serves a different rendering purpose (overlay vs gradient stop).

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
┌──────────────┐                   │  Theme fonts │
│  Theme state │                   │  lookup      │
│  color_vars  │                   │  → weight,   │
│  var → hex   │                   │    italic,   │
│  resolution  │                   │    text_color│
       │                           └──────┬───────┘
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

## 8. EXCEPTION Legacy Mapping

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
| S1: mount_root `mounted` visible | SCOPE | F2: `FOLDER_VISIBLE` | "mounted" IS "visible" in CORE |
| S2: normal `unmarked` visible | SCOPE | F2: `FOLDER_VISIBLE` | Same gradient colors |
| S3: `revealed` visible | SCOPE | F7: `FOLDER_REVEALED` | Same gradient colors |
| S4: `masked` virtual | SCOPE | F5/F6: `FOLDER_MASKED_REVEALED` or `FOLDER_MASKED_MIRRORED` | Split into 2 states by direct child check |

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

> `TreeContext.SCOPE` — defined with text colors in theme.json but currently unused by any view. The enum value and theme colors are retained during migration but not wired into the new style system. The unified FontStyleClass variables replace per-context text color logic.

---

## 9. Widget Gradient System

Separate from the delegate GradientClass system (Sections 1–8), the widget gradient system provides JSON-driven gradient backgrounds for QWidget subclasses.

### 9.1 Dataclasses

```
GradientStop(position, color, offset_px=0)
    position: 0.0–1.0 percentage along gradient line
    color:    theme var name or "#hex" direct
    offset_px: signed pixel nudge from computed position

WidgetGradientDef(type, stops, anchor, angle, center_x, center_y, radius, child_opacity)
    type:          "linear" or "radial"
    stops:         tuple[GradientStop, ...] — 2+ stops
    anchor:        "horizontal" or "vertical" (linear only)
    angle:         degrees offset from anchor baseline (linear only)
    center_x/y:    % of widget dimensions (radial only)
    radius:        % of smaller dimension (radial only)
    child_opacity: 0–255, controls child widget background transparency
```

### 9.2 JSON Schema (theme.json "gradients" section)

Each entry is a named gradient definition:

```json
{
    "gradients": {
        "gradient_name": {
            "type": "linear",
            "anchor": "vertical",
            "angle": 0,
            "child_opacity": 0,
            "stops": [
                { "pos": 0.0, "color": "palette_or_ui_var" },
                { "pos": 1.0, "color": "#hex_direct" }
            ]
        }
    }
}
```

Stop `color` resolution order:
1. `#hex` prefix → passthrough
2. `theme.palette[color]` → hex
3. `theme.ui[color]` → hex
4. Fallback → `palette.polar_night_0`

### 9.3 Active Gradient Definitions

| Name | Type | Anchor | Stops | Widget |
|------|------|--------|-------|--------|
| `main_window` | linear | vertical | 2 (top-lit, dark bottom) | QMainWindow (IgnoreScopeApp) |
| `dock_panel` | linear | vertical | 3 (glass card, lighter top edge) | QDockWidget (both docks) |
| `config_panel` | linear | vertical | 2 (subtle top-lit) | ContainerRootPanel |
| `status_bar` | linear | horizontal | 3 (center-bright bar) | QStatusBar |

### 9.4 GradientBackgroundMixin

Mixin class providing `paintEvent()` that paints the gradient before `super().paintEvent()`. Widgets set `_gradient_name` to a key from the gradients section.

```
class GradientBackgroundMixin:
    _gradient_name = ""
    paintEvent() → QPainter fills widget rect with resolved gradient → super().paintEvent()
```

MRO: Mixin must appear before QWidget subclass (e.g., `class MyWidget(GradientBackgroundMixin, QWidget)`).

### 9.5 Transparency Cascade

```
┌─────────────────────────────┐
│  Widget gradient             │  ← always opaque (painted by mixin)
│  ┌───────────────────────┐  │
│  │ Child widget bg        │  │  ← child_opacity: 0=transparent, 255=opaque
│  │  ┌─────────────────┐  │  │
│  │  │ Row gradient     │  │  │  ← row_gradient_opacity: 0=invisible, 255=opaque
│  │  │ (delegate state) │  │  │     Text/symbols always at full opacity
│  │  └─────────────────┘  │  │
│  └───────────────────────┘  │
└─────────────────────────────┘
```

- `child_opacity` (per-gradient, 0–255): Controls QSS `background-color` alpha for child widgets. At 0, children are transparent and the widget gradient shows through.
- `row_gradient_opacity` (theme.json delegate section, 0–255): Controls delegate row gradient painter opacity. At 242 (~95%), widget gradient subtly bleeds through row backgrounds. Text/symbols render at full opacity.

### 9.6 Separation from Delegate System

| Aspect | Widget Gradients (Section 9) | Delegate Gradients (Section 1) |
|--------|------------------------------|-------------------------------|
| Target | QWidget backgrounds | Tree/list row backgrounds |
| Model | WidgetGradientDef (N stops) | GradientClass (4 fixed stops) |
| Config | theme.json "gradients" section | state_style.json / list_style.json |
| Rendering | GradientBackgroundMixin.paintEvent() | GradientDelegate._paint_gradient() |
| Angles | Configurable anchor + angle | Always horizontal |
| Types | Linear + Radial | Linear only |
