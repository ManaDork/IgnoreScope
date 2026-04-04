# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**IgnoreScope** is a Docker container management CLI + GUI that authors mounted folder structures. It uses Docker volume layering to hide directories while allowing specific files to be pushed/pulled at runtime via `docker cp`.

## Code Practice
- **Correctness and readability over premature optimization.**

## Key Concepts
- **MatrixState**: Prefer truth table evaluation over gated conditional chains when deriving state from multiple boolean flags. Compute each flag independently, then match against explicit condition tuples. See `ARCHITECTUREGLOSSARY.md → MatrixState`. Applied in `core/node_state.py`.
- **DRY Audit**: Scan for duplicated logic across modules. Classify clones: Type 1 (exact copy-paste), Type 2 (renamed variables, same structure), Type 3 (similar pattern, extractable). Report file, lines, severity, extraction opportunity.
- **Extract Method Refactor**: Consolidate duplicated code blocks into a shared function/base-class method. Preserves behavior — only changes structure.
- **Review Drift**: Pair with DRY Audit, watch for variable and function name inconsistencies

## Workflow

| Trigger | Action | Check Against | Halt |
|---------|--------|---------------|------|
| Adding new variables, functions, or modules | DRY Audit (Type 1/2/3) + naming check | `ARCHITECTUREGLOSSARY.md`, `COREFLOWCHART.md` | On GAP |
| Proposing architecture or design | Read Architecture Blueprints before designing | All domain-relevant Blueprints | On conflict |
| Debugging or tracing code | Confirm variable names, path formulas, ownership | `ARCHITECTUREGLOSSARY.md`, `COREFLOWCHART.md` | No |
| Plan, feature spec, or implementation complete | Conflict check against Blueprints; flag docs needing update | All affected Blueprints | On GAP |
| User input ambiguous (not directly referencing code) | Ask user if intent is relative to existing structure or new feature; narrow scope | Ask user | Yes |
| User requests architecture update | Update Architecture Blueprints | Specified docs | No |

### Architecture Blueprints
`.claude/IgnoreScopeContext/architecture/` — canonical design reference. Always-on, not gated to commands.

| Document | Domain |
|----------|--------|
| `ARCHITECTUREGLOSSARY.md` | All — terms, patterns, state values, domain ownership |
| `COREFLOWCHART.md` | Core, Docker, CLI, Extensions — data flow, phase pipeline |
| `DATAFLOWCHART.md` | GUI — data flow, module responsibility |
| `MIRRORED_ALGORITHM.md` | Core — mirrored intermediate computation |
| `GUI_STATE_STYLES.md` | GUI — state visual definitions |
| `GUI_LAYOUT_SPECS.md` | GUI — widget layout spec |
| `GUI_STRUCTURE.md` | GUI — widget hierarchy and sizing |

## Tool Preferences

### Git
- **for all git operations**: Always use `git -C <path>` instead of `cd <path> && git` 

### JetBrains MCP (Prefer Over Built-in Tools)
- **Read files**: Use `get_file_text_by_path` over Read tool
- **Edit files**: Use `replace_text_in_file` over Edit tool (supports regex)
- **Create files**: Use `create_new_file` over Write tool (auto-creates parent dirs)
- **Search by name**: Use `find_files_by_name_keyword` over Glob (faster, uses indexes)
- **Search by content**: Use `search_in_files_by_text` / `search_in_files_by_regex` over Grep
- **Context**: Use `get_all_open_file_paths` to see what the user is working on
- **Navigation**: Use `get_symbol_info` to understand symbols, types, and declarations
- **Refactoring**: Use `rename_refactoring` for symbol renames (project-wide safe)
- **Inspections**: Use `get_file_problems` to validate changes
- **Formatting**: Use `reformat_file` after edits to match project style
- **Present work**: Use `open_file_in_editor` to show the user modified/relevant files
- **Context**: Use `get_all_open_file_paths` first when the user asks a question — their open files indicate what they're focused on
- **Present work**: Use `open_file_in_editor` to show files relevant to the current investigation or answer then give them line # to look at.

# DEBUG COMMUNICATIONS
- `Trace Full Code Path`: Trace the full stack of the functions by the code ignoring comments descriptions; Collect comments associated with the stack for post comparison, conflicting intentions, terminology inconsistency, redundant behaviors from other stacks.

# ARCHITECTURE REVIEWS
- Applies to `Review`, `Analyse`, `Inspect`: Trace the full stack of the functions by code ignoring the comments descriptions; Collect comments associated with the stacks. After full code trace of each stack, Compare all comments for conflicting intentions, terminology inconsistency, redundant behaviors from other stacks, ownership inconsistency.

## Workflow Configuration

### Commands
| Command | Purpose |
|---------|---------|
| `/zev-project` | Guided architecture scaffolding (lite, brainstorm, review) |
| `/zev-feature` | Specify **what** to build — feature spec, technical design, scope |
| `/zev-discuss` | Plan **when/how** to execute — task planning, scheduling, backlog |
| `/zev-start` | Begin a task — fetch context, create branch, spawn zone agents. Use `/zev-start auto` for autonomous mode. |
| `/zev-resume` | Continue after a break — reconstruct context from durable state |
| `/zev-review` | Pre-PR self-review — evaluate changes against requirements |
| `/zev-sync` | Pull latest and rebase current branch onto base branch |
| `/zev-backlog` | Quick-capture a backlog item from conversation context |
| `/zev-publish` | Publish work — commit, push, tag, PR with confirmation checkpoints |
| `/zev-bug` | Capture bugs discovered during adjacent feature implementation |
| `/zev-feedback` | Capture Zev workflow friction and improvement suggestions |

