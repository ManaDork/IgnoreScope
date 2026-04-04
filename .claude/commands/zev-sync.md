---
description: "Pull latest changes and rebase current branch onto main."
---

# /zev-sync — Sync Branch

> Pulls latest changes and rebases your current branch onto `main`. Safe by default — never force-pushes or discards changes.

## Step 1: Gather Current State

Run in parallel:
- `git -C <project_root> branch --show-current`
- `git -C <project_root> status --short`
- `git -C <project_root> remote`

## Step 2: Commit Uncommitted Changes if Needed

If there are uncommitted changes (staged or unstaged, but NOT untracked-only):
1. Show the user the changes
2. Stage modified/deleted files with `git -C <project_root> add -u`
3. Stage new files that look like project code (not build artifacts, `.env`, `__pycache__/`, etc.)
4. Commit with format: `[AI] WIP: save changes before sync`

If the working tree is clean, continue.

## Step 3: Sync the Branch

- **On `main`:** `git -C <project_root> pull --rebase origin main`
- **On a feature branch:** `git -C <project_root> fetch origin main && git -C <project_root> rebase origin/main`

## Step 4: Conflict Resolution

When `git rebase` stops due to conflicts:
1. List conflicted files: `git -C <project_root> diff --name-only --diff-filter=U`
2. For each conflicted file:
   - Read the file to understand both sides
   - Resolve intelligently: superset wins, combine independent changes, prefer main for structural changes
   - Ask user for ambiguous cases
3. Stage resolved files and continue: `git -C <project_root> rebase --continue`
4. If conflicts are too complex, abort: `git -C <project_root> rebase --abort` and report to user

## Step 5: Report Results

Show:
- Branch name
- Whether new commits were pulled/rebased
- Conflict resolution summary (if any)
- Current git status

---

## Safety Rules (HARD RULES — never violate)

- **NEVER** run `git push --force`, `git push --force-with-lease`, or any force push variant
- **NEVER** run `git reset --hard`, `git clean -f`, `git checkout .`, or `git restore .`
- **NEVER** delete branches
- If anything goes wrong, abort the rebase and tell the user rather than attempting destructive recovery