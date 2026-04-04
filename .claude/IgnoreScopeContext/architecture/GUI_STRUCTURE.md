# GUI Structure Audit

> **Purpose:** Single-source-of-truth for every UI object with dimensions — widgets, layouts, docks, frames, splitters — with sizing behavior, parent-child relationships, and whether values are hardcoded/derived/variable.
> **Related:** `GUI_LAYOUT_SPECS.md` (behavioral specs), `DATAFLOWCHART.md` (module responsibilities)

---

## Section 1: Full Widget Hierarchy

Every QObject that affects layout or dimensions gets `setObjectName()`. No anonymous intermediaries.

**Convention:** camelCase with underscore descriptions.
- Panel prefixes: `localHost`, `scope`, `config`
- Roles: `Dock`, `Wrapper`, `Layout`, `Container`, `Tree`, `Header`, `Splitter`, `Frame`, `Label`, `TextEdit`
- Underscores for intermediate descriptors: `localHost_wrapperLayout`, `scope_containerLayout`
- Existing names shown as `[existing]`. New names shown as `[+new]`.

```
QMainWindow (IgnoreScopeApp)                                          app.py
├── QWidget  [+central_hidden]                                        app.py:200
├── QMenuBar                                                          menus.py
├── QStatusBar  [+statusBar]                                          app.py:205
│   └── QLabel  [+status_label]                                       app.py:207
│
├── QDockWidget  [existing: localHostDock]                             app.py:215
│   └── QWidget  [+localHost_wrapper]                                  app.py:217
│       └── QVBoxLayout  [+localHost_wrapperLayout]                    app.py:218
│           └── QWidget  [+localHost_container]                        app.py:220
│               └── QVBoxLayout  [+localHost_containerLayout]          app.py:221
│                   └── LocalHostView  [+localHostView]                (injected app.py:164)
│                       └── QVBoxLayout  [+localHost_viewLayout]       local_host_view.py:74
│                           └── QTreeView  [+localHostTree]            local_host_view.py:66
│                               └── QHeaderView                       (auto — not a QObject child)
│
├── QDockWidget  [existing: scopeDock]                                 app.py:227
│   └── QWidget  [+scope_wrapper]                                      app.py:229
│       └── QVBoxLayout  [+scope_wrapperLayout]                        app.py:230
│           └── _GripSplitter  [+scopeSplitter]                        app.py:235
│               ├── QWidget  [+scope_container]                        app.py:232
│               │   └── QVBoxLayout  [+scope_containerLayout]          app.py:233
│               │       └── ScopeView  [+scopeView]                    (injected app.py:167)
│               │           └── QVBoxLayout  [+scope_viewLayout]       scope_view.py:104
│               │               └── QTreeView  [+scopeTree]            scope_view.py:96
│               │                   └── QHeaderView                    (auto)
│               │
│               └── ContainerRootPanel  [+configPanel]                 app.py:234
│                   └── QVBoxLayout  [+config_panelLayout]             container_root_panel.py:48
│                       ├── QFrame  [existing: configHeaderFrame]      container_root_panel.py:53
│                       │   └── QHBoxLayout  [+config_headerLayout]    container_root_panel.py:56
│                       │       ├── QLabel  [existing: configHeaderLabel]  container_root_panel.py:60
│                       │       └── (QSpacerItem — addStretch)         container_root_panel.py:64
│                       └── QPlainTextEdit  [existing: configViewerText]  container_root_panel.py:74
│
└── (QSettings persistence: windowState, windowGeometry, layoutVersion=11)
```

### Naming Changes Summary

| File | Line | Variable | objectName | Status |
|------|------|----------|-----------|--------|
| app.py | 200 | `central` | `central_hidden` | new |
| app.py | 205 | `status_bar` | `statusBar` | new |
| app.py | 207 | `self.status_label` | `status_label` | new |
| app.py | 216 | `self.local_host_dock` | `localHostDock` | existing |
| app.py | 217 | `local_host_widget` | `localHost_wrapper` | new |
| app.py | 218 | `local_host_layout` | `localHost_wrapperLayout` | new |
| app.py | 220 | `self.local_host_config_container` | `localHost_container` | new |
| app.py | 221 | QVBoxLayout(container) | `localHost_containerLayout` | new |
| app.py | 228 | `self.scope_dock` | `scopeDock` | existing |
| app.py | 229 | `scope_widget` | `scope_wrapper` | new |
| app.py | 230 | `scope_layout` | `scope_wrapperLayout` | new |
| app.py | 232 | `self.scope_config_container` | `scope_container` | new |
| app.py | 233 | QVBoxLayout(container) | `scope_containerLayout` | new |
| app.py | 235 | `scope_splitter` | `scopeSplitter` | new |
| local_host_view.py | 60 | `self` (LocalHostView) | `localHostView` | new |
| local_host_view.py | 74 | QVBoxLayout(self) | `localHost_viewLayout` | new |
| local_host_view.py | 66 | `self._tree_view` | `localHostTree` | new |
| scope_view.py | 90 | `self` (ScopeView) | `scopeView` | new |
| scope_view.py | 104 | QVBoxLayout(self) | `scope_viewLayout` | new |
| scope_view.py | 96 | `self._tree_view` | `scopeTree` | new |
| container_root_panel.py | 43 | `self` (ContainerRootPanel) | `configPanel` | new |
| container_root_panel.py | 48 | QVBoxLayout(self) | `config_panelLayout` | new |
| container_root_panel.py | 54 | `self._header_frame` | `configHeaderFrame` | existing |
| container_root_panel.py | 56 | QHBoxLayout(frame) | `config_headerLayout` | new |
| container_root_panel.py | 61 | `self._header_label` | `configHeaderLabel` | existing |
| container_root_panel.py | 76 | `self._config_text_edit` | `configViewerText` | existing |

