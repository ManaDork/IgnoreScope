---
description: "Pre-PR self-review: evaluate changes against requirements and acceptance criteria."
---

# /zev-review — Pre-PR Self-Review

> Evaluates changes against requirements before involving team reviewers. This is a self-review tool, not a replacement for team code review.

## Step 1: Detect Current Work

Run in parallel:
- `git -C <project_root> branch --show-current` — current branch
- `git -C <project_root> log main..HEAD --oneline` — commits on this branch
- `git -C <project_root> diff main...HEAD --stat` — files changed
- `git -C <project_root> diff main...HEAD` — full diff
- `git -C <project_root> status --short` — uncommitted changes

If on `main` with no changes, report "nothing to review" and suggest `/zev-start`.

## Step 2: Gather Requirements

Collect everything about what this task should accomplish:

### Planning Docs
- Read `planning/tasks/` for a doc matching the current branch/task
- Read `planning/features/` for related feature specs
- Read `planning/backlog/` for context on deferred scope

### Architecture Context
- Read relevant docs from `.claude/IgnoreScopeContext/architecture/`
- Check `ARCHITECTUREGLOSSARY.md` for applicable patterns (especially MatrixState)
- Check `COREFLOWCHART.md` for data flow alignment

If no planning docs or task docs exist, ask the user to describe expected behavior.

## Step 3: Collect All Changes

Build a complete picture:
- List all commits: `git -C <project_root> log main..HEAD --oneline`
- Full diff: `git -C <project_root> diff main...HEAD`
- File stats: `git -C <project_root> diff main...HEAD --stat`
- Note uncommitted changes separately

## Step 4: Spawn Deep Review Agents

For each major area of change, spawn an exploration agent to understand surrounding code context.

### Agent Zones
| Zone | Paths | Spawn When |
|------|-------|------------|
| Core Logic | `IgnoreScope/core/` | Changes touch core modules |
| Docker Layer | `IgnoreScope/docker/` | Changes touch Docker operations |
| CLI | `IgnoreScope/cli/` | Changes touch CLI commands |
| GUI | `IgnoreScope/gui/` | Changes touch UI components |
| Extensions | `IgnoreScope/container_ext/` | Changes touch extensions |
| Tests | `tests/`, `IgnoreScope/tests/` | Always — verify test coverage |

## Step 5: Conduct Review

Evaluate changes against requirements. Check for:

### Completeness
- Are all acceptance criteria addressed?
- Any requirements missed?

### Correctness
- Logic errors, edge cases, off-by-one
- None/null handling
- MatrixState patterns applied correctly (truth table evaluation, not gated chains)

### Security
- Injection risks (subprocess calls, Docker commands)
- Auth/authz gaps
- Secrets in code
- Path traversal risks (Docker mount paths)

### Performance
- Unnecessary subprocess calls
- Unbounded loops
- Missing error handling on Docker operations

### Error Handling
- Unhappy paths covered?
- Errors propagated correctly?
- User-facing messages helpful?

### Tests
- New/changed paths tested?
- Test names describe behavior?
- Coverage gaps?

### Style & Consistency
- Follows established patterns in the codebase?
- Naming conventions match
- **DRY Audit** — classify duplication in changed files AND surrounding modules: Type 1 (exact), Type 2 (renamed), Type 3 (extractable). If `scope.md` has DRY checkpoints, verify each addressed.
- **Review Drift** — naming consistency against `ARCHITECTUREGLOSSARY.md` terms. Flag mismatches.

### Dependencies
- Docker API interactions correct?
- PyQt6 patterns followed?
- pathspec usage correct?

### Architecture Blueprint Alignment
- Verify changes match documented flows in relevant Architecture Blueprints
- Flag Blueprints needing post-merge update
- If `technical-design.md` has "Architecture Doc Impact", verify each listed doc

### Bug Review
- Trace changed code paths for unintended side effects
- Check for regressions in adjacent functionality
- Verify error messages and user-facing behavior

## Step 6: Report Findings

```
## Review: {branch name}

### Summary
{One paragraph of what the changes do}

### Requirements Checklist
- [x] {AC item — pass}
- [ ] {AC item — fail/partial}

### Issues Found

#### Blocking
- **{file}:{line}** — {description}
  - Suggested fix: {fix}

#### Warnings
- **{file}:{line}** — {description}

#### Nits
- **{file}:{line}** — {description}

### DRY Audit Results
- **Type 1:** {exact duplicates found}
- **Type 2:** {renamed variable duplicates}
- **Type 3:** {extractable patterns}

### What Looks Good
- {Well-implemented aspects}

### Suggestions
- {Optional improvements — not blocking}

### Architecture Doc Updates Needed
- **{doc name}** — {what needs updating}
```

## Step 7: Offer Next Steps

Based on findings:
- **Blocking issues:** Offer to fix them now
- **Clean review:** Suggest committing and creating a PR via `/zev-publish`
- **Uncommitted changes:** Offer to commit first
- **Tests missing:** Offer to write them
- **Architecture docs flagged:** Offer to update or create backlog item