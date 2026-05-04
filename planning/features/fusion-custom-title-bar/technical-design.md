# Technical Design: Fusion Custom Title Bar

## Overview

Replace the OS-drawn Windows title bar with a custom `GradientHeaderBar` widget that participates in the glassmorphism theme system. Unify all three header bar implementations (title bar, dock title bars, config panel header) under a single base widget.

## Architecture

### GradientHeaderBar (new base widget)

```
GradientHeaderBar(GradientBackgroundMixin, QWidget)
    _gradient_name: str          # theme JSON gradient key
    _label: QLabel               # header text
    _actions: QHBoxLayout        # right-aligned action buttons
    HEADER_HEIGHT: int = 36      # constant height (DPI-aware TBD)

    Signals:
        contextMenuRequested(QPoint)
        clicked()

    Methods:
        set_label_text(str)
        add_action_button(icon, tooltip, callback) -> QPushButton
        paintEvent()  # via GradientBackgroundMixin
        contextMenuEvent()  # emits signal
```

### CustomTitleBar (GradientHeaderBar subclass)

```
CustomTitleBar(GradientHeaderBar)
    _gradient_name = "title_bar"

    Buttons: minimize (─), maximize (□/❐), close (✕)
    Close hover: red background
    Maximize toggles between □ (restore) and ❐ (maximize)

    Methods:
        nativeEvent()         # WM_NCHITTEST for snap layouts + drag
        _on_minimize()        # window().showMinimized()
        _on_maximize_toggle() # toggle showMaximized/showNormal
        _on_close()           # window().close()
```

### Platform Abstraction

```
Windows-specific (Phase 2):
    nativeEvent() override on QMainWindow
    - WM_NCHITTEST → HTMAXBUTTON, HTCAPTION, HTCLIENT
    - Requires ctypes for win32 constants
    - DWM frame extension via dwmapi.DwmExtendFrameIntoClientArea

Future macOS (not implemented):
    NSWindow manipulation would go in a parallel platform module
    GradientHeaderBar itself is platform-agnostic
```

## Dependencies

### Internal
| Module | Interaction |
|--------|-------------|
| `gui/style_engine.py` | `GradientBackgroundMixin` base class, `WidgetGradientDef` loading |
| `gui/app.py` | Window flags, title bar injection, dock widget creation |
| `gui/container_root_panel.py` | Config panel header replacement |
| `gui/menus.py` | Menu bar styling coordination |
| `themes/glassmorphism_v1_theme.json` | New `title_bar` gradient entry, dock header gradient entries |

### External
| Dependency | Purpose |
|------------|---------|
| `ctypes` (stdlib) | Win32 API constants for WM_NCHITTEST |
| `dwmapi` (via ctypes) | DwmExtendFrameIntoClientArea for window shadow |

### Ordering
1. `GradientHeaderBar` must exist before `CustomTitleBar` (inheritance)
2. Theme JSON `title_bar` gradient must exist before widget instantiation
3. `QDockWidget.setTitleBarWidget()` must happen after dock creation in `app.py`
4. QSettings migration must handle existing saved layouts

## Key Changes

### New Files
| File | Purpose |
|------|---------|
| `gui/gradient_header_bar.py` | `GradientHeaderBar` base widget + `CustomTitleBar` subclass |
| `gui/win32_titlebar.py` | Windows-specific `nativeEvent` handler + DWM shadow helper |

### Modified Files
| File | Change |
|------|--------|
| `gui/app.py` | Set `FramelessWindowHint`, inject `CustomTitleBar`, replace dock title bars with `GradientHeaderBar`, disable dock floating, QSettings migration |
| `gui/container_root_panel.py` | Replace `configHeaderFrame` + eventFilter + `_header_height()` with `GradientHeaderBar` instance, collapse/expand uses `HEADER_HEIGHT` constant |
| `gui/style_engine.py` | Remove legacy QSS: `QDockWidget::title`, `QMenuBar` bg styling, `#configHeaderFrame`, `#configHeaderLabel`. Add menu bar visual blending with title bar. |
| `gui/menus.py` | Remove QMenuBar background QSS reliance, coordinate with title bar gradient for visual continuity |
| `themes/glassmorphism_v1_theme.json` | Add `gradients.title_bar` entry, optionally add `gradients.dock_header` |

### Removed Code
| Location | What |
|----------|------|
| `style_engine.py:674-690` | `QDockWidget::title` + close/float button QSS |
| `style_engine.py:615-629` | `QMenuBar` background QSS (replaced by gradient blending) |
| `style_engine.py:738-750` | `#configHeaderFrame` + `#configHeaderLabel` QSS |
| `container_root_panel.py:61-80` | `configHeaderFrame` QFrame + QLabel setup |
| `container_root_panel.py:120-133` | `_header_height()` font metrics calculation |
| `container_root_panel.py:225-230` | eventFilter for header click |
| `app.py` dock creation | Float button feature flags |

## Interfaces & Data

### Theme JSON Addition

```json
"title_bar": {
    "type": "linear",
    "anchor": "horizontal",
    "angle": 0,
    "stops": [
        {"position": 0.0, "color": "title_left"},
        {"position": 0.5, "color": "title_mid"},
        {"position": 1.0, "color": "title_right"}
    ],
    "child_opacity": 0
}
```

Palette additions in `base.palette`:
```json
"title_left": "#181535",
"title_mid": "#3030A0",
"title_right": "#4070C0"
```

### Win32 Constants

```python
WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTCAPTION = 2
HTMAXBUTTON = 9
HTMINBUTTON = 8
HTCLOSE = 20
```

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|-------------|
| QPalette override on Fusion style | Windows 11 draws title bar via OS, not Qt — palette has no effect on window chrome |
| Embed menu in title bar | Adds complexity (drag region + menu coexistence), user prefers separate rows with visual continuity |
| Allow dock floating with custom frames | Each floated dock becomes its own top-level frameless window — significant complexity for marginal benefit |
| Single phase implementation | Too large a blast radius; 3 phases allow incremental validation |

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Win11 snap layouts lost | Medium | `WM_NCHITTEST` via `nativeEvent()` + ctypes |
| DWM window shadow lost | Low | `DwmExtendFrameIntoClientArea` with 1px invisible border |
| DPI scaling inconsistency | Medium | Use `logicalDpiX()` for `HEADER_HEIGHT` or scale constant |
| QSettings layout corruption on upgrade | Medium | Migration layer in `_restore_layout()`, version flag in QSettings |
| Custom drag-to-move edge cases | Medium | `mousePressEvent`/`mouseMoveEvent` on title bar widget, tested with multi-monitor |
| Accessibility regression | Low | `setAccessibleName()` on custom window buttons |
| macOS incompatibility | N/A | Project is Windows-only; platform logic isolated in `win32_titlebar.py` |

## Architecture Doc Impact

| Document | Update Needed |
|----------|---------------|
| `GUI_STRUCTURE.md` | Add CustomTitleBar + GradientHeaderBar to widget hierarchy (Section 1), sizing table (Section 2), hardcoded pixels (Section 5) |
| `GUI_LAYOUT_SPECS.md` | New "Frameless Window Mode" subsection (Section 1), title bar gradient (Section 8), module ownership (Section 9) |
| `THEME_WORKFLOW.md` | Add title_bar gradient mapping (Section 3), code location entry for new modules (Section 6) |
| `ARCHITECTUREGLOSSARY.md` | Add GradientHeaderBar, CustomTitleBar terms |
| `GUI_STATE_STYLES.md` | No change (title bar has no state-driven styling) |
