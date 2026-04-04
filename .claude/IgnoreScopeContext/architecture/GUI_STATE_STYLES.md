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
              tree_state_style.json lookup
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

15 tree states (8 folder + 7 file) + 2 selected overrides.

GUI reads CORE-computed NodeState fields via flat truth tables — no tree walking in the GUI.
Folder states read: `visibility` + `has_pushed_descendant` + `has_direct_visible_child`.
File states read: `visibility` + `pushed` + `host_orphaned`.

### 3.1 Folder States (8)

8 states derived from CORE visibility + tree-context fields.

| ID | State Name | Truth Table | GradientClass(pos1, pos2, pos3, pos4) | FontStyleClass |
|----|-----------|-------------|---------------------------------------|---------------|
| F1 | `FOLDER_HIDDEN` | vis=hidden | `(background, background, background, background)` | `muted` |
| F2 | `FOLDER_VISIBLE` | vis=visible | `(background, background, visible, visible)` | `default` |
| F3 | `FOLDER_MOUNTED_MASKED` | vis=masked, has_pushed_desc=F | `(mounted, mounted, masked, masked)` | `muted` |
| F4 | `FOLDER_MOUNTED_MASKED_PUSHED` | vis=masked, has_pushed_desc=T | `(mounted, mounted, masked, pushed)` | `default` |
| F5 | `FOLDER_MASKED_REVEALED` | vis=virtual, has_direct_vis=T | `(masked, masked, hidden, revealed)` | `default` |
| F6 | `FOLDER_MASKED_MIRRORED` | vis=virtual, has_direct_vis=F | `(masked, masked, virtual, virtual)` | `default` |
| F7 | `FOLDER_REVEALED` | vis=revealed | `(revealed, revealed, visible, visible)` | `default` |
| F8 | `FOLDER_PUSHED_ANCESTOR` | vis=hidden, has_pushed_desc=T | `(background, background, background, pushed)` | `default` |

**Folder truth table** (GUI reads NodeState fields, no tree walking):

```
visibility | has_pushed_desc | has_direct_vis | -> State Name                  | Font
---------- | --------------- | -------------- | ------------------------------ | -------
hidden     | T               | -              | FOLDER_PUSHED_ANCESTOR         | default
hidden     | -               | -              | FOLDER_HIDDEN                  | muted
visible    | -               | -              | FOLDER_VISIBLE                 | default
masked     | F               | -              | FOLDER_MOUNTED_MASKED          | muted
masked     | T               | -              | FOLDER_MOUNTED_MASKED_PUSHED   | default
virtual   | -               | T              | FOLDER_MASKED_REVEALED         | default
virtual   | -               | F              | FOLDER_MASKED_MIRRORED         | default
revealed   | -               | -              | FOLDER_REVEALED                | default
```

"-" = field not checked for this state (any value matches).

**Notes:**

- **FOLDER_VISIBLE** = "mounted" in CORE. vis=visible is produced ONLY when mounted=T. The checkbox column provides "is this node a mount root?" distinction separately.
- **FOLDER_PUSHED_ANCESTOR** = hidden folder (not under any mount) with a pushed descendant. Distinct from F4 (FOLDER_MOUNTED_MASKED_PUSHED) which is a masked folder inside a mount. F8 uses background base with pushed accent; F4 uses mounted+masked base.
- **FOLDER_MOUNTED_MASKED** vs **FOLDER_MOUNTED_MASKED_PUSHED**: Both vis=masked. Pushed descendant presence distinguishes empty masked zone from one containing docker cp content.
- **FOLDER_MASKED_REVEALED** vs **FOLDER_MASKED_MIRRORED**: Both vis=virtual. Direct visible child distinguishes "parent of visible content" from "structural mkdir-p intermediate."
- F5 gradient is **user-confirmed**: `(masked, masked, hidden, revealed)` — masked identity left, revealed children indicated right.
- Old states F2 (`FOLDER_VISIBLE` with mounted=F), F3 (`FOLDER_VISIBLE_MIRRORED`), F5 (`FOLDER_MASKED` with mounted=F), F6 (`FOLDER_MASKED_REVEALED_CHILDREN` with mounted=F) eliminated — impossible or invalid under CORE's ancestor-derived flags.

