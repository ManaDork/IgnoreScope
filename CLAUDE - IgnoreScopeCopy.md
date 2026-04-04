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