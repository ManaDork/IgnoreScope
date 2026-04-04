---
description: "Capture a bug found during implementation."
---

# /zev-bug — Bug Capture

> Capture a bug found during implementation. Collects context, investigates the code path, writes a report. Does NOT fix the bug.

## Parse Argument

- **`{bug-name}`** — Use as the bug identifier
- **`list`** — Show existing bugs in `_workbench/_bugs/`
- **Empty** — Ask for a short bug name

## Workflow

### If `list`:
Read and summarize all files in `_workbench/_bugs/`. Show: filename, expectation, current behavior, date.

### Otherwise:

### Step 1: Collect User Input

Prompt for:
- **Expected behavior** — What should happen?
- **Current behavior** — What actually happens?
- **Reproduction steps** (optional) — How to trigger it?

### Step 2: Collect Context Automatically

Gather from current session:
- Current branch name
- Current task (from branch name / task doc)
- Recently modified files
- Active planning doc

### Step 3: Investigate

- Locate the code path related to the bug description
- Trace the execution path (ignore comments, trace actual code behavior)
- Identify likely root cause or area
- Note related functions and modules

### Step 4: Write Report

Create `_workbench/_bugs/{bug_name}.md`:

```markdown
# Bug: {Bug Name}

**Date:** {YYYY-MM-DD}
**Found during:** {branch} / {task description}
**Severity:** {estimate: low/medium/high/critical}

## Expected Behavior
{What should happen}

## Current Behavior
{What actually happens}

## Reproduction Steps
{How to trigger, if known}

## Investigation

### Code Path
{Traced execution path}

### Likely Root Cause
{Analysis of what's going wrong}

### Related Files
- `{file}:{line}` — {relevance}

## Context
- **Branch:** {current branch}
- **Task:** {current task}
- **Modified files:** {recently changed files}
```

### Step 5: Report

Print the file path. Do NOT offer to fix — bug capture is the scope.