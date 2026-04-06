# Code Review: Architecture Blueprints — Phase 2 Findings

**Date:** 2026-04-06
**Scope:** All 7 architecture blueprints
**Method:** Compare every doc claim against current code
**Total findings:** 5 issues (10 claims verified correct)

---

## FINDINGS (needs update)

### [ARCHITECTUREGLOSSARY.md:247-248] Stale state names
- **Type:** stale
- **Doc says:** FOLDER_VIRTUAL_MIRRORED, FOLDER_VIRTUAL_MIRRORED_REVEALED
- **Code reality:** FOLDER_MIRRORED, FOLDER_MIRRORED_REVEALED (VIRTUAL_ prefix dropped)
- **Recommendation:** update

### [COREFLOWCHART.md:7,88] Outdated state count
- **Type:** outdated-count
- **Doc says:** "14 states (7 folder + 7 file) + 2 overrides"
- **Code reality:** 20 tree states (12 folder + 8 file) + 2 selected overrides
- **Recommendation:** update to match GUI_STATE_STYLES.md line 93 (authoritative)

### [DATAFLOWCHART.md:7] Same outdated state count
- **Type:** outdated-count
- **Doc says:** "14 states (7 folder + 7 file) + 2 overrides"
- **Code reality:** 20 tree states (12 folder + 8 file)
- **Recommendation:** update

### [GUI_LAYOUT_SPECS.md:505] Same outdated state count
- **Type:** outdated-count
- **Doc says:** "14 tree states (7 folder + 7 file)"
- **Code reality:** 20 tree states (12 folder + 8 file)
- **Recommendation:** update

### [test_node_state.py:970,983] Stale test docstrings
- **Type:** stale
- **Doc says:** References FOLDER_MOUNTED_MASKED, FOLDER_MOUNTED_MASKED_PUSHED
- **Code reality:** These states don't exist. Tests check visibility="masked" correctly — just docstrings are stale
- **Recommendation:** update docstrings

---

## VERIFIED CORRECT (no change needed)

| Document | Claim | Status |
|----------|-------|--------|
| COREFLOWCHART.md Phase 3 | Stage 2 config-native, 3 checks | Correct |
| MIRRORED_ALGORITHM.md | Stage descriptions, data flow | Correct |
| GUI_STATE_STYLES.md | 20 states, formula, color categories | Correct (authoritative) |
| ARCHITECTUREGLOSSARY.md | NodeState fields (no has_mount_masks) | Correct |
| ARCHITECTUREGLOSSARY.md | Folder state count = 12 | Correct |
| ARCHITECTUREGLOSSARY.md | Backward-compat properties | Correct |
| Color system | Categorical naming in JSON | Correct |
| Formulaic system | derive_gradient() generates defs | Correct |
| Pipeline | Config-native Stages 2+3 | Correct |
| theme.json | Retained during migration | Correct |

---

## SUMMARY

3 docs have outdated "14 states" count → should be "20 states (12 folder + 8 file)".
1 doc has stale VIRTUAL_MIRRORED names → should be MIRRORED.
1 test file has stale docstrings referencing removed states.

**GUI_STATE_STYLES.md is the authoritative reference** — it has correct counts and current state names. Other docs should defer to it.
