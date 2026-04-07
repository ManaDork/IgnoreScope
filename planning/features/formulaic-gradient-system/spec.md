# Formulaic Gradient System

## Problem Statement

The current display state system has three issues:

1. **MOUNTED_MASKED is invalid** — the mount root cannot be masked by its own pathspec patterns. The `mount_root_masked` flag was a workaround that proved unnecessary — mirrored folders already communicate masked content through children's states.

2. **State definitions are hand-built** — each folder state manually declares a `GradientClass(p1, p2, p3, p4)`. Adding a new state requires writing a gradient, a truth table entry, a font assignment, and tests. Error-prone and duplicative.

3. **No consistent visual language** — the gradient positions carry semantic meaning (visibility, context, ancestor, config) but this isn't enforced. Hand-built gradients can violate the formula.

## Success Criteria

- MOUNTED_MASKED removed. Mount root shows as FOLDER_MOUNTED (distinct from VISIBLE via config.mount accent).
- `derive_gradient()` function replaces hand-built `_FOLDER_STATE_DEFS` and `FOLDER_STATE_TABLE`.
- Gradient positions derived from node properties — no lookup table for folder states.
- PUSHED and REVEALED unified as `ancestor.visible` for folder ancestor tracking.
- State names derivable from the formula (for debugging/logging).
- All 12 folder states produce correct gradients via the formula.
- File states unchanged (keep slim hand-built layout, deferred).

## Visual Language — Gradient Formula

```
P1 = visibility     what the container sees     (visible, hidden, mirrored, co)
P2 = context         parent/inherited visibility (visible, hidden, co)
P3 = ancestor        descendant tracking         (anc_visible, or falls to P4)
P4 = config          direct/inherited action     (mount, reveal, masked, virtual_*)
```

**P3-P4 fallback chain:** P3 = ancestor if present, else P4. P4 = config if present, else P1.

**P1-P2 relationship:** P2 mirrors P1 except REVEALED (P1=visible, P2=hidden — visible in hidden context).

## Folder States (12)

| State | P1 | P2 | P3 | P4 | Font |
|---|---|---|---|---|---|
| VISIBLE | visible | visible | — | — | default |
| MOUNTED | visible | visible | — | mount | default |
| MOUNTED_REVEALED | visible | visible | anc_visible | mount | default |
| REVEALED | visible | hidden | — | reveal | default |
| HIDDEN | hidden | hidden | — | — | muted |
| MASKED | hidden | hidden | — | masked | muted |
| PUSHED_ANCESTOR | hidden | hidden | anc_visible | — | default |
| MIRRORED | mirrored | hidden | — | — | virtual_mirrored |
| MIRRORED_REVEALED | mirrored | hidden | anc_visible | — | virtual_mirrored |
| VIRTUAL_VOLUME | mirrored | hidden | — | virtual_vol | virtual_volume |
| VIRTUAL_AUTH | mirrored | hidden | — | virtual_auth | virtual_auth |
| CONTAINER_ONLY | co | co | — | — | italic |

"—" = falls to next in chain (P3→P4→P1).

## Acceptance Criteria

- [ ] `mount_root_masked` removed from MountSpecPath (field + serialization)
- [ ] `has_mount_masks` removed from NodeState
- [ ] Header RMB Mask/Unmask actions removed from local_host_view.py
- [ ] `toggle_mount_root_masked()` removed from mount_data_tree.py
- [ ] FOLDER_MOUNTED state added (is_mount_root=True, vis=visible → config.mount accent)
- [ ] FOLDER_MOUNTED_REVEALED state added (MOUNTED + has_visible_descendant)
- [ ] `derive_gradient()` function computes P1-P4 from node properties
- [ ] `ancestor.pushed` + `ancestor.revealed` → unified `ancestor.visible`
- [ ] All 12 folder states verified via derivation table
- [ ] File states unchanged (slim layout preserved)
- [ ] Architecture docs updated

## Out of Scope

- File state formulaic derivation (deferred)
- File font color differentiation (FILE_MASKED vs FILE_HIDDEN)
- File P3 sync state
- Container Scope panel override system
- Dynamic state name generation in production code (debugging only)
