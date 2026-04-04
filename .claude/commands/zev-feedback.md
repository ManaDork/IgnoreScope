---
description: "Capture feedback about the Zev workflow."
---

# /zev-feedback — Workflow Feedback

> Capture feedback about the Zev workflow — what's working, what isn't, suggestions. Creates a local report.

## Parse Argument

- **Empty** — Interactive feedback capture
- **`list`** — Show existing feedback in `_workbench/_feedback/`
- **`{topic}`** — Skip to capture with topic pre-filled

## Workflow

### If `list`:
Read and summarize all files in `_workbench/_feedback/`. Show: filename, topic, date.

### Otherwise:

### Step 1: Collect Context Automatically

- Project name: IgnoreScope
- Date: current date
- Current branch
- Current task (if any)

### Step 2: Prompt for Feedback

- **What were you doing?** — Which command, what task
- **What wasn't working?** — Friction, confusion, incorrect behavior, missing feature
- **Suggestions** — How should it work instead?

### Step 3: Write Report

Create `_workbench/_feedback/zev-feedback-{date}-{slug}.md`:

```markdown
# Zev Feedback: {Topic}

**Date:** {YYYY-MM-DD}
**Project:** IgnoreScope
**Branch:** {current branch}
**Task:** {current task}

## Context
{What was being done}

## Issue
{What wasn't working}

## Suggestion
{How it should work}

## Notes
{Any additional context}
```

### Step 4: Report

Print the file path. Remind user to copy file to Miriam_Dom project if submitting feedback upstream.