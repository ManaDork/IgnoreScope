---
description: "Plan when and how to execute: task planning, scheduling, and backlog management."
---

# /zev-discuss — Execution Planning

> Plan **when** and **how** to execute work: task planning, scheduling, and backlog management. For specifying **what** to build, use `/zev-feature` instead.

## Step 1: Parse Argument

Extract topic from `$ARGUMENTS`:
- **Task name** — Discuss implementation of a specific task
- **`backlog`** — Review and manage the backlog
- **Feature name** — Plan execution of a feature spec from `planning/features/`
- **Empty** — Ask what they want to plan

## Step 2: Gather Context

Read existing planning docs relevant to the topic:
- `planning/features/` — feature specs that provide task breakdowns and scope
- `planning/tasks/` — existing task docs
- `planning/backlog/` — deferred items
- `.claude/IgnoreScopeContext/architecture/` — relevant Architecture Blueprints

Check git history for recent work context:
- `git -C <project_root> log --oneline -20` — recent commits
- `git -C <project_root> branch -a` — existing branches (to avoid duplicate work)

## Step 3: Planning Discussion

Adapt based on the topic:

### Task Planning
- Discuss implementation approach for a specific task
- Surface relevant architecture constraints from Blueprints
- Identify affected zones and dependencies
- Check for DRY risks in planned changes
- Create or update task doc in `planning/tasks/{task-name}.md`

### Feature Execution
- Read the feature spec from `planning/features/{name}/`
- Break feature scope into ordered tasks with dependencies
- Identify phases and priorities
- Check DRY checkpoints from `scope.md`
- Write task docs for each planned item

### Backlog Management
- Review `planning/backlog/` items
- Prioritize and categorize
- Pull items into active work or defer further
- Park items discovered during discussion

## Step 4: Explore as Needed

Spawn agents to answer codebase questions that arise during planning.

### Agent Zones
| Zone | Paths | Triggers |
|------|-------|----------|
| Core Logic | `IgnoreScope/core/` | Questions about config, hierarchy, node state |
| Docker Layer | `IgnoreScope/docker/` | Questions about container operations |
| CLI | `IgnoreScope/cli/` | Questions about commands, argument parsing |
| GUI | `IgnoreScope/gui/` | Questions about UI, views, models |
| Extensions | `IgnoreScope/container_ext/` | Questions about extensions |
| Tests | `tests/`, `IgnoreScope/tests/` | Questions about test coverage |

## Step 5: Produce Artifacts

Write planning docs as agreed. Always ask before creating files:
- Task docs: `planning/tasks/{task-name}.md`
- Backlog items: `planning/backlog/{item-name}.md`

## Step 6: Offer Next Steps

- Suggest `/zev-start` to begin work on the first task
- Suggest `/zev-feature` if requirements need to be specified first
- Suggest `/zev-backlog` for quick backlog captures during work