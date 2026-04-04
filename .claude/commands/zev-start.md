---
description: "Begin work on a task: fetch context, create branch, spawn zone agents. Use `/zev-start auto` for autonomous mode."
---

# /zev-start — Begin a Task

> Initializes a new task. If work already exists for this task, use `/zev-resume` instead.

## Step 1: Parse Argument

Extract the task description from `$ARGUMENTS`.

- **`auto [description]`** — Detect the `auto` keyword anywhere in arguments. Strip it and set `AUTO_MODE=true`. The remaining argument is the task description. If empty in auto mode, ask for a description.
- **Task description** — A short description of what to work on (e.g., "add system tray minimize", "fix docker cp permissions").
- **Empty or unrecognizable** — Ask the user for a task description. Never guess or make one up.

## Step 2: Derive Branch Name

From the task description:
1. Lowercase the description
2. Replace spaces/special chars with hyphens
3. Truncate to ~50 chars
4. Prefix with `feature/`, `bugfix/`, `hotfix/`, or `refactor/` based on description
5. Example: "add system tray minimize" → `feature/add-system-tray-minimize`

## Step 3: Guard Against Duplicate Work

Run `git -C "E:/SANS/SansMachinatia/_workbench/project_ignore_scope/IgnoreScopeDocker" branch -a` and check for branches with similar names.
Check `planning/tasks/` for existing task docs with matching names.

If work exists:
- **Normal mode:** Suggest `/zev-resume` instead.
- **Auto mode:** Continue working (skip the /zev-resume suggestion).

## Step 4: Create Feature Branch

```
git -C <project_root> checkout main
git -C <project_root> checkout -b {branch_name}
```

If the user specifies a base branch other than `main`, use that instead.

## Step 5: Load Planning Context

Check `planning/tasks/` for any existing task doc matching this work.
Check `planning/features/` for related feature specs.
Read Architecture Blueprints for the task area. Cross-reference against planned changes:
- Verify new functions/variables don't conflict with `ARCHITECTUREGLOSSARY.md` terms
- Verify ownership aligns with `COREFLOWCHART.md` module map
- If feature `technical-design.md` has "Architecture Doc Impact", check listed docs
Read `planning/backlog/` for related deferred items.

If a task doc exists, surface its requirements, AC, and approach.
If no task doc exists:
- **Normal mode:** Note that the user may want to run `/zev-feature` first for larger work.
- **Auto mode:** Create a lightweight task doc from the description.

## Step 6: Pre-Implementation Quality Gates

### DRY Audit
Scan modules the task will modify for existing duplication (Type 1/2/3).
Check for existing utility functions that cover the planned work.
If feature `scope.md` has DRY checkpoints, evaluate against current code.
Report findings in setup summary. Scope: affected zones only.

### Adherence Check
Read relevant Architecture Blueprints. Verify planned changes align with documented flows.
Flag conflicts as blockers. Set adherence level: Tracking, Planning, Structural, or GAP.

## Step 7: Spawn Exploration Agents

Based on the task description, pick relevant agent zones. Run in parallel with `run_in_background: true`.

### Agent Zones
| Zone | Paths | Triggers |
|------|-------|----------|
| Core Logic | `IgnoreScope/core/` | Config changes, hierarchy, node state, constants |
| Docker Layer | `IgnoreScope/docker/` | Container ops, lifecycle, compose, file operations |
| CLI | `IgnoreScope/cli/` | CLI commands, interactive mode, argument parsing |
| GUI | `IgnoreScope/gui/` | PyQt6 UI, views, models, style, delegates |
| Extensions | `IgnoreScope/container_ext/` | Claude ext, git ext, install, workflow setup |
| Tests | `tests/`, `IgnoreScope/tests/` | Test creation, test updates, test investigation |

Spawn agents for zones matching the task description. Always include Tests if code changes are expected.

### External Context
- **Docker Engine** — Container runtime via subprocess
- **Perforce** — VCS via p4 CLI (see `.p4config`)
- **GitHub** — Mirror sync via `scripts/sync_to_github.py`
- **Related repo:** p4mcp-server-linux (Perforce MCP server)

## Step 8: Report Setup Summary

Display:
- Task description
- Branch name created
- Planning docs found/created
- Architecture docs referenced
- DRY Audit findings
- Running agents and their zones
- Suggested approach based on findings

**Normal mode:** Wait for the user before beginning implementation.
**Auto mode:** Immediately begin implementation without waiting.

---

## Auto Mode Steps (only when AUTO_MODE=true)

### Step 9: Verify
- **9a: Test check** — Run `pytest` from the project root. If no tests exist for the changed code, note it but don't fail.
- **9b: Requirements check** — Map each acceptance criterion from the task doc to the diff. Check that each AC is addressed.
- **9c: Verdict** — If all checks pass, continue. If any check fails, attempt to fix (retry up to 3 times). If still failing, stop auto mode and hand control to user.

### Step 10: Auto-commit
Stage specific changed files (do NOT use `git add -A`). Commit with format:
```
[AI] Description of change
```

### Step 11: Auto-push
```
git -C <project_root> push -u origin {branch_name}
```

### Step 12: Auto-create PR
Use `gh pr create` with:
- Summary of implementation
- Acceptance criteria checklist
- Link to related planning docs

### Step 13: Auto-merge
```
gh pr merge --squash --delete-branch
```
If merge fails (branch protection, required reviews), report failure and leave PR open.

### Step 14: Completion Report
Display:
- Task description and branch name
- Files changed with brief descriptions
- Verification results
- PR link
- Suggest: `/zev-start auto {next task}` to continue

## Cross-Reference
- `/zev-start` initializes work. `/zev-resume` continues it.
- If `/zev-start` detects existing work, it suggests `/zev-resume`.
- If `/zev-resume` finds no prior work, it suggests `/zev-start`.