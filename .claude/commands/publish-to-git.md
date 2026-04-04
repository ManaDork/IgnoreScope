# /publish-to-git — Sync to GitHub mirror, commit, push, and optionally tag a release

> Copies publishable files from P4 workspace to GitHub mirror, commits, pushes,
> and optionally bumps version + tags for CI release.

**Arguments:** `$ARGUMENTS` — optional: `minor`, `major`, `--no-bump`, or `--tag-only`
- Default (no args): patch bump + sync + commit + push + tag

## Paths

- **P4 workspace (source):** `E:\SANS\SansMachinatia\_workbench\project_ignore_scope\IgnoreScopeDocker`
- **GitHub mirror (destination):** `E:\SANS\SansMachinatia\_workbench\GitHubPublishing\IgnoreScopeDocker`
- **Remote:** `https://github.com/ManaDork/IgnoreScope.git`

## Safety Rules

- NEVER run `git push --force` or any force-push variant
- NEVER skip the confirmation prompt before push
- NEVER commit without showing the user the diff summary first
- If tests fail, warn the user and ask whether to continue — do not abort silently

## Instructions

### Step 1: Parse Arguments

Read `$ARGUMENTS`. Valid values:
- *(empty)* — **default: patch bump** + sync + commit + push + tag
- `minor` / `major` — override bump type
- `--no-bump` — sync, commit, and push only. No version bump, no tag
- `--tag-only` — skip bump and sync, tag the current version and push the tag

### Step 2: Pre-flight Checks

Run in parallel:
- Read `IgnoreScope/_version.py` and extract the current `__version__`
- Verify `scripts/sync_to_github.py` exists

Display: `Current version: {version}`

Ask the user:
> Run pytest before publishing? (Y/n)

If yes:
```powershell
python -m pytest tests/ -x -q
```
- Pass → continue
- Fail → show summary, ask: "Tests failed — continue anyway? (y/N)". If no, abort.

### Step 3: Version Bump (default unless `--no-bump` or `--tag-only`)

Skip if `--no-bump` or `--tag-only`. Default bump type is `patch`.

1. Parse current version into `(major, minor, patch)` integers
2. Compute new version per bump type
3. Update `IgnoreScope/_version.py` — replace the `__version__ = "..."` line
4. Display: `Version: 0.1.0 → 0.2.0`
5. Set `$TAG_VERSION` to the new version

If `--tag-only`, set `$TAG_VERSION` to the current version.

### Step 4: Run Sync Script

```powershell
python scripts/sync_to_github.py
```

Show the output (copied/deleted counts). If it errors, abort.

### Step 5: Git Operations in Mirror

All commands run with cwd = `E:\SANS\SansMachinatia\_workbench\GitHubPublishing\IgnoreScopeDocker`.

**5a — Init if needed** (only when `.git/` is missing):
```powershell
git init
git remote add origin https://github.com/ManaDork/IgnoreScope.git
git branch -M main
```

**5b — Stage and review:**
```powershell
git add .
git status
git diff --cached --stat
```
If nothing staged → "Nothing to publish — mirror is up to date." Skip to Step 6 if tagging, else end.

**5c — Commit:**
Ask for a commit message, or suggest: `"Update IgnoreScope to v{version}"` (or `"Update IgnoreScope"` if no bump).

**5d — Push:**
Ask: "Push to origin/main? (Y/n)"

If first push (just initialized): `git push -u origin main`
Otherwise: `git push origin main`

### Step 6: Tag and Release (default unless `--no-bump`)

Skip only if `--no-bump` was specified.

```powershell
git tag v{$TAG_VERSION}
git push origin v{$TAG_VERSION}
```

Tell the user:
> Tagged `v{$TAG_VERSION}` and pushed. Release workflow triggered.
> https://github.com/ManaDork/IgnoreScope/actions

### Step 7: Summary

Display:
- Version published (or "no version change")
- Commit hash (short)
- Tag pushed (or "no tag")
- Repo link: `https://github.com/ManaDork/IgnoreScope`

## Install Commands (for release notes)

```bash
uv tool install git+https://github.com/ManaDork/IgnoreScope
```
