# Consolidated Theme File — Technical Design

## Overview

Merge 5 visual JSON files into a single `{theme_name}_{version}_theme.json` with 5 sections. Remove all hardcoded hex fallbacks from Python. Add per-panel style differentiation via deep-merge and theme-driven ContainerRootPanel styling.

## Architecture

### Current Flow
```
theme.json ──────────────────→ StyleGui.__init__()
                                  ├─ palette, ui, text, delegate, gradients
                                  └─ build_stylesheet() uses ui/palette keys

tree_state_style.json ──→ BaseDisplayConfig.__init__()
tree_state_font.json  ──→    ├─ _color_vars dict
                              ├─ _font_vars dict
                              └─ text colors loaded from theme.json["text"]

display_config.py ───── hardcoded hex fallbacks (text_primary, hover_color, etc.)
style_engine.py  ───── hardcoded hex fallbacks (palette_color, ui_color, etc.)
```

### Target Flow
```
glassmorphism_v1_theme.json ──→ ThemeLoader.load()
    ├─ base       → StyleGui (palette, ui, text, delegate)
    ├─ gradients  → StyleGui (widget gradient defs)
    ├─ local_host → TreeDisplayConfig("local_host")
    │                 ├─ state_colors (resolved)
    │                 └─ fonts (resolved)
    ├─ scope      → deep_merge(local_host, scope) → TreeDisplayConfig("scope")
    │                 ├─ state_colors (merged)
    │                 └─ fonts (merged)
    └─ config_panel → ContainerRootPanel + StyleGui.build_stylesheet()
                        ├─ header_bg, header_text
                        ├─ viewer_bg, viewer_text
                        └─ border

No hex literals in Python. Missing keys → KeyError at load time.
```

## Dependencies

### Internal
- `style_engine.py` — loads consolidated file, removes hex fallbacks
- `display_config.py` — receives resolved dicts, removes hex class defaults
- `list_display_config.py` — receives resolved dicts (same pattern)
- `container_root_panel.py` — reads config_panel styling
- `app.py` — passes panel name to display config constructors
- `local_host_view.py` / `scope_view.py` — may need config identity param

### External
- None

### Ordering
1. Define consolidated JSON schema + write initial file
2. ThemeLoader: parse consolidated file, deep-merge scope over local_host
3. StyleGui: load from ThemeLoader instead of theme.json directly
4. BaseDisplayConfig: accept resolved dicts instead of loading JSONs
5. TreeDisplayConfig: instantiate per-panel with identity
6. config_panel section → QSS template + ContainerRootPanel
7. Remove all Python hex literals
8. Remove old separate JSON files
9. Update tests
10. Architecture doc updates

## Key Changes

### Consolidated File Schema

```json
{
    "_meta": {
        "theme_name": "glassmorphism",
        "version": "v1"
    },
    "base": {
        "palette": {
            "base_0": "#0F0A1E",
            "...": "..."
        },
        "ui": {
            "window_bg": "#1A1035",
            "...": "..."
        },
        "text": {
            "text_primary": "#E8DEFF",
            "...": "..."
        },
        "delegate": {
            "selection_color": "#6366F1",
            "selection_alpha": 100,
            "hover_color": "#2D1F55",
            "hover_alpha": 60,
            "row_gradient_opacity": 242
        }
    },
    "gradients": {
        "main_window": { "...": "..." },
        "dock_panel": { "...": "..." },
        "config_panel": { "...": "..." },
        "status_bar": { "...": "..." }
    },
    "local_host": {
        "state_colors": {
            "visibility.background": "#1A1035",
            "config.mount": "#00E5CC",
            "...": "..."
        },
        "fonts": {
            "default": { "weight": "normal", "italic": false, "text_color": "text_primary" },
            "...": "..."
        }
    },
    "scope": {
        "state_colors": {},
        "fonts": {}
    },
    "config_panel": {
        "header_bg": "surface_bg",
        "header_text": "accent_primary",
        "viewer_bg": "panel_bg",
        "viewer_text": "text_primary",
        "border": "border"
    }
}
```

**scope deep-merge**: At load time, `scope.state_colors` is merged over a copy of `local_host.state_colors`. Same for `fonts`. Empty scope sections = identical to local_host.

**config_panel values**: Reference `ui` key names (not hex). Resolved at stylesheet build time via `ui_color()`.

### ThemeLoader (new, in style_engine.py)

```python
def _load_consolidated_theme(path: Path) -> dict:
    """Load consolidated theme file. Validate required sections.
    Deep-merge scope over local_host.
    """
    with open(path) as f:
        raw = json.load(f)

    required = {"base", "gradients", "local_host", "config_panel"}
    missing = required - raw.keys()
    if missing:
        raise ValueError(f"Theme file missing sections: {missing}")

    # Deep-merge scope over local_host
    local = raw["local_host"]
    scope_raw = raw.get("scope", {})
    raw["_scope_resolved"] = {
        "state_colors": {**local.get("state_colors", {}),
                         **scope_raw.get("state_colors", {})},
        "fonts": {**local.get("fonts", {}),
                  **scope_raw.get("fonts", {})},
    }
    return raw
```

### StyleGui Changes