### Quality Procedures
| Procedure | When | What |
|-----------|------|------|
| DRY Audit | /zev-start, /zev-resume | Spawn GP agent to classify duplication (Type 1/2/3) against affected zones |
| Adherence Check | /zev-start, /zev-resume, /zev-feature | Consult DOCUMENTATION table, apply ADHERENCE rules for affected zones |
| Bug Review | /zev-review, /zev-publish | Check `_workbench/_bugs/` for reports filed during this branch |

### Task Management
- **Provider:** None (manual task descriptions)
- **Task docs:** `planning/tasks/{task-name}.md`

### Build & Test
- **Build command:** (none — pure Python package)
- **Test command:** `pytest`

### Git Conventions
- **Branch format:** `{type}/short-name` (prefixes: `feature/`, `bugfix/`, `hotfix/`, `refactor/`)
- **Commit format:** `[AI] Description of change`
- **Default base branch:** `main`
- **AI marker:** `[AI]` prefix

### Agent Zones
| Zone | Paths | Triggers |
|------|-------|----------|
| Core Logic | `IgnoreScope/core/` | Config, hierarchy, node state, constants |
| Docker Layer | `IgnoreScope/docker/` | Container ops, lifecycle, compose, file ops |
| CLI | `IgnoreScope/cli/` | Commands, interactive mode, argument parsing |
| GUI | `IgnoreScope/gui/` | PyQt6 UI, views, models, style, delegates |
| Extensions | `IgnoreScope/container_ext/` | Claude ext, git ext, install, workflow |
| Tests | `tests/`, `IgnoreScope/tests/` | Test creation, updates, investigation |

### Key Locations
| Path | Purpose |
|------|---------|
| `IgnoreScope/` | Main package — all source code |
| `tests/` | Top-level test directory |
| `scripts/` | Build/deploy scripts |
| `Icons/` | GUI assets (git-ignored) |
| `planning/` | Feature specs, task docs, backlog |
| `.claude/IgnoreScopeContext/architecture/` | Architecture Blueprints (see Workflow section) |
| `planning/backlog/` | Parked work items and feature pointers |
| `.claude/TODOs/` | Legacy work items (migrated to `planning/backlog/`) |
| `_workbench/_bugs/` | Bug reports (created by `/zev-bug`) |
| `_workbench/_feedback/` | Zev feedback reports (created by `/zev-feedback`) |

### DOCUMENTATION
| Name | Path | Domain |
|------|------|--------|
| `ARCHITECTUREGLOSSARY.md` | `.claude/IgnoreScopeContext/architecture/` | All — terms, patterns, state values, domain ownership |
| `COREFLOWCHART.md` | `.claude/IgnoreScopeContext/architecture/` | Core, Docker, CLI, Extensions — data flow, phase pipeline |
| `DATAFLOWCHART.md` | `.claude/IgnoreScopeContext/architecture/` | GUI — data flow, module responsibility |
| `MIRRORED_ALGORITHM.md` | `.claude/IgnoreScopeContext/architecture/` | Core — mirrored intermediate computation |
| `GUI_STATE_STYLES.md` | `.claude/IgnoreScopeContext/architecture/` | GUI — state visual definitions |
| `GUI_LAYOUT_SPECS.md` | `.claude/IgnoreScopeContext/architecture/` | GUI — widget layout spec |
| `GUI_STRUCTURE.md` | `.claude/IgnoreScopeContext/architecture/` | GUI — widget hierarchy and sizing |

### PROJECT ARCHITECTURE
| Document | Purpose | Adherence |
|----------|---------|-----------|
| `ARCHITECTUREGLOSSARY.md` | Domain terms, patterns, ownership | Structural |
| `COREFLOWCHART.md` | Core data flow, phase pipeline | Structural |
| `DATAFLOWCHART.md` | GUI data flow, module responsibility | Structural |
| `MIRRORED_ALGORITHM.md` | Mirrored intermediate computation | Structural |
| `GUI_STATE_STYLES.md` | State visual definitions | Planning |
| `GUI_LAYOUT_SPECS.md` | Widget layout spec | Planning |
| `GUI_STRUCTURE.md` | Widget hierarchy and sizing | Planning |

### ADHERENCE
| Level | Trigger | Action | Halt |
|-------|---------|--------|------|
| Tracking | Any file change in governed zone | Update doc if out of date | No |
| Planning | /zev-feature, /zev-discuss | Check doc alignment, update if conflict | No |
| Structural | /zev-feature, /zev-discuss, /zev-start, /zev-resume | Read doc, resolve gaps with user | On conflict |
| GAP | Any interaction with governed zone | Halt execution, surface to user | Yes |

### External Dependencies
- **Docker Engine** — Container runtime, accessed via subprocess
- **Perforce** — VCS via p4 CLI (see `.p4config`)
- **GitHub** — Mirror sync via `scripts/sync_to_github.py`
- **Related repo:** [p4mcp-server-linux](https://github.com/ManaDork/p4mcp-server-linux.git) — Perforce MCP server

### Planning
- **Feature specs:** `planning/features/{feature-name}/` (created by `/zev-feature`)
- **Task plans:** `planning/tasks/{task-name}.md` (created by `/zev-discuss` or `/zev-start`)
- **Backlog:** `planning/backlog/`
- **Architecture (existing):** `.claude/IgnoreScopeContext/architecture/`
- **TODOs (existing):** `.claude/TODOs/` 