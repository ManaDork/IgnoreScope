# Code Review: CLAUDE.md — Phase 3 Findings

**Date:** 2026-04-06
**Scope:** Project CLAUDE.md accuracy
**Total findings:** 2 (minor)

---

## FINDINGS

### [CLAUDE.md:12] MatrixState concept partially superseded
- **Type:** outdated (minor)
- **Current:** "MatrixState: Prefer truth table evaluation over gated conditional chains... Applied in `core/node_state.py`."
- **Actual:** Still applies to Stage 1 visibility (compute_visibility truth table). However, folder display states now use derive_gradient() formula, not truth tables. FILE_STATE_TABLE still uses truth table pattern.
- **Recommendation:** Add note: "Stage 1 visibility uses MatrixState pattern. Folder display states use formulaic derivation via derive_gradient(). File display states retain truth table."

### [CLAUDE.md:12] "match against explicit condition tuples" partially stale
- **Type:** outdated (minor)
- **Current:** "match against explicit condition tuples"
- **Actual:** FOLDER_STATE_TABLE was removed. Folder states resolve via _resolve_folder_state() if/elif chain. File states still use condition tuple matching.
- **Recommendation:** Clarify: "applied in core/node_state.py (Stage 1 visibility) and gui/display_config.py (file states). Folder display states use formulaic derivation."

---

## VERIFIED CORRECT (no change needed)

| Section | Claim | Status |
|---------|-------|--------|
| Project Overview | Docker volume layering description | Correct |
| Architecture Blueprints table | 7 documents listed | Correct — all 7 exist |
| Agent Zones | Paths and triggers | Correct |
| Key Locations | All paths | Correct |
| DOCUMENTATION table | Names, paths, domains | Correct |
| PROJECT ARCHITECTURE | Adherence levels | Correct |
| Workflow table | Triggers and actions | Correct |
| External Dependencies | Docker, Perforce, GitHub | Correct |
| Commands table | All /zev-* commands | Correct |
| Quality Procedures | DRY, Adherence, Bug Review | Correct |
| Debug/Architecture Review protocols | Trace methodology | Correct |

---

## SUMMARY

CLAUDE.md is largely accurate. Two minor findings about MatrixState concept description — the pattern still applies to Stage 1 and file states, but folder display states now use formulaic derivation. No stale function names, no stale state names, no broken path references.
