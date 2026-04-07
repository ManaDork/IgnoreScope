# Font Derived Parity — Feature Specification

## Problem Statement

File states in `display_config.py` use **hand-coded font assignments** — static string literals in a dict, while folder states derive fonts formulaically through `derive_gradient()`. This creates two problems:

1. **Structural asymmetry**: Folders have `_FOLDER_STATE_INPUTS` → `derive_gradient()` → `(GradientClass, font)`. Files have a flat dict of hand-coded tuples. Adding or modifying file font behavior requires editing magic strings scattered across 8 entries.

2. **Missing pushed font keys**: `pushed_sync` and `pushed_nosync` font entries don't exist. When pushed file sync-state tracking lands (future feature), there are no font variables to wire into.

The background gradient system has 25 per-state color variables in `tree_state_style.json`. The font system has 6 keys in `tree_state_font.json` mapping to 4 text colors in `theme.json`. This feature closes the **structural** gap (formulaic derivation) and stubs the **content** gap (pushed font placeholders).

## Success Criteria

- File font assignments are derived through a formula (`derive_file_style()`), not hand-coded
- Pushed font keys exist as documented placeholders for future wiring
- Existing visual behavior is preserved — zero rendering changes
- Test coverage validates derivation for all 8 file states

## Acceptance Criteria

- [ ] `derive_file_style()` function exists in `display_config.py`
- [ ] `derive_file_style()` produces identical `(GradientClass, font_key)` output to current hand-coded `_FILE_STATE_DEFS` for all 8 file states
- [ ] `_FILE_STATE_DEFS` is replaced with `_FILE_STYLE_INPUTS` dict + `derive_file_style()` comprehension (parallel to folder pattern)
- [ ] `_TREE_STATE_DEFS` unchanged — still union of folder + file defs
- [ ] `pushed_sync` and `pushed_nosync` font keys added to `tree_state_font.json` (unused placeholders)
- [ ] `text_pushed_sync` and `text_pushed_nosync` added to `theme.json` `"text"` section (placeholder hex)
- [ ] `text_pushed_sync` and `text_pushed_nosync` class attribute defaults added to `TreeDisplayConfig`
- [ ] Python code referencing pushed keys includes comments marking them as unused placeholders
- [ ] New parametrized tests validate `derive_file_style()` output for all 8 file states
- [ ] New tests validate pushed font key existence in JSON
- [ ] `GUI_STATE_STYLES.md` updated: document `derive_file_style()`, new font keys, file derivation formula
- [ ] All existing tests pass unchanged
- [ ] `_build_state_styles()` requires zero modifications

## Out of Scope

- **FILE_MASKED / FILE_REVEALED font differentiation** — states stay as `"muted"` / `"default"` (deferred, tracked in `style-polish-round-2`)
- **FILE_HOST_ORPHAN gradient** — remains `None` (blocked on core orphan detection)
- **Pushed sync/nosync implementation** — only placeholder entries, no wiring to node state
- **GUI palette shift** — tracked in `planning/backlog/gui-palette-shift.md`
- **Selection opacity blend** — tracked in `planning/backlog/selection-opacity-blend.md`
- **Font constant extraction** (enum/module-level) — DRY audit flagged this as medium severity; can be a follow-up refactor
- **Bold weight usage** — weight field stays `"normal"` for all entries

## Open Questions

None — all design decisions resolved during discovery.

## Related Work

| Document | Relationship |
|----------|-------------|
| `planning/features/style-polish-round-2/` | Parent feature — this resolves deferred file font items |
| `planning/features/formulaic-gradient-system/` | Reference implementation — folder derivation pattern to mirror |
| `planning/backlog/gui-palette-shift.md` | Future — will change text color hex values |
| `docs/architecture/GUI_STATE_STYLES.md` | Blueprint — must update |
