# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**IgnoreScope** is a Docker container management CLI + GUI that authors mounted folder structures. It uses Docker volume layering to hide directories while allowing specific files to be pushed/pulled at runtime via `docker cp`.

- Project quick reference: `.claude/IgnoreScopeContext/IGNORESCOPEREF.md`

## Architecture Blueprints 
- `.claude/IgnoreScopeContext/architecture/COREFLOWCHART.md` — backend phases, rules, module map
- `.claude/IgnoreScopeContext/architecture/DATAFLOWCHART.md` — GUI data flow, rules
- `.claude/IgnoreScopeContext/architecture/ARCHITECTUREGLOSSARY.md` — canonical term definitions (target system)

## Active Initiative: Sibling Unification
- `.claude/IgnoreScopeContext/architecture/MOUNT_DATA_TREE.md` — initiative overview, domain impacts, approved conflicts
- `.claude/IgnoreScopeContext/architecture/SHARED_CLASS_PHASE1.md` — core/docker/cli changes (LocalMountConfig + JSON schema)
- `.claude/IgnoreScopeContext/architecture/GUI_MAIN_PHASE2.md` — tree + view adaptation (MountDataTree hosts siblings)
- `.claude/IgnoreScopeContext/architecture/GUI_SIBLING_PHASE3.md` — sibling UX workflow (folder picker, panel removal)

## Development Commands
- Commands: `.claude/IgnoreScopeContext/DEVELOPMENTCOMMANDS.md`

## Project State
- IN REFACTOR
- OBJECTIVE: Architecture Flow: `.claude/IgnoreScopeContext/architecture/COREFLOWCHART.md`
- Consolidate logic to CORE  
- Prioritize unified terminology (see `.claude/IgnoreScopeContext/architecture/ARCHITECTUREGLOSSARY.md`)
- GUI logic removal `.claude/IgnoreScopeContext/architecture/DATAFLOWCHART.md`  

## Code Practice
- **Correctness and readability over premature optimization.**

## Key Concepts
- **MatrixState**: Prefer truth table evaluation over gated conditional chains when deriving state from multiple boolean flags. Compute each flag independently, then match against explicit condition tuples. See `ARCHITECTUREGLOSSARY.md → MatrixState`. Applied in `core/node_state.py`.
- **DRY Audit**: Scan for duplicated logic across modules. Classify clones: Type 1 (exact copy-paste), Type 2 (renamed variables, same structure), Type 3 (similar pattern, extractable). Report file, lines, severity, extraction opportunity.
- **Extract Method Refactor**: Consolidate duplicated code blocks into a shared function/base-class method. Preserves behavior — only changes structure.
- **Review Drift**: Pair with DRY Audit, watch for variable and function name inconsistencies  

## WORKFLOW
- **When input not directly referencing or matching code** Ask User if intent is relative to existing structure or feature, if Yes; Identify meta feature with user to narrow down scope.
- **When new variables and functions are being added** DRY Audit to Prevent Drift
- Check ARCHITECTUREGLOSSARY.md
- Check COREFLOWCHART.md
- Check DATAFLOWCHART.md
- Expose GAPS to resolve into `Architecture Blueprints` 

### IGNORESCOPEREF.md
- **When planning refactor:** `Write Intents of Intiative then Locate conflicts with `Architecture Blueprints` with User in {Initative}.md's.`  
- **When planning:** Read `Architecture Blueprints` before designing
- **When planning:** DRY Audit when new functions are being added 
- **When planning:** Review Drift from planning phase intent against current code  
- **When debugging:** Read `Architecture Blueprints` to confirm correct variable names and path formulas before tracing code
- **On plan completion:** Check conflicts with `Architecture Blueprints` to resolve or update `Architecture Blueprints` 
- **On user request:** Update `Architecture Blueprints` when user explicitly asks to record something

## Tool Preferences

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