---
description: "Continue work after a session break: reconstruct context from durable state."
---

# /zev-resume — Continue Work

> Reconstructs context from git state, planning docs, and task history. Use `/zev-start` to begin new work.

## Step 1: Detect Current Work from Git

Run in parallel:
- `git -C <project_root> branch --show-current` — current branch
- `git -C <project_root> log main..HEAD --oneline` — commits on this branch
- `git -C <project_root> status --short` — uncommitted changes
- `git -C <project_root> diff --stat` — unstaged change summary

Extract task context from branch name (strip prefix, convert hyphens to words).

If on `main` with no changes, report "no active work found" and suggest `/zev-start`.

## Step 2: Fetch Task Context

Look for task docs matching the branch name or extracted description:
- Check `planning/tasks/` for matching task docs
- Check `planning/features/` for related feature specs
- Check `planning/backlog/` for related deferred items

## Step 3: Check Progress

- Check for Claude Code tasks via TaskList
- Read planning context:
  - Read task doc if found — check approach/notes sections for progress
  - Read feature spec if related — check which deliverables are addressed
  - Read `planning/backlog/` for items deferred from this work
- Summarize: what's done (from commits), what's in progress (from uncommitted), what's next

## Step 4: Quality Gates on Existing Changes

### DRY Audit
Scan uncommitted and branch changes for duplication (Type 1/2/3).

### Adherence Check
Read relevant Architecture Blueprints. Verify current changes align with documented flows.

## Step 5: Spawn Exploration Agents

Based on the task description and changed files, pick relevant agent zones. Run in parallel with `run_in_background: true`.

### Agent Zones
| Zone | Paths | Triggers |
|------|-------|----------|
| Core Logic | `IgnoreScope/core/` | Config changes, hierarchy, node state, constants |
| Docker Layer | `IgnoreScope/docker/` | Container ops, lifecycle, compose, file operations |
| CLI | `IgnoreScope/cli/` | CLI commands, interactive mode, argument parsing |
| GUI | `IgnoreScope/gui/` | PyQt6 UI, views, models, style, delegates |
| Extensions | `IgnoreScope/container_ext/` | Claude ext, git ext, install, workflow setup |
| Tests | `tests/`, `IgnoreScope/tests/` | Test creation, test updates, test investigation |

## Step 6: Report Status

Display:
- Task description (from branch name / task doc)
- Git state: branch, commits so far, uncommitted changes
- Planning progress: what's done, what's next
- Architecture docs referenced
- Running agents and their zones
- Suggested next action

## Step 7: Continue

Resume work with agent follow-up instructions.

### Workflow Reminders
- **Commit format:** `[AI] Description of change`
- **Branch format:** `{type}/short-name`
- **Base branch:** `main`
- Follow up on agent results as they complete
- Update task doc notes as you work

## Cross-Reference
- `/zev-resume` continues work. `/zev-start` initializes it.
- If `/zev-resume` finds no prior work, it suggests `/zev-start`.
- If `/zev-start` detects existing work, it suggests `/zev-resume`.