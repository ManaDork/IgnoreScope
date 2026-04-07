# Consolidated Theme File — Feature Specification

## Problem Statement

Visual configuration is scattered across 5 JSON files (`theme.json`, `tree_state_style.json`, `tree_state_font.json`, `list_style.json`, `list_font.json`) plus hardcoded hex fallbacks in Python code (`style_engine.py`, `display_config.py`). This creates three problems:

1. **Palette shifts require touching 5+ files** — every color change means editing multiple JSONs and updating Python fallback values that silently drift.
2. **No per-panel style differentiation** — LocalHost and Scope panels share one `tree_state_style.json` with no way to give them distinct state colors.
3. **Desktop Docker Scope Config panel has no theme integration** — its header, viewer, and border colors are hardcoded in QSS selectors with no JSON override path.

## Success Criteria

- All visual configuration lives in a single `{theme_name}_{version}_theme.json` file
- No hex color literals remain in `style_engine.py` or `display_config.py`
- Scope panel can override any LocalHost state color via deep-merge fallback
- ContainerRootPanel (Desktop Docker Scope Config) reads its styles from the theme file
- Palette shifts are JSON-only changes — zero Python edits needed

## Acceptance Criteria

- [ ] Single consolidated theme file with 5 top-level sections: `base`, `gradients`, `local_host`, `scope`, `config_panel`
- [ ] File naming convention: `{theme_name}_{version}_theme.json`
- [ ] `base` section contains: `palette`, `ui`, `text`, `delegate` subsections
- [ ] `gradients` section contains named widget gradient definitions (existing schema)
- [ ] `local_host` section contains: `state_colors` (from tree_state_style.json) + `fonts` (from tree_state_font.json)
- [ ] `scope` section contains: `state_colors` + `fonts` — deep-merged over `local_host` at load time
- [ ] `scope` keys missing from JSON inherit from `local_host` values
- [ ] `config_panel` section contains: `header_bg`, `header_text`, `viewer_bg`, `viewer_text`, `border` — referencing theme var names
- [ ] StyleGui loads the consolidated file instead of `theme.json`
- [ ] BaseDisplayConfig receives resolved dicts instead of loading separate JSON files
- [ ] TreeDisplayConfig instantiated per-panel with panel-specific resolved state colors
- [ ] All hex literals removed from `style_engine.py` (`palette_color`, `ui_color`, `_resolve_gradient_color` fallbacks)
- [ ] All hex literals removed from `display_config.py` class-level defaults (`text_primary`, `text_dim`, `text_warning`, `text_virtual_purple`, `text_pushed_sync`, `text_pushed_nosync`, `hover_color`)
- [ ] Missing required keys raise clear errors at load time (no silent hex fallbacks)
- [ ] ContainerRootPanel reads `config_panel` section for header/viewer/border styling
- [ ] QSS `#configHeaderFrame`, `#configHeaderLabel`, `#configViewerText` selectors use theme-resolved values
- [ ] Old separate JSON files removed after consolidation
- [ ] All existing tests pass (updated to reference new load paths)
- [ ] New tests validate consolidated loading, deep-merge fallback, missing-key errors

## Out of Scope

- **Session History (list panel) section** — add as 6th section when the panel gets wired to the UI
- **Theme switching at runtime** — single theme loaded at init; hot-reload is future work
- **Theme editor UI** — no GUI for editing the theme file
- **Gradient unification** — widget gradients and delegate gradients remain separate systems
- **ContainerPatternListWidget styling** — pattern list row styling deferred

## Open Questions

None — all design decisions resolved during discovery.

## Related Work

| Document | Relationship |
|----------|-------------|
| `planning/features/widget-gradient-background-styles/` | Sibling — established gradients section in theme.json |
| `planning/features/style-polish-round-2/` | Predecessor — introduced categorical color system |
| `planning/backlog/gui-palette-shift.md` | Consumer — palette shifts become JSON-only after this feature |
| `docs/architecture/GUI_STATE_STYLES.md` | Blueprint — must update for consolidated theme structure |
| `docs/architecture/DATAFLOWCHART.md` | Blueprint — update theme loading flow |
