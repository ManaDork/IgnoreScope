# Font Derived Parity — Scope

## Phase: Single (MVP = Full)

No phasing needed — all work is tightly coupled and low complexity.

## Task Breakdown

| # | Task | Depends On | Complexity | DRY Checkpoint |
|---|------|-----------|------------|----------------|
| 1 | Add `pushed_sync` / `pushed_nosync` entries to `tree_state_font.json` | — | Low | Verify no key collision with existing 6 entries |
| 2 | Add `text_pushed_sync` / `text_pushed_nosync` to `theme.json` text section + `TreeDisplayConfig` class defaults | 1 | Low | Verify no attribute name collision on BaseDisplayConfig |
| 3 | Implement `derive_file_style()` function in `display_config.py` | — | Medium | Compare font logic against `derive_gradient()` lines 121-131; ensure no accidental Type 1 clone beyond shared concepts |
| 4 | Replace `_FILE_STATE_DEFS` with `_FILE_STYLE_INPUTS` + comprehension; verify `_TREE_STATE_DEFS` union unchanged | 3 | Low | Assert derived output matches previous hand-coded values before removing old code |
| 5 | Add parametrized tests for `derive_file_style()` + pushed key validation; update `test_font_vars_count` / `test_font_vars_keys` | 1, 2, 3, 4 | Medium | Verify test names don't collide with existing test functions |
| 6 | Update `GUI_STATE_STYLES.md` — file derivation section, font variable tables, pushed placeholders | 1, 2, 3 | Low | Cross-check against current doc structure (Sections 3, 6.1, 6.3) |

## Deferred (from this feature)

- FILE_MASKED / FILE_REVEALED font color differentiation
- Pushed sync/nosync actual wiring to NodeState
- FILE_HOST_ORPHAN gradient (blocked on core)
- Font constant extraction (enum / module-level)
- Bold weight usage

## Estimated File Changes

| File | Change Type |
|------|-------------|
| `IgnoreScope/gui/display_config.py` | New function + refactored dict |
| `IgnoreScope/gui/tree_state_font.json` | 2 new entries |
| `IgnoreScope/gui/theme.json` | 2 new entries in text section |
| `IgnoreScope/tests/test_gui/test_display_config.py` | New tests + updated counts |
| `.claude/IgnoreScopeContext/architecture/GUI_STATE_STYLES.md` | Documentation update |
