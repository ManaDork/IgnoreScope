# Theme Color Sampling Workflow

> **Architecture Blueprint** — canonical workflow for applying color changes from reference images to the IgnoreScope theme system.

---

## When to Use

When the user provides a reference image with numbered/annotated color targets, extract the actual colors before writing any code or JSON.

---

## Workflow

### 1. Identify Numbered Elements

Map each numbered annotation to its GUI element:
- Node state colors (row gradients)
- Panel backgrounds (dock gradients)
- Headers, borders, text fields
- Widget-specific areas (pattern list, config viewer)

### 2. Extract Colors from Image

For each numbered element, eyedrop the hex color from the reference image. Report the full table back to the user before applying:

```
| # | Element              | Extracted Hex |
|---|----------------------|---------------|
| 1 | Pushed File Node     | #F17149       |
| 2 | Revealed Folder Node | #DD9B4C       |
...
```

### 3. Map Colors to Theme Data Locations

Each extracted color maps to a specific key in `glassmorphism_v1_theme.json`:

#### Node State Colors → `local_host.state_colors` / `scope.state_colors`

| Visual Element       | JSON Key                      |
|----------------------|-------------------------------|
| Pushed File Node     | `config.pushed`               |
| Revealed Folder Node | `config.revealed`             |
| Mount Folder Node    | `config.mount`                |
| Masked Folder Node   | `config.masked`               |
| Virtual Node         | `virtual.volume`, `virtual.auth` |
| Accessible Folder    | `visibility.accessible`       |
| Restricted Folder    | `visibility.restricted`       |
| Virtual Structural   | `visibility.virtual`          |

#### Panel Backgrounds → `gradients` section

| Visual Element        | JSON Key                          |
|-----------------------|-----------------------------------|
| LocalHost panel bg    | `gradients.dock_panel.stops`      |
| Scope panel bg        | `gradients.scope_dock_panel.stops`|
| Main window bg        | `gradients.main_window.stops`     |
| Config panel bg       | `gradients.config_panel.stops`    |
| Status bar bg         | `gradients.status_bar.stops`      |

Gradient stops use **palette variable names**, not inline hex. Define the hex in `base.palette`, then reference by name.

#### UI Chrome → `base.ui` + `config_panel` sections

| Visual Element         | JSON Key                           |
|------------------------|------------------------------------|
| Header background      | `base.ui.surface_bg` (QSS: `QHeaderView::section`, `QDockWidget::title`) |
| Config panel header    | `config_panel.header_bg` → references `base.ui` key |
| Pattern list bg        | `config_panel.pattern_bg` → references `base.ui` key |
| Mount text field bg    | `base.ui.panel_bg` (QSS: `QLineEdit`) |
| Menu bar bg            | `base.ui.panel_bg` (QSS: `QMenuBar`) |
| Border color           | `base.ui.border`                   |

#### Text Colors → `base.text`

| Visual Element         | JSON Key              |
|------------------------|-----------------------|
| Pushed file text       | `text_pushed_sync`    |
| Virtual node text      | `text_virtual_purple` |
| Warning/orphan text    | `text_warning`        |
| Primary text           | `text_primary`        |
| Muted/dim text         | `text_dim`            |

#### Delegate Overlays → `base.delegate`

| Visual Element         | JSON Key              |
|------------------------|-----------------------|
| Selection highlight    | `selection_color`     |
| Selection opacity      | `selection_alpha`     |
| Hover highlight        | `hover_color`         |
| Hover opacity          | `hover_alpha`         |
| Row gradient opacity   | `row_gradient_opacity`|

### 4. Confirm with User

Present the extracted colors + mapped locations. Let user correct before applying.

### 5. Apply to JSON

Update `glassmorphism_v1_theme.json` only. No Python code changes needed for color values — the theme engine reads everything from JSON.

### 6. Update Tests

Tests that assert specific hex values need updating after palette changes. These are in:
- `IgnoreScope/tests/test_gui/test_style_engine.py`
- `IgnoreScope/tests/test_gui/test_display_config.py`

