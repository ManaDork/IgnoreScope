# Consolidated Theme File — Scope

## Phase: Single (MVP = Full)

All changes ship together. The consolidated file replaces the old files atomically — no intermediate state where both systems coexist.

## Task Breakdown

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 1 | Write `glassmorphism_v1_theme.json` with all 5 sections + `_meta` | — | Low | Verify all current hex values from 3 source files are present. No data loss. |
| 2 | Add `_load_consolidated_theme()` to `style_engine.py` — parse file, validate sections, deep-merge scope | — | Medium | Check for overlap with existing `json.load()` calls in StyleGui and BaseDisplayConfig. |
| 3 | Refactor `StyleGui.__init__()` to load from consolidated file via `_find_theme_file()` | 1, 2 | Medium | Verify all `self._theme[key]` access patterns still resolve. No fallback hex in `palette_color()`, `ui_color()`, `_resolve_gradient_color()`. |
| 4 | Refactor `BaseDisplayConfig.__init__()` to accept resolved dicts instead of filenames | 2 | Medium | Compare with existing `json.load()` pattern. Verify `resolve_text_color()` still works without class-level hex defaults. |
| 5 | Refactor `TreeDisplayConfig` to accept `panel` param ("local_host" / "scope") and read from consolidated theme | 3, 4 | Medium | Verify `_TREE_STATE_DEFS` unchanged. Check that both `LocalHostDisplayConfig` and `ScopeDisplayConfig` subclasses pass correct panel identity. |
| 6 | Update `LocalHostDisplayConfig` and `ScopeDisplayConfig` to pass panel identity | 5 | Low | Verify column definitions and filters unchanged. |
| 7 | Update `ListDisplayConfig` to accept resolved dicts (same pattern as TreeDisplayConfig) | 4 | Low | List panel not wired — keep `list_style.json` / `list_font.json` as fallback source until session_history section added. |
| 8 | Add `config_panel` section loading to `StyleGui` + resolve var names to hex via `ui_color()` | 3 | Low | Verify `config_panel` key names match `ui` section keys. |
| 9 | Wire `config_panel` styles into `build_stylesheet()` QSS template — replace hardcoded `#configHeaderFrame`, `#configHeaderLabel`, `#configViewerText` selectors | 8 | Low | Verify QSS selectors match objectNames in `container_root_panel.py`. |
| 10 | Remove all hex literals from `style_engine.py` and `display_config.py` | 3, 4, 5 | Low | Grep for `#[0-9A-Fa-f]{6}` in both files. Zero hits expected (except comments). |
| 11 | Remove old JSON files: `theme.json`, `tree_state_style.json`, `tree_state_font.json` | 1–10 | Low | Grep entire `gui/` for references to old filenames. All must be gone. |
| 12 | Update tests: hex assertions, file loading paths, new deep-merge and missing-key tests | 1–11 | Medium | Verify test names don't collide. Add tests for: consolidated loading, scope deep-merge, missing section error, missing key error, config_panel resolution. |
| 13 | Update architecture docs: `GUI_STATE_STYLES.md`, `DATAFLOWCHART.md`, `GUI_STRUCTURE.md` | 1–11 | Low | Cross-check per-panel differentiation section doesn't conflict with existing delegate gradient docs. |

## Estimated File Changes

| File | Change Type |
|------|-------------|
| `IgnoreScope/gui/glassmorphism_v1_theme.json` | New — consolidated theme |
| `IgnoreScope/gui/style_engine.py` | Refactor — ThemeLoader, hex removal, config_panel API |
| `IgnoreScope/gui/display_config.py` | Refactor — dict injection, hex removal, per-panel identity |
| `IgnoreScope/gui/list_display_config.py` | Refactor — dict injection (minor) |
| `IgnoreScope/gui/app.py` | Minor — panel identity wiring |
| `IgnoreScope/gui/local_host_view.py` | Minor — pass panel identity |
| `IgnoreScope/gui/scope_view.py` | Minor — pass panel identity |
| `IgnoreScope/gui/container_root_panel.py` | Minor — config_panel style consumption |
| `IgnoreScope/gui/theme.json` | Removed |
| `IgnoreScope/gui/tree_state_style.json` | Removed |
| `IgnoreScope/gui/tree_state_font.json` | Removed |
| `IgnoreScope/tests/test_gui/test_style_engine.py` | Updated — hex values, new loader tests |
| `IgnoreScope/tests/test_gui/test_display_config.py` | Updated — constructor changes, per-panel tests |
| Architecture docs (3) | Updated |

## Deferred

- Session History section (6th section, when list panel wired)
- Theme switching / hot-reload
- Theme editor GUI
- ContainerPatternListWidget row styling
