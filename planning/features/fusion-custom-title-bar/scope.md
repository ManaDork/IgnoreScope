# Scope: Fusion Custom Title Bar

## Resolved Decisions (2026-04-09)

| Decision | Choice |
|----------|--------|
| Branching | One branch per phase: `feature/gradient-header-bar`, `feature/frameless-title-bar`, `feature/header-unification` |
| DPI | `BASE_HEADER_HEIGHT = 36`, scaled by `logicalDpiX() / 96.0` |
| Menu bar blend | Menu bar background = title_bar gradient bottom color. Title bar + menu bar appear as one unified bar, no visible seam. |
| Accessibility | `setAccessibleName()` on all custom window buttons (confirmed priority) |

## Phases

### Phase 1: GradientHeaderBar Base Widget
Branch: `feature/gradient-header-bar` off `v0.3-staging`
Standalone reusable widget. No window changes. Can be tested in isolation.

### Phase 2: Frameless Window + Custom Title Bar
Branch: `feature/frameless-title-bar` off `v0.3-staging` (after Phase 1 merge)
Main window goes frameless. CustomTitleBar subclass injected. Win32 snap layout support. DWM shadow. QSettings migration. Menu bar uses title_bar gradient bottom color for seamless visual unity.

### Phase 3: Dock + Config Panel Unification
Branch: `feature/header-unification` off `v0.3-staging` (after Phase 2 merge)
Replace dock QSS title bars and config panel eventFilter header with GradientHeaderBar instances. Remove legacy QSS. Disable dock floating.

## Task Breakdown

### Phase 1: GradientHeaderBar

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 1.1 | Create `gui/gradient_header_bar.py` with `GradientHeaderBar` class | None | Medium | Extends `GradientBackgroundMixin` pattern from `_GradientDockWidget` / `_GradientStatusBar` |
| 1.2 | Implement constant `HEADER_HEIGHT`, label, action button API | 1.1 | Low | Config panel `_header_height()` becomes consumer — don't duplicate height logic |
| 1.3 | Add `contextMenuRequested` signal + `clicked` signal | 1.1 | Low | Config panel eventFilter emits similar — will be replaced in Phase 3 |
| 1.4 | Add `title_bar` gradient entry to `glassmorphism_v1_theme.json` | None | Low | New key, no conflict with existing 5 gradient entries |
| 1.5 | Unit tests for GradientHeaderBar (instantiation, height, signals) | 1.1 | Low | — |

### Phase 2: Frameless Title Bar

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 2.1 | Create `gui/win32_titlebar.py` with `WM_NCHITTEST` handler + DWM shadow | None | High | Platform-specific, no existing code to conflict |
| 2.2 | Create `CustomTitleBar(GradientHeaderBar)` with min/max/close buttons | 1.1 | Medium | Button hover/click pattern — no existing window button code |
| 2.3 | Set `FramelessWindowHint` in `app.py._setup_ui()` | 2.1 | Low | — |
| 2.4 | Inject `CustomTitleBar` into main window layout | 2.2, 2.3 | Medium | — |
| 2.5 | Wire `nativeEvent()` on `IgnoreScopeApp` to `win32_titlebar` handler | 2.1, 2.4 | Medium | — |
| 2.6 | Style menu bar to visually blend with title bar (gradient continuity) | 2.4 | Low | QMenuBar QSS bg → transparent or matching gradient edge color |
| 2.7 | QSettings migration: detect pre-frameless layouts, adjust geometry | 2.3 | Medium | Extends existing `_restore_layout()` pattern |
| 2.8 | Manual test: drag, min, max, close, snap layouts, multi-monitor, DPI | 2.5 | — | — |

### Phase 3: Dock + Config Unification

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 3.1 | Replace dock title bars with `GradientHeaderBar` via `setTitleBarWidget()` | 1.1 | Medium | Replaces QSS `QDockWidget::title` — remove dead QSS |
| 3.2 | Add dock header gradient entries to theme JSON (or reuse existing dock gradients) | 3.1 | Low | Dock gradients already exist — header could sample from them |
| 3.3 | Disable dock floating: remove float button, set `DockWidgetFloatable` off | 3.1 | Low | — |
| 3.4 | Replace config panel `configHeaderFrame` + eventFilter with `GradientHeaderBar` | 1.1 | Medium | Collapse/expand wiring moves from eventFilter to `clicked` signal |
| 3.5 | Config panel: use `HEADER_HEIGHT` constant for collapsed min/max height | 3.4 | Low | Replaces `_header_height()` font metrics — verify DPI behavior |
| 3.6 | Remove legacy QSS: `QDockWidget::title`, `#configHeaderFrame`, `#configHeaderLabel` | 3.1, 3.4 | Low | Grep for orphaned selectors |
| 3.7 | Remove legacy QMenuBar background QSS (replaced by gradient blending in 2.6) | 2.6 | Low | — |
| 3.8 | Update architecture docs: GUI_STRUCTURE, GUI_LAYOUT_SPECS, THEME_WORKFLOW, ARCHITECTUREGLOSSARY | 3.6 | Medium | — |
| 3.9 | Manual test: all header bars gradient, config collapse/expand, dock close/reopen via View menu | 3.6 | — | — |

## DRY Checkpoints

- **GradientHeaderBar vs _GradientDockWidget / _GradientStatusBar**: GradientHeaderBar inherits the same mixin. The `_Gradient*` classes in `app.py` are thin subclasses — they may become consumers of GradientHeaderBar or remain separate (they wrap entire widgets, not just headers).
- **CustomTitleBar button painting vs delegate overlay painting**: Different domains (window chrome vs tree row rendering). No shared code expected.
- **Config panel collapse height vs GradientHeaderBar.HEADER_HEIGHT**: Phase 3 explicitly replaces `_header_height()` font metrics with the constant. Verify the constant works at all DPI scales.
- **Win32 nativeEvent vs existing event handling**: No existing `nativeEvent()` override in the codebase. Clean addition.