### 3.2 File States (7)

7 states derived from CORE visibility + `pushed` + `host_orphaned` flags.

| ID | State Name | Truth Table | GradientClass(pos1, pos2, pos3, pos4) | FontStyleClass |
|----|-----------|-------------|---------------------------------------|---------------|
| FI1 | `FILE_HIDDEN` | vis=hidden, pushed=F | `(background, background, background, background)` | `muted` |
| FI2 | `FILE_VISIBLE` | vis=visible, pushed=F | `(background, background, visible, visible)` | `default` |
| FI3 | `FILE_MASKED` | vis=masked, pushed=F | `(background, background, hidden, hidden)` | `muted` |
| FI4 | `FILE_REVEALED` | vis=revealed, pushed=F | `(background, background, visible, revealed)` | `default` |
| FI5 | `FILE_PUSHED` | vis=masked, pushed=T, host_orphaned=F | `(pushed, pushed, hidden, hidden)` | `default` |
| FI6 | `FILE_HOST_ORPHAN` | vis=masked, pushed=T, host_orphaned=T | *(DEFERRED — `warn_soft` TBD)* | `italic` |
| FI7 | `FILE_CONTAINER_ORPHAN` | vis=orphaned | `(warning, warning, hidden, hidden)` | `italic` |

**File truth table** (GUI reads NodeState fields, no tree walking):

```
visibility | pushed | host_orph | -> State Name            | Font
---------- | ------ | --------- | ------------------------ | ------
hidden     | F      | -         | FILE_HIDDEN              | muted
visible    | F      | -         | FILE_VISIBLE             | default
masked     | F      | -         | FILE_MASKED              | muted
revealed   | F      | -         | FILE_REVEALED            | default
masked     | T      | F         | FILE_PUSHED              | default
masked     | T      | T         | FILE_HOST_ORPHAN         | italic  (DEFERRED)
orphaned   | (T)    | -         | FILE_CONTAINER_ORPHAN    | italic
```

"-" = field not checked (any value). `host_orphaned` only discriminates within pushed files.
`container_orphaned` is already encoded in vis=orphaned (TTFF matrix), so no separate column needed.

**Notes:**

- **FILE_MASKED** and **FILE_REVEALED** are new states — the old spec had no states for unpushed files in masked or revealed zones.
- **FILE_HOST_ORPHAN** is DEFERRED. The state exists in the design model but requires scoping decisions about scan coverage before implementation. Gradient uses `warn_soft` (amber, visually distinct from orange `warning`).
- **FILE_CONTAINER_ORPHAN** renamed from old `FILE_ORPHANED`. vis=orphaned implies pushed=T and container_orphaned=T (TTFF matrix).
- **Pushed redundancy rule:** When pushed=T AND visibility in {visible, revealed}, the push is redundant. GUI treats these as their base state (FILE_VISIBLE or FILE_REVEALED).
- Old FI4 (`FILE_PUSHED_VISIBLE`) and FI6 (`FILE_ORPHANED_VISIBLE`) eliminated — impossible or collapsed into base states.

### 3.3 Selected State Overrides

| Override | Applies To | Mechanism |
|----------|-----------|-----------|
| FOLDER_SELECTED | Any F1–F8 state | pos2 -> `selected`, pos3 -> `selected` |
| FILE_SELECTED | Any FI1–FI7 state | pos2 -> `selected`, pos3 -> `selected` |

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

### 5.1 tree_state_style.json

Color variables for tree panel GradientClass resolution. Each variable maps to a hex color from the Nord palette or state color definitions.

| Variable | Hex | Color Group | Source |
|----------|-----|-------------|--------|
| `background` | `#3B4252` | Neutral | `palette.polar_night_1` |
| `mounted` | `#3D4A3E` | Green | `state_colors.mounted` |
| `pushed` | `#3D4A3E` | Green | `state_colors.pushed` (same hex as mounted) |
| `masked` | `#4A3B42` | Red | `state_colors.masked` |
| `revealed` | `#4A4838` | Yellow | `state_colors.revealed` |
| `visible` | `#4C566A` | — | `visibility_colors.visible` |
| `virtual` | `#373E4D` | — | `visibility_colors.virtual` |
| `hidden` | `#2E3440` | — | `visibility_colors.hidden` |
| `warning` | `#D08770` | Warning | `palette.orange` |
| `selected` | `#5E81AC` | — | `delegate.selection_color` |