**26 total** — 5 existing + 21 new `setObjectName()` calls.

**QSpacerItem** (from `addStretch()`): Not a QObject, cannot take objectName. Documented by position in hierarchy only.

---

## Section 2: Sizing Audit Table

One row per object — every layer, all named.

**Legend:**
- **Resizes To**: `parent` (fills space given by parent), `children` (grows to fit content), `fixed` (hardcoded px), `constrained` (has min/max), `splitter` (ratio-controlled), `stretch` (layout stretch factor)
- **Kind**: `hardcoded` (literal px), `derived` (computed at runtime), `variable` (stretch/ratio/policy), `QSS` (from stylesheet)

### Window Shell

| Layer | objectName | Line | File | Type | Resizes To | Sizing | Kind | Why |
|-------|-----------|------|------|------|-----------|--------|------|-----|
| 0 | IgnoreScopeApp | 195-196 | app.py | QMainWindow | constrained | min 1100×700, default 1400×900 | hardcoded | Root window |
| 1 | `central_hidden` | 200-201 | app.py | QWidget | fixed | maxSize 0×0 | hardcoded | Hides central widget so docks fill window |
| 1 | `statusBar` | 205 | app.py | QStatusBar | parent | height: auto from font | variable | Status bar stretches full width |
| 2 | `status_label` | 207 | app.py | QLabel | children | auto | variable | Text determines width |

### Local Host Dock

| Layer | objectName | Line | File | Type | Resizes To | Sizing | Kind | Why |
|-------|-----------|------|------|------|-----------|--------|------|-----|
| 1 | `localHostDock` | 215 | app.py | QDockWidget | parent | resizeDocks 500px initial | hardcoded | Left dock area |
| 2 | `localHost_wrapper` | 217 | app.py | QWidget | parent | margins 0,1,2,2 | hardcoded | Dock content widget |
| 3 | `localHost_wrapperLayout` | 218 | app.py | QVBoxLayout | — | contentsMargins 0,1,2,2 | hardcoded | Layout manager |
| 4 | `localHost_container` | 220 | app.py | QWidget | stretch | stretch=1 in parent layout | variable | Tree placeholder |
| 5 | `localHost_containerLayout` | 221 | app.py | QVBoxLayout | — | default margins | variable | Layout manager |
| 6 | `localHostView` | (injected) | local_host_view.py | LocalHostView(QWidget) | parent | margins 0,0,0,0 | hardcoded | View widget |
| 7 | `localHost_viewLayout` | 74 | local_host_view.py | QVBoxLayout | — | contentsMargins 0,0,0,0 | hardcoded | Layout manager |
| 8 | `localHostTree` | 66 | local_host_view.py | QTreeView | parent | indentation 20px | hardcoded | Tree fills view |

### Scope Dock

| Layer | objectName | Line | File | Type | Resizes To | Sizing | Kind | Why |
|-------|-----------|------|------|------|-----------|--------|------|-----|
| 1 | `scopeDock` | 227 | app.py | QDockWidget | parent | resizeDocks 500px initial | hardcoded | Right dock area |
| 2 | `scope_wrapper` | 229 | app.py | QWidget | parent | margins 0,1,0,4 | hardcoded | Dock content widget |
| 3 | `scope_wrapperLayout` | 230 | app.py | QVBoxLayout | — | contentsMargins 0,1,0,4 | hardcoded | Layout manager |
| 4 | `scopeSplitter` | 235 | app.py | _GripSplitter | parent | stretchFactor 0→3, 1→1 (75/25) | variable | Vertical splitter |
| 5a | `scope_container` | 232 | app.py | QWidget | splitter | 75% of splitter | variable | Tree placeholder (top) |
| 6a | `scope_containerLayout` | 233 | app.py | QVBoxLayout | — | default margins | variable | Layout manager |
| 7a | `scopeView` | (injected) | scope_view.py | ScopeView(QWidget) | parent | margins 0,0,0,0 | hardcoded | View widget |
| 8a | `scope_viewLayout` | 104 | scope_view.py | QVBoxLayout | — | contentsMargins 0,0,0,0 | hardcoded | Layout manager |
| 9a | `scopeTree` | 96 | scope_view.py | QTreeView | parent | indentation 20px | hardcoded | Tree fills view |
| 5b | `configPanel` | 234 | app.py | ContainerRootPanel | splitter | 25% of splitter | variable | Config panel (bottom) |
| 6b | `config_panelLayout` | 48 | container_root_panel.py | QVBoxLayout | — | contentsMargins 6,6,6,6, spacing 0 | hardcoded | Layout manager |
| 7b | `configHeaderFrame` | 53 | container_root_panel.py | QFrame | children | auto from label + margins | derived | Header clickable area |
| 8b | `config_headerLayout` | 56 | container_root_panel.py | QHBoxLayout | — | contentsMargins 6,6,6,6, spacing 6 | hardcoded | Header layout |
| 9b | `configHeaderLabel` | 60 | container_root_panel.py | QLabel | children | auto from text + font | derived | Header text |
| 7c | `configViewerText` | 74 | container_root_panel.py | QPlainTextEdit | stretch | stretch=1, Expanding×Expanding | variable | JSON preview area |

### Splitter Handle (_GripHandle)

| Layer | objectName | Line | File | Type | Resizes To | Sizing | Kind | Why |
|-------|-----------|------|------|------|-----------|--------|------|-----|
| — | (splitter handle) | 60-66 | app.py | _GripHandle | fixed | sizeHint 10px (h or w) | hardcoded | Three-dot grip indicator |

---

## Section 3: QSS Dimension Map

Every stylesheet selector that sets a dimension, from `style_engine.py` `_STYLESHEET_TEMPLATE`.

### Tree Views

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QTreeView::item` | padding | 4px | 181 |
| `QTreeView::item` | border-bottom | 1px solid | 182 |
| `QTreeView` | border | 1px solid | 174 |
| `QTreeView` | border-radius | 4px | 175 |

### Header

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QHeaderView::section` | padding | 6px | 198 |
| `QHeaderView::section` | border-right | 1px solid | 200 |
| `QHeaderView::section` | border-bottom | 1px solid | 201 |

### Group Boxes

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QGroupBox` | border | 1px solid | 208 |
| `QGroupBox` | border-radius | 4px | 209 |
| `QGroupBox` | margin-top | 12px | 210 |
| `QGroupBox` | padding-top | 8px | 211 |
| `QGroupBox::title` | padding | 0 8px | 219 |

### Buttons

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QPushButton` | border | 1px solid | 226 |
| `QPushButton` | border-radius | 4px | 227 |
| `QPushButton` | padding | 6px 12px | 228 |
| `QPushButton` | min-width | 60px | 229 |

### Line Edits

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QLineEdit` | border | 1px solid | 249 |
| `QLineEdit` | border-radius | 4px | 250 |
| `QLineEdit` | padding | 4px 8px | 251 |

### Checkboxes

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QCheckBox` | spacing | 6px | 267 |
| `QCheckBox::indicator` | width | 16px | 272 |
| `QCheckBox::indicator` | height | 16px | 273 |
| `QCheckBox::indicator` | border-radius | 3px | 274 |
| `QCheckBox::indicator` | border | 1px solid | 275 |

### Menu Bar

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QMenuBar` | border-bottom | 1px solid | 292 |
| `QMenuBar::item` | padding | 6px 12px | 297 |

### Menus

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QMenu` | border | 1px solid | 309 |
| `QMenu::item` | padding | 6px 24px | 314 |
| `QMenu::separator` | height | 1px | 327 |
| `QMenu::separator` | margin | 4px 8px | 329 |

### Status Bar

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QStatusBar` | border-top | 1px solid | 335 |

### Dock Widgets

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QDockWidget::title` | padding | 6px | 352 |
| `QDockWidget::title` | border | 1px solid | 353 |
| `QDockWidget::close-button` | padding | 2px | 359 |

### Scrollbars

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `QScrollBar:vertical` | width | 12px | 374 |
| `QScrollBar:vertical` | border-radius | 6px | 375 |
| `QScrollBar::handle:vertical` | border-radius | 6px | 380 |
| `QScrollBar::handle:vertical` | min-height | 20px | 381 |
| `QScrollBar:horizontal` | height | 12px | 394 |
| `QScrollBar:horizontal` | border-radius | 6px | 395 |
| `QScrollBar::handle:horizontal` | border-radius | 6px | 400 |
| `QScrollBar::handle:horizontal` | min-width | 20px | 401 |