```python
class StyleGui:
    def __init__(self):
        theme_path = self._find_theme_file()
        self._theme_data = _load_consolidated_theme(theme_path)

        # Map old access patterns to new structure
        self._theme = {
            "palette": self._theme_data["base"]["palette"],
            "ui": self._theme_data["base"]["ui"],
            "text": self._theme_data["base"]["text"],
            "delegate": self._theme_data["base"]["delegate"],
            "gradients": self._theme_data["gradients"],
        }
        # ... existing init continues

    def _find_theme_file(self) -> Path:
        """Find *_theme.json in gui directory."""
        gui_dir = Path(__file__).parent
        candidates = list(gui_dir.glob("*_theme.json"))
        if not candidates:
            raise FileNotFoundError("No *_theme.json found in gui/")
        return candidates[0]  # single theme for now

    def palette_color(self, key: str) -> str:
        return self._theme["palette"][key]  # KeyError if missing — no fallback

    def ui_color(self, key: str) -> str:
        return self._theme["ui"][key]  # KeyError if missing — no fallback

    def config_panel_style(self) -> dict[str, str]:
        """Resolve config_panel section values to hex via ui lookup."""
        raw = self._theme_data.get("config_panel", {})
        return {k: self.ui_color(v) for k, v in raw.items()}
```

### BaseDisplayConfig Changes

```python
class BaseDisplayConfig:
    def __init__(
        self,
        state_defs: dict,
        color_vars: dict[str, str],   # pre-resolved, not a filename
        font_vars: dict[str, dict],   # pre-resolved, not a filename
        text_colors: dict[str, str],  # from base.text section
    ):
        self._color_vars = color_vars
        self._font_vars = font_vars
        # Apply text colors as attributes (replaces theme.json loading)
        for attr, value in text_colors.items():
            setattr(self, attr, value)
        self.state_styles = self._build_state_styles(state_defs)
```

No more `text_primary: str = "#E8DEFF"` class defaults. All values injected from JSON.

### TreeDisplayConfig Per-Panel

```python
class TreeDisplayConfig(BaseDisplayConfig):
    def __init__(self, panel: str = "local_host"):
        sg = StyleGui.instance()
        theme = sg._theme_data
        if panel == "scope":
            resolved = theme["_scope_resolved"]
        else:
            resolved = theme["local_host"]

        super().__init__(
            _TREE_STATE_DEFS,
            color_vars=resolved["state_colors"],
            font_vars=resolved["fonts"],
            text_colors=theme["base"]["text"],
        )
```

### QSS config_panel Integration

```python
# In build_stylesheet(), resolve config_panel vars:
cp = self._theme_data.get("config_panel", {})
config_header_bg = self.ui_color(cp.get("header_bg", "surface_bg"))
config_header_text = self.ui_color(cp.get("header_text", "accent_primary"))
config_viewer_bg = self.ui_color(cp.get("viewer_bg", "panel_bg"))
config_viewer_text = self.ui_color(cp.get("viewer_text", "text_primary"))
config_border = self.ui_color(cp.get("border", "border"))
```

Template entries for `#configHeaderFrame`, `#configHeaderLabel`, `#configViewerText` become `{config_header_bg}`, `{config_header_text}`, etc.

### Modified Files

| File | Change |
|------|--------|
| `style_engine.py` | ThemeLoader, StyleGui refactored to consolidated file, hex fallbacks removed |
| `display_config.py` | BaseDisplayConfig accepts dicts, TreeDisplayConfig per-panel, hex defaults removed |
| `list_display_config.py` | Same pattern as TreeDisplayConfig (receives dicts) |
| `container_root_panel.py` | Reads config_panel styles from StyleGui |
| `app.py` | Passes panel identity to display config constructors |
| `local_host_view.py` | Passes "local_host" to TreeDisplayConfig |
| `scope_view.py` | Passes "scope" to TreeDisplayConfig |
| `glassmorphism_v1_theme.json` | New consolidated file |

### Removed Files

| File | Reason |
|------|--------|
| `theme.json` | Consolidated into `*_theme.json` |
| `tree_state_style.json` | Consolidated into `local_host.state_colors` |
| `tree_state_font.json` | Consolidated into `local_host.fonts` |
| `list_style.json` | Kept for now (list panel not wired) |
| `list_font.json` | Kept for now (list panel not wired) |

### New Files

| File | Purpose |
|------|---------|
| `IgnoreScope/gui/glassmorphism_v1_theme.json` | Consolidated theme |

## Interfaces & Data

### ThemeLoader Input/Output
**Input:** Path to `*_theme.json`
**Output:** Parsed dict with `_scope_resolved` deep-merge applied

### BaseDisplayConfig Constructor
**Input:** `state_defs`, `color_vars` (dict), `font_vars` (dict), `text_colors` (dict)
**Output:** Configured instance with `state_styles` and text color attributes

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| Keep separate files, add an index | Still requires multi-file edits for palette shifts |
| YAML instead of JSON | Adds a dependency. JSON is already the project standard |
| Python dataclass config | Mixes data and code. JSON keeps theme swappable |
| Runtime chain lookup for scope fallback | Adds indirection. Deep-merge at load is simpler and debuggable |

## Risks

| Risk | Mitigation |
|------|-----------|
| Breaking existing display configs that load from filenames | Phased: keep old constructors working during transition, remove after validation |
| Consolidated file grows unwieldy | Sections are self-contained. Theme name in `_meta` for identification |
| Scope deep-merge hides unexpected inheritance | Log merged keys at debug level. Tests verify merge behavior |

## Architecture Doc Impact

| Document | Update Required |
|----------|----------------|
| `GUI_STATE_STYLES.md` | Update Section 5 (Color Variable Reference) for consolidated source. Add per-panel differentiation docs |
| `DATAFLOWCHART.md` | Update theme loading flow diagram |
| `GUI_STRUCTURE.md` | Note config_panel theme integration |
