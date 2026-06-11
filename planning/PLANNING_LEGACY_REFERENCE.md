# PLANNING_LEGACY_REFERENCE — Where the Old Planning Files Went

**For agent Zev (and any agent reconstructing history).** On 2026-06-10 this project's planning tree had grown stale and was archived wholesale; `planning/` was recreated empty for the fresh Zev deployment. This file is the map back to the old material.

## Archive location

```
E:\SANS\SansMachinatia\_workbench\archive\IgnoreScope\zev-v3-install-archive-2026-06-10\
  planning\            ← the entire legacy planning tree, moved verbatim
    backlog\             deferred work items (incl. backlog\deferred\)
    features\            feature specs: {name}\spec.md + technical-design.md + scope.md
                         (incl. features\_archive\config-panel-collapse-fix\,
                          features\fusion-custom-title-bar\, features\deferred\)
    reference\           reference material kept alongside planning
    tasks\               task docs (incl. tasks\done\ — e.g. virtual-mount-phase-3.md,
                          unify-l4-task-1-1-owner-field.md, unify-l4-task-1-5-delete-collect-isolation.md)
    README.md            the legacy planning tree's own orientation doc
  claude\agents\zev.md   ← the project's old bindings + Agent Zones (answer key for redeploy)
  CLAUDE.md.snapshot     ← CLAUDE.md as of archive date (zev sections intact)
  ARCHIVE_MANIFEST.md    ← full inventory + restore procedure
```

This archive path is registered as an additional working directory in this project's Claude Code setup, so Read/Glob/Grep reach it directly.

## How to dig (instructions for Zev)

1. **Lookups go to `zev-pa`** — batch them, pass ABSOLUTE archive paths (zev-pa's default scope is the project root; the archive is outside it). Example ask: *"Glob `<archive>\planning\tasks\**\*.md`, return filename + first H1 + any 'Decisions Locked' block."*
2. **Branch/task slug convention** — legacy branch names map to task docs by slug: strip `feature/` | `bugfix/` | `hotfix/` | `refactor/` from the branch name → `planning\tasks\<slug>.md` (check `tasks\done\` next). Same rule the live suite uses.
3. **Decisions headings** — the canonical heading is `Decisions Locked`; legacy docs may use the aliases `Decided` or `Resolved`. Search all three.
4. **Checkboxes are NOT state** — legacy task docs contain `- [ ]`/`- [x]` AC boxes. They are historical artifacts from before TaskList became authoritative; read them as a record of intent, never as current status.
5. **Features are 3-doc folders** — `spec.md` (problem/AC/out-of-scope), `technical-design.md` (look for an "Architecture Doc Impact" section), `scope.md` (task table with DRY Checkpoint column). `features\_archive\` holds completed/abandoned ones.
6. **Git history still has everything** — the planning files were git-tracked until the archive commit. `git -C <project_root> log --follow -- planning/<path>` recovers any file's full history; `git show <sha>:planning/<path>` retrieves old revisions without touching the archive at all.
7. **Cross-referencing old work** — when a legacy item resurfaces (e.g. `fusion-custom-title-bar`), do NOT resume the legacy doc in place. Bring it through the live pipeline: `/zev-brainstorm` (concept) or `/zev-feature` (build-worthy), citing the archive path in `Source:`/`Related:` so the lineage is explicit.

## Rules for this folder going forward

- New planning material is created ONLY by the live Zev suite (`/zev-feature`, `/zev-discuss`, `/zev-backlog`, `/zev-brainstorm`) under the recreated `tasks\`, `features\`, `backlog\`, `brainstorm\`.
- Nothing gets copied back from the archive wholesale — pull individual items through the pipeline (rule 7) so stale content can't quietly re-contaminate the tree.
