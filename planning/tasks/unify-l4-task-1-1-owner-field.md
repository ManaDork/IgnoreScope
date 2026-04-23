# Unify L4 — Task 1.1: Add `owner` Field to `MountSpecPath`

**Feature:** `unify-l4-reclaim-isolation-term`
**Phase:** 1 — Structural Unification (L4 Retirement)
**Task:** 1.1
**Branch:** `feature/unify-l4-task-1-1-owner-field` (off `staging-v0.5`)
**Depends on:** — (first task of Phase 1)
**Blocks:** 1.2 (`ExtensionConfig.synthesize_mount_specs`), 1.10 (read-only RMB re-key)

---

## Scope

Add a single new field to `MountSpecPath`:

```python
owner: str = "user"  # or "extension:{name}"
```

Foundation for:
- Volume naming (`vol_{owner_segment}_{path}` — Task 1.4)
- GUI read-only RMB gating (Task 1.10)
- Scope Config header signal derivation (Phase 3)
- Compose YAML metadata comments (post-Phase-1 polish)

Task 1.1 is a **schema-only** change. No consumer code reads the field yet — that lands in Tasks 1.2+.

---

## Acceptance Criteria

- [x] `MountSpecPath` dataclass gains `owner: str = "user"` field with docstring describing format and load-bearing downstream uses.
- [x] `validate()` rejects malformed owner values: anything other than `"user"` or `"extension:{non-empty-name}"` (empty name, bare `"extension:"`, bare `"claude"`, or empty string all produce an error).
- [x] `to_dict()` omits `owner` when value is `"user"` (default) — preserves Phase 1/2 JSON round-trip shape.
- [x] `to_dict()` emits `owner` when value differs from `"user"` (e.g., `"extension:claude"`).
- [x] `from_dict()` defaults missing `owner` key to `"user"` — legacy configs deserialize unchanged.
- [x] Test coverage in `test_mount_spec_path.py` new MSP-5 section: defaults, validation accept (user / extension:{name} / extension:my-tool), validation reject (bare name, `extension:`, empty), serialization (omit default / emit non-default / legacy default / round-trip).
- [x] `ARCHITECTUREGLOSSARY.md` — `MountSpecPath` Fields block gains `owner` bullet; JSON example gains an `"extension:claude"` row; cross-field constraints block notes `owner` format rule.
- [x] `ARCHITECTUREGLOSSARY.md` — STENCIL section Identifiers block gains `MountSpecPath.owner` forward-reference bullet noting Phase 1 Tasks 1.2–1.10 as consumers.
- [x] `pytest` on `IgnoreScope/tests/test_core/test_mount_spec_path.py` passes (71/71).
- [x] Full suite: no new regressions — the 2 pre-existing `test_integration.py` failures (Task 4.3 validator fixtures; to be fixed in Task 1.12) remain the only failures.

---

## Out of Scope (explicitly deferred)

- `ExtensionConfig.synthesize_mount_specs()` — Task 1.2
- Volume naming scheme change (`vol_{owner_segment}_{path}`) — Task 1.4
- `_collect_isolation_paths` deletion — Task 1.5
- Read-only RMB guard re-key — Task 1.10
- `COREFLOWCHART.md` / `DATAFLOWCHART.md` narrative updates — Task 1.14 (phase-wide Blueprint catch-up)

The `ARCHITECTUREGLOSSARY.md` edits in this task are inline per-task updates (the field exists → the field is documented). Narrative L4 rewrite and extension synth flow updates wait for their respective tasks.

---

## Files Touched

| File | Change |
|------|--------|
| `IgnoreScope/core/mount_spec_path.py` | Add `owner` field, validator rule, to_dict/from_dict handling, docstrings |
| `IgnoreScope/tests/test_core/test_mount_spec_path.py` | New MSP-5 section: 13 tests across 3 classes (defaults, validation, serialization) |
| `docs/architecture/ARCHITECTUREGLOSSARY.md` | MountSpecPath Fields `owner` bullet + example row + constraint line; STENCIL Identifiers block forward-reference bullet |

---

## Notes

**Scout report (Sonnet, pre-implementation):** Confirmed Task 1.1 inline doc scope = glossary MountSpecPath entry + STENCIL identifiers forward-reference only. COREFLOWCHART / DATAFLOWCHART / MIRRORED_ALGORITHM have no field-level references requiring update at this task's granularity — those land at Task 1.14.

**Round-trip invariant:** Default-`"user"` specs serialize to dicts without an `owner` key. Existing on-disk scope JSON files with no `owner` key deserialize cleanly with `owner == "user"`.