---

## Theme File Structure

```
glassmorphism_v1_theme.json
├── _meta                    # theme name + version
├── base
│   ├── palette              # all named hex colors (gradient stops reference these)
│   ├── ui                   # semantic UI colors (QSS template references these)
│   ├── text                 # text color definitions (font vars reference these)
│   └── delegate             # selection/hover overlays + row opacity
├── gradients
│   ├── main_window          # app background gradient (3-stop vertical)
│   ├── dock_panel           # LocalHost dock gradient (cooler blue-gray)
│   ├── scope_dock_panel     # Scope dock gradient (warmer purple, separate from local_host)
│   ├── config_panel         # Desktop Docker Scope Config gradient
│   └── status_bar           # status bar gradient
├── local_host
│   ├── state_colors         # row gradient colors for LocalHost tree (16 keys)
│   └── fonts                # font definitions for LocalHost tree
├── scope
│   ├── state_colors         # row gradient colors for Scope tree (deep-merged over local_host)
│   └── fonts                # font overrides for Scope tree
└── config_panel             # Desktop Docker Scope Config panel styling (refs base.ui keys)
```

### State Colors Keys (16 per panel)

```
visibility.accessible        # STATE — content accessible to container
visibility.restricted        # STATE — content restricted from container
visibility.virtual           # STATE — structural intermediate / container-only

config.mount                 # mount root / active mount
config.masked                # content excluded from container
config.revealed              # content restored under mask
config.pushed                # docker cp'd content

inherited.masked             # inherited mask from ancestor
inherited.revealed           # inherited reveal from ancestor
inherited.virtual_auth       # virtual auth path
inherited.virtual_volume     # virtual volume path

ancestor.visible             # ancestor has visible descendants

virtual.volume               # volume virtual node
virtual.auth                 # auth virtual node

status.warning               # attention-required state
ui.selected                  # delegate selection overlay
```

---

## Code Locations

| What | File | How It Reads Theme |
|------|------|--------------------|
| Palette override | `gui/__init__.py` | `QPalette.Highlight` set to `#6366F1` (Active + Inactive) after `setStyle("Fusion")` |
| Theme loader | `gui/style_engine.py` | `_load_consolidated_theme()` — validates, deep-merges scope |
| QSS builder | `gui/style_engine.py` | `build_stylesheet()` — reads `base.ui`, `config_panel` |
| Gradient resolver | `gui/style_engine.py` | `_resolve_gradient_color()` — palette → ui → hex fallback |
| Folder state derivation | `gui/display_config.py` | `derive_gradient()` — visibility STATE + METHOD flags → GradientClass |
| File state derivation | `gui/display_config.py` | `derive_file_style()` — visibility STATE + flags → GradientClass |
| Tree row colors | `gui/display_config.py` | `TreeDisplayConfig(panel=)` — reads `local_host` or `_scope_resolved` |
| Dock gradient assignment | `gui/app.py` | `_gradient_name = "dock_panel"` (local_host) |
| Dock gradient assignment | `gui/app.py` | `_gradient_name = "scope_dock_panel"` (scope) |
| Config panel styles | `gui/style_engine.py` | `config_panel_style()` — resolves var names → hex |

---

## Visibility → State Colors Mapping

Visibility is pure **STATE** — what the container sees. The 3 state values map directly to `visibility.*` JSON keys:

| Visibility Value | JSON Key | Meaning |
|-----------------|----------|---------|
| `"accessible"` | `visibility.accessible` | Content accessible to container (mounted or revealed) |
| `"restricted"` | `visibility.restricted` | Content restricted from container (hidden, masked, orphaned) |
| `"virtual"` | `visibility.virtual` | Structural intermediate or container-only node |

METHOD flags (`is_masked`, `is_revealed`, `is_mount_root`, etc.) drive the P3/P4 accent positions in the gradient, selecting from `config.*`, `inherited.*`, `virtual.*`, and `ancestor.*` keys.
