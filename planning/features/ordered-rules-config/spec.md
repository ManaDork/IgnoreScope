# Feature: Ordered Rules Config

> **SUPERSEDED** — This VolumeRule-based design was replaced by the MountSpecPath architecture. See `ARCHITECTUREGLOSSARY.md → MountSpecPath`.

## Problem Statement

IgnoreScope's Docker volume configuration uses flat `set[Path]` for `masked` and `revealed` directories. This creates a hard limitation: **reveals expose ALL descendants with no way to re-mask within a revealed area**. The root causes are:

1. `compute_visibility()` has an absolute `revealed > masked` priority
2. `hierarchy.py` uses a fixed 3-layer volume ordering (mounts -> masks -> reveals)
3. `LocalMountConfig` stores masks/reveals as unordered sets -- no layering semantics

Docker's compose volumes ARE linear and support interleaved layers (last-writer-wins). The config model doesn't leverage this.

**Who it's for:** Any user working with large directory trees (e.g., UE5 projects) where reveals need granular scoping -- expose `Content/Maps` but re-mask `Content/Maps/Cache`.

## Success Criteria

1. User can create a nested mask within a revealed folder (mask -> reveal -> nested mask)
2. Docker container filesystem reflects the nested layering correctly
3. GUI tree view shows correct visibility at each nesting level
4. Existing configs auto-migrate without data loss
5. Checkbox toggle UX preserved -- mask/reveal checkboxes still work (append-at-end)

## User Stories

- As a developer, I want to reveal a folder within a masked area AND re-mask specific subfolders within it, so that I can expose only the content I need without leaking large cache/build directories
- As a developer, I want to see the ordered rule list so I can understand and reorder the volume layering
- As a developer, I want my existing configs to migrate automatically when I update IgnoreScope

## Acceptance Criteria

- [ ] `VolumeRule(action, path)` dataclass replaces `masked`/`revealed` flat sets in `LocalMountConfig`
- [ ] Rules evaluate in order, last matching rule wins (gitignore semantics)
- [ ] Docker compose volumes are generated in rule order (interleaved masks and reveals)
- [ ] `compute_node_state()` evaluates rules instead of flat set membership
- [ ] Mask/Reveal checkboxes in tree columns still work (append rule at end, remove on uncheck)
- [ ] Context menu allows "Add Mask Rule" under revealed folders (new capability)
- [ ] Rule list panel shows ordered rules with drag-to-reorder
- [ ] Ordering conflict warnings shown when reveal appears before its parent mask
- [ ] Old config format (`masked`/`revealed` arrays) auto-migrates to `rules` array
- [ ] All 95+ existing tests updated and passing
- [ ] New tests cover nested mask/reveal scenarios
- [ ] `NodeState.masked`/`NodeState.revealed` boolean flags remain unchanged (display system untouched)
- [ ] Architecture blueprints updated (ARCHITECTUREGLOSSARY, COREFLOWCHART, MIRRORED_ALGORITHM)

## Out of Scope

- Glob/wildcard pattern matching (reserved for future `pathspec` extension)
- File-level rules (Docker volumes are folder-only; files use `pushed_files` via docker cp)
- `pathspec` pip dependency (absolute paths + `is_descendant()` only)
- Changes to `NodeState` dataclass or `compute_visibility()` truth table
- Changes to display system (delegates, proxy filters, tooltips)

## Open Questions

- None remaining -- all design decisions resolved during planning session