**Color groups** (semantic families):

- **Green** (mount/push): `mounted`, `pushed` — active content in container
- **Red** (mask): `masked` — content excluded from container
- **Yellow** (reveal): `revealed` — content restored under mask
- **Warning** (orphan): `warning` — attention-required state
- **Neutral**: `background` — no state / default

**Variable naming convention:** `warning`, `conflict`, and other color names describe **visual intent**, not state names. The same variable name (e.g., `warning`) may resolve to different hex values in different JSON configs — tree panels use `tree_state_style.json`, list panels use `list_style.json`. Each config file is an independent namespace.

### 5.2 list_style.json

Color variables for list panel (Session History) GradientClass resolution.

| Variable | Hex | Source |
|----------|-----|--------|
| `background` | `#3B4252` | `ui.panel_bg` |
| `selected` | `#5E81AC` | `ui.accent_secondary` |
| `warning` | `#EBCB8B` | `palette.yellow` |
| `destructive` | `#BF616A` | `palette.red` |

**Migration from theme.json dotted paths:**

| Old Reference | New Variable |
|---------------|-------------|
| `ui.panel_bg` | `background` |
| `ui.accent_secondary` | `selected` |
| `palette.yellow` | `warning` |
| `palette.red` | `destructive` |

---

## 6. Font Variable Reference

### 6.1 tree_state_font.json

Font variables for tree panel FontStyleClass resolution. All values use **variable indirection** — `text_color` references a variable name resolved by TreeDisplayConfig, not a direct hex value.

| Variable | Weight | Italic | text_color (variable) | Used By |
|----------|--------|--------|----------------------|---------|
| `default` | normal | false | `text_primary` | F2, F4–F8, FI2, FI4–FI5 |
| `muted` | normal | false | `text_dim` | F1, F3, FI1, FI3 |
| `italic` | normal | true | `text_warning` | FI6, FI7 |

**Note:** Text color is included in FontStyleClass to unify text rendering. The old TreeContext-based text color axis is absorbed: all tree contexts share the same font variables via their respective display configs.

### 6.2 list_font.json

Font variables for list panel (Session History) FontStyleClass resolution. Same variable indirection pattern.

| Variable | Weight | Italic | text_color (variable) |
|----------|--------|--------|----------------------|
| `default` | normal | false | `text_primary` |

### 6.3 One-Off Color Variables (Base Class Definitions)

The following hex colors are used in rendering but don't correspond to any gradient state variable. First pass: defined as class-level variables on the base DisplayConfig classes. JSON storage decisions deferred.

**TreeDisplayConfig base class:**

| Variable | Hex | Purpose | Source |
|----------|-----|---------|--------|
| `text_primary` | `#ECEFF4` | Bright text for visible/active states | `palette.snow_storm_2` |
| `text_dim` | `#616E88` | Muted text for hidden states | (custom, between snow_storm and polar_night) |
| `text_warning` | `#D08770` | Orange text for orphaned files | `palette.orange` |
| `hover_color` | `#4C566A` | Delegate hover overlay | `delegate.hover_color` (same hex as gradient `visible`) |
| `hover_alpha` | 60 | Delegate hover overlay alpha | `delegate.hover_alpha` |
| `selection_alpha` | 100 | Delegate selection overlay alpha | `delegate.selection_alpha` |

**ListDisplayConfig base class:**

| Variable | Hex | Purpose |
|----------|-----|---------|
| `text_primary` | `#ECEFF4` | Bright text for all history entries |

**Note:** `selected` (#5E81AC) is already a gradient state variable — only its alpha (100) is a one-off. `hover_color` shares its hex with the gradient `visible` variable but serves a different rendering purpose (overlay vs gradient stop).

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
┌──────────────┐                   │  Font JSON   │
│  Style JSON  │                   │  lookup      │
│  var → hex   │                   │  → weight,   │
│  resolution  │                   │    italic,   │
└──────┬───────┘                   │    text_color│
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