### Config Panel (by objectName)

| Selector | Property | Value | Line |
|----------|----------|-------|------|
| `#configHeaderFrame` | border | 1px solid | 414 |
| `#configHeaderFrame` | border-radius | 4px | 415 |
| `#configHeaderLabel` | font-size | 12px | 421 |
| `#configViewerText` | font-size | 11px | 428 |
| `#configViewerText` | border | 1px solid | 431 |
| `#configViewerText` | border-radius | 4px | 432 |

---

## Section 4: Column Width Definitions

From `display_config.py` — ColumnDef widths per panel.

### LocalHostDisplayConfig (5 columns)

| Col | Header | Width | Mode | Line |
|-----|--------|-------|------|------|
| 0 | "Local Host" | stretch | `QHeaderView.ResizeMode.Stretch` | 328-330 |
| 1 | "Mount" | 70px | `QHeaderView.ResizeMode.Fixed` | 331-340 |
| 2 | "Mask" | 70px | `QHeaderView.ResizeMode.Fixed` | 341-350 |
| 3 | "Reveal" | 70px | `QHeaderView.ResizeMode.Fixed` | 351-359 |
| 4 | "Pushed" | 70px | `QHeaderView.ResizeMode.Fixed` | 360-368 |

### ScopeDisplayConfig (2 columns)

| Col | Header | Width | Mode | Line |
|-----|--------|-------|------|------|
| 0 | "Container Scope" | stretch | `QHeaderView.ResizeMode.Stretch` | 391-393 |
| 1 | "Pushed" | 80px | `QHeaderView.ResizeMode.Fixed` | 395-402 |

### Column Application (view_helpers.py)

```
view_helpers.py:72  header.setStretchLastSection(False)
view_helpers.py:74  if col_def.width == "stretch" → setSectionResizeMode(Stretch)
view_helpers.py:77  else → setSectionResizeMode(Fixed) + resizeSection(i, col_def.width)
```

---

## Section 5: Hardcoded Pixel Value Index

Every literal pixel value in the GUI codebase.

### app.py — Window & Docks

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `1100, 700` | Minimum window size | 195 | hardcoded |
| `1400, 900` | Default window size | 196 | hardcoded |
| `0, 0` | Central widget maxSize (hides it) | 201 | hardcoded |
| `0, 1, 2, 2` | Local host dock margins (T,R,B adjusted) | 219 | hardcoded |
| `0, 1, 0, 4` | Scope dock margins (T,B adjusted) | 231 | hardcoded |
| `500` | Default left dock width | 245 | hardcoded |
| `500` | Default right dock width | 246 | hardcoded |

### app.py — _GripHandle

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `2` | Dot radius (px) | 49 | hardcoded |
| `8` | Dot spacing (px) | 50 | hardcoded |
| `10` | Handle sizeHint height/width | 63, 65 | hardcoded |

### app.py — Splitter Ratios

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `3:1` | stretchFactor tree(75%):panel(25%) | 238-239 | variable (ratio) |

### container_root_panel.py

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `6, 6, 6, 6` | Panel layout margins | 49 | hardcoded |
| `0` | Panel layout spacing | 50 | hardcoded |
| `6, 6, 6, 6` | Header layout margins | 57 | hardcoded |
| `6` | Header layout spacing | 58 | hardcoded |
| `16777215` | QWIDGETSIZE_MAX (unconstrained) | 109 | derived |
| `1` | CSS border width (matches QSS) | 116 | hardcoded |

### container_root_panel.py — Collapse Height Formula (derived)

```python
# Lines 117-122
collapsed_height = (
    panel_margins.top + panel_margins.bottom
    + 2 * css_border        # 2px
    + header_margins.top + header_margins.bottom
    + fontMetrics.height
)
```

### view_helpers.py

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `20` | Tree indentation (px) | 53 | hardcoded |

### local_host_view.py

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `0, 0, 0, 0` | View layout margins | 75 | hardcoded |

### scope_view.py

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `0, 0, 0, 0` | View layout margins | 105 | hardcoded |

### session_history.py

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `0, 0, 0, 0` | View layout margins | 232 | hardcoded |

### display_config.py — Column Widths

| Value | Purpose | Line | Kind |
|-------|---------|------|------|
| `70` | Mount column width | 333 | hardcoded |
| `70` | Mask column width | 343 | hardcoded |
| `70` | Reveal column width | 353 | hardcoded |
| `70` | Pushed column width (LocalHost) | 362 | hardcoded |
| `80` | Pushed column width (Scope) | 397 | hardcoded |

### style_font.py

No hardcoded dimensions. Generic QFont wrapper — font sizes set via JSON data.