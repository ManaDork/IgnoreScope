---
description: "Publish work: commit, push, and optionally tag or create PR."
---

# /zev-publish — Publish Work

> Publish current work: commit, push, and optionally tag or create PR. For pre-publish review, run `/zev-review` first. For autonomous publishing, use `/zev-start auto`.

## Parse Argument

- **Empty** — Commit + push
- **`pr`** — Commit + push + create PR
- **`tag {version}`** — Commit + push + tag
- **`release {version}`** — Commit + push + tag + create PR
- **`--dry-run`** — Show what would happen without executing
- **`--skip-review`** — Skip the /zev-review suggestion

## Step 1: Detect State

Run in parallel:
- `git -C <project_root> branch --show-current`
- `git -C <project_root> status --short`
- `git -C <project_root> log main..HEAD --oneline`
- `git -C <project_root> diff --stat`

## Step 2: Suggest Review

Unless `--skip-review` is set, check if `/zev-review` has been run on this branch recently.
If not, suggest running it first. Ask the user to confirm proceeding without review or run `/zev-review` now.

## Step 3: Stage and Commit (with confirmation)

If there are uncommitted changes:
1. Show the changes to the user
2. Stage relevant files (NOT `git add -A` — be selective, exclude `.env`, `__pycache__/`, etc.)
3. **Ask for confirmation** before committing
4. Commit with format: `[AI] Description of change`

## Step 4: Push (with confirmation)

1. Show what will be pushed (commits, branch)
2. **Ask for confirmation** before pushing
3. `git -C <project_root> push -u origin {branch_name}`

## Step 5: Tag (if applicable, with confirmation)

If `tag` or `release` mode:
1. Show the tag that will be created
2. **Ask for confirmation**
3. `git -C <project_root> tag {version}`
4. `git -C <project_root> push origin {version}`

## Step 6: Create PR (if applicable, with confirmation)

If `pr` or `release` mode:
1. Draft PR title and body from commits and task docs
2. Show the draft to the user
3. **Ask for confirmation**
4. `gh pr create --title "{title}" --body "{body}"`

## Step 7: Bug Review

Quick scan of changes for obvious bugs before finalizing:
- Trace changed code paths for unintended side effects
- Check subprocess calls for injection risks
- Verify error handling on Docker operations

## Step 8: Report Summary

Display:
- Branch and commits published
- Tag created (if applicable)
- PR link (if applicable)
- Any warnings from bug review