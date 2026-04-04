# Feature: Style State Polish

## Problem Statement

The state/style system has accumulated inconsistencies during the MountSpecPath refactor:
1. **Truth table conflation:** `visibility="mirrored"` serves double duty — both "masked folder with revealed child" and "structural mkdir path." These are visually and semantically different states sharing one visibility value, distinguished only by `has_direct_visible_child`.
2. **File state gaps:** 5 of 13 file state combinations fall through to FILE_HIDDEN silently. Pushed files that are visible or revealed render as hidden.
3. **Folder gradient framework** established (LEFT=self, MID=ancestor, RIGHT=descendant) but not fully applied to all states or documented in architecture.
4. **File gradient** has no defined framework — gradients are ad-hoc.

## Success Criteria

1. Every reachable (visibility, flag) combination has an explicit truth table entry — no silent fallbacks
2. Folder gradients follow the 4-position framework consistently
3. File gradients follow their own 4-position framework consistently
4. `compute_visibility()` returns distinct values for mirrored vs virtual (mkdir) paths
5. Architecture docs updated to reflect the style framework

## User Stories

- As a user, I want masked folders with revealed children to look visually distinct from structural mkdir paths, so I can understand the tree hierarchy at a glance
- As a user, I want pushed files that are visible to show as visible (not hidden), so the state display is honest
- As a developer, I want every state combination to have an explicit mapping, so style bugs are caught immediately rather than silently falling back

## Acceptance Criteria

### Refactor: Visibility Split
- [ ] `compute_visibility()` returns `"virtual"` for mkdir-only paths (formerly `"mirrored"`)
- [ ] `"mirrored"` value deprecated or repurposed
- [ ] Truth table entries updated for `"virtual"` visibility
- [ ] Stage 2 in `apply_node_states_from_scope()` uses `"virtual"` instead of `"mirrored"`

### Folder Gradient Framework
- [ ] All 9+ folder states follow the framework:

| P1 | P2 | P3 | P4 |
|----|----|----|-----|
| visibility | visibility (inherited) | descendant influence (uses P4 color) | self config action / inheritance type |

- [ ] P1 values: `visible`, `hidden`, `virtual`
- [ ] P4 values: `masked`, `revealed`, `mounted`, or muted inheritance variant
- [ ] P3 shows descendant effect using P4's color when a child affects this node

### Folder Font
- [ ] 3 font tiers: Visible (default), Hidden (muted), Virtual/mirrored (new mid-tier?)

### File Gradient Framework
- [ ] All 8+ file states follow the framework:

| F1 | F2 | F3 | F4 |
|----|----|----|-----|
| visibility | background | sync status (deferred) | pushed state |

- [ ] F3 sync: deferred but slot reserved in gradient

### File State Gaps Fixed
- [ ] `(visible, True, *)` → explicit entry (FILE_VISIBLE_PUSHED or FILE_VISIBLE)
- [ ] `(revealed, True, *)` → explicit entry (FILE_REVEALED_PUSHED or FILE_REVEALED)
- [ ] No silent fallbacks — resolve_tree_state() logs warning on unmatched

### Architecture Docs
- [ ] GUI_STATE_STYLES.md updated with gradient frameworks
- [ ] ARCHITECTUREGLOSSARY.md "visibility" entry updated for `"virtual"` value

## Out of Scope

- New color palette design (colors stay, framework changes)
- GradientClass.with_selected() implementation (skipped tests remain)
- Container scan diff implementation for F3 sync (slot reserved, implementation deferred)
- FILE_HOST_ORPHAN gradient (remains deferred)

## Open Questions

1. Should `"mirrored"` be completely replaced by `"virtual"`, or should both exist?
2. Does P3 (descendant influence) need its own color variable, or does using P4's color suffice?
3. For file F3 sync — should the gradient slot show background (deferred) or a neutral placeholder?
