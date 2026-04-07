# Active Config Monitoring

## Status: TODO

## Problem

Pattern ordering errors in `scope_docker.json` silently produce wrong visibility states.
Exception patterns placed BEFORE their covering deny are overridden by gitignore last-match-wins semantics, but no warning is shown to the user.

Example: `!Content/__ExternalActors__/` placed before `Content/` — the Content/ deny overrides all 8 exceptions, making them appear masked instead of revealed.

## Proposed Feature

Real-time pattern validation that warns when:
- Exception patterns precede their covering deny (ineffective ordering)
- Exception patterns have no covering deny at all (already validated by `MountSpecPath.validate()`)
- Pattern changes would create container orphans (already implemented in `detect_orphan_creating_removals()`)

## Reference

Old IgnoreScope had config monitoring — check archive at:
- `E:\SANS\SansMachinatia\_workbench\archive\IgnoreScope\utils\pattern_conflict.py`
- `E:\SANS\SansMachinatia\_workbench\archive\IgnoreScope\ignore_scope_hooks\`

Current validation in `MountSpecPath.validate()` catches missing deny parents but NOT ordering issues.

## Files

- `core/mount_spec_path.py` — `validate()` method, add ordering check
- `core/pattern_conflict.py` — existing conflict detection module
- `gui/` — surface warnings in UI (tooltip, status bar, or dialog)
