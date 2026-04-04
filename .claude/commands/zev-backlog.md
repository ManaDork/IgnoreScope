---
description: "Quick-capture a backlog item from conversation context."
---

# /zev-backlog — Quick Backlog Capture

> Quick-capture a backlog item from conversation context. For full backlog management, use `/zev-discuss backlog`.

## Parse Argument

- **Empty** — Infer concept from recent conversation context
- **`list`** — Show existing items in `planning/backlog/`
- **`{concept}`** — Use as the item description

## Workflow

### If `list`:
Read and summarize all files in `planning/backlog/`. Show: filename, "What" line, date.

### Otherwise:

1. **Extract concept** — From arguments or recent conversation context
2. **Derive filename** — Kebab-case slug: `planning/backlog/{concept-slug}.md`
3. **Check for duplicates** — Scan `planning/backlog/` for similar items. If found, ask if this is the same item or distinct.
4. **Write item:**

```markdown
# Backlog: {Concept Name}

**What:** {Brief description of the item}
**Why deferred:** {Why this isn't being done now}
**Implementation notes:** {Any technical details or approach ideas}
**Pull when:** {Conditions under which this should be pulled into active work}
**Source:** {Branch/task/conversation that surfaced this}
**Date:** {YYYY-MM-DD}
**Related:** {Links to features, tasks, or architecture docs}
```

5. **Report** — Print the file path. No next steps — speed is the priority.