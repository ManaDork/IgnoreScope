# Feature Spec: Fusion Custom Title Bar

**Status:** Phase 1 (`GradientHeaderBar` base widget) shipped 2026-04-09 (commits 67d17ee + 9b35d3b, see `planning/tasks/gradient-header-bar.md`). Phases 2-3 (frameless window + custom title bar; dock title bar upgrade; config panel header refactor) deferred. Promoted from `planning/backlog/fusion-custom-title-bar.md` per cleanup Phase C.3 #2 (2026-05-04).

## Problem Statement

The Windows OS title bar is the only element the glassmorphism theme system cannot reach. It draws with the system accent color and breaks the dark gradient aesthetic. Additionally, three different "header bar" implementations exist (OS title bar, QSS dock titles, config panel eventFilter header) with no shared visual language.

## Success Criteria

- Main window has a custom gradient title bar with minimize/maximize/close buttons
- Title bar and menu bar visually appear as one solid gradient shape (separate rows, continuous gradient feel)
- Dock title bars use the same GradientHeaderBar base widget with gradient backgrounds
- Config panel header uses GradientHeaderBar, replacing eventFilter + font metrics calculation
- Win11 snap layouts work (hover maximize button shows snap flyout)
- Window drag-to-move works from the title bar region
- DWM window shadow preserved
- No dock floating (removed to avoid native-frame inconsistency)

## User Stories

1. **As a user**, I see a continuous dark gradient from the title bar through the entire window, matching the glassmorphism theme.
2. **As a user**, I can minimize, maximize, and close the window using familiar icon buttons (─ □ ✕).
3. **As a user**, I can drag the window by clicking the title bar area.
4. **As a user**, Win11 snap layouts appear when I hover the maximize button.
5. **As a user**, all header bars (title, dock, config panel) share a consistent gradient visual style.
6. **As a user**, I can right-click header bars for context menus (config panel: expand/collapse).

## Acceptance Criteria

- [ ] `GradientHeaderBar` base widget paints gradient via `GradientBackgroundMixin`, has constant height, label text, action buttons, and `contextMenuRequested` signal
- [ ] Main window uses `Qt.WindowType.FramelessWindowHint`
- [ ] Custom title bar widget with ─ □ ✕ buttons, hover highlights, close-button red hover
- [ ] `nativeEvent()` handles `WM_NCHITTEST` returning `HTMAXBUTTON` for max button region, `HTCAPTION` for drag region
- [ ] DWM frame extended with 1px invisible border for window shadow
- [ ] `title_bar` gradient entry in `glassmorphism_v1_theme.json`
- [ ] Dock title bars replaced via `QDockWidget.setTitleBarWidget(GradientHeaderBar(...))`
- [ ] Float button removed from docks
- [ ] Config panel `configHeaderFrame` + eventFilter + font metrics height replaced by `GradientHeaderBar`
- [ ] Config panel collapse/expand uses constant `HEADER_HEIGHT` from `GradientHeaderBar`
- [ ] Legacy QSS sections removed: `QDockWidget::title`, `QMenuBar` bg, `#configHeaderFrame`, `#configHeaderLabel`
- [ ] `QSettings` layout migration handles frameless geometry offset
- [ ] Menu bar styled to visually blend with title bar gradient (no visible seam)

## Out of Scope

- macOS title bar handling (project is Windows-only; design keeps platform logic isolated for future)
- Embedding menu bar inside the title bar (separate rows chosen)
- Dock floating with custom frames on floated windows
- Resizable window edges via custom hit-testing (Qt handles resize grip via `FramelessWindowHint` + size policy)

## Open Questions

1. **DPI scaling**: Should `HEADER_HEIGHT` be a logical pixel constant or DPI-aware via `logicalDpiX()`? The config panel currently uses font metrics — switching to a constant needs a DPI strategy.
2. **Menu bar gradient**: Does the menu bar get its own gradient entry, or use `title_bar` gradient with an offset? User wants them to look like one shape.
3. **Accessibility**: Do custom window buttons need `setAccessibleName()`? (Yes for screen reader support — confirm priority.)

---

## Cross-Feature Integration Notes (folded in from backlog 2026-04-08)

### Reusable GradientHeaderBar Widget

The codebase had three different "header bar" implementations as of 2026-04-08:

| Header | Implementation | Gradient | Click Behavior |
|--------|---------------|----------|----------------|
| Windows title bar | OS-drawn | None | OS drag/buttons |
| Dock title bars (`QDockWidget::title`) | QSS flat color | No | Qt close/float buttons |
| Config panel header (`configHeaderFrame`) | QFrame + QLabel + eventFilter | Parent mixin only | Manual toggle |

A shared `GradientHeaderBar` widget unifies all three with a fixed known height (constant, not font-metrics calculation), gradient background via `GradientBackgroundMixin` (theme-driven), label text + optional action buttons, and click signal emission (no event filter).

### QSS Reduction (Phases 2-3)

Moving styled headers from QSS to `paintEvent` via gradient mixin removes:
- `QDockWidget::title` section (lines 662-668 of stylesheet template)
- `QMenuBar` / `QMenuBar::item` sections (lines 603-617)
- `#configHeaderFrame` / `#configHeaderLabel` sections (lines 726-738)

These participate in theme JSON `gradients` section directly instead.

### Implementation Order

1. ✓ Phase 1: `GradientHeaderBar` base widget (shipped 2026-04-09)
2. Frameless window + custom title bar using `GradientHeaderBar`
3. Refactor config panel header to use `GradientHeaderBar` (collapsed height becomes constant)
4. Optional: replace dock title bars via `setTitleBarWidget()`
