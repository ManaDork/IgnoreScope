# planning/

Active feature specs, task plans, and backlog items for IgnoreScope. Most files in this tree are gitignored; the force-tracked subset is listed below.

## Subfolder convention

| Folder | Status |
|---|---|
| `features/`, `tasks/`, `backlog/` | Active, in-progress, or queued work |
| `*/done/` | Shipped, acceptance criteria satisfied |
| `*/_archive/` | Abandoned or superseded designs (kept for historical reference) |
| `*/deferred/` | Valid-but-paused work waiting on a precondition |

The `_archive/` underscore prefix sorts these dirs to the top of file listings, signalling "look here for context" before the active items.

## Force-tracked files

Most of `planning/` is gitignored. These specific files are force-tracked (`git add -f`) and committed to the repo:

- `planning/backlog/fusion-custom-title-bar.md` — pending Phase C user disposition
- `planning/features/_archive/config-panel-collapse-fix/{scope,spec,technical-design}.md`
- `planning/tasks/done/unify-l4-task-1-1-owner-field.md`
- `planning/tasks/done/unify-l4-task-1-5-delete-collect-isolation.md`
- `planning/tasks/done/virtual-mount-phase-3.md`

Force-tracking is a per-file decision; the rest of the tree is local-only.

## Provenance

Convention adopted 2026-05-03 in `refactor/project-cleanup` (Phase B.5). Source plan: `_workbench/_evaluations/project-cleanup-2026-05-02.md`.
