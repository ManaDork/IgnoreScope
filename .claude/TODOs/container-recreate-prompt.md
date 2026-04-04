# TODO: GUI Container Recreate Prompt

## Feature
When any action requires a container recreate (e.g., volume config change, image rebuild), the GUI should prompt the user and warn that runtime-deployed extensions will be lost.

## Context
Runtime installs via `docker exec` are ephemeral — they live in the container filesystem layer, not in volumes or the image. Container recreation destroys them.

- **Git** — installed via `apt-get`/`apk` inside the running container
- **P4 MCP Server** — copied from `/devenv` mount into `/usr/local/lib/`
- **Claude Code CLI** — installed via `curl` installer script

All three are lost on container recreate. Users reported "successful" deploys that disappeared — the deploy did succeed, but the container was subsequently recreated.

## Scope
1. **Track deployed extensions** — Store which extensions have been deployed to a container in `ScopeDockerConfig` (e.g., `deployed_extensions: set[str]`).
2. **Warn on recreate** — When the GUI triggers a container recreate, check `deployed_extensions`. If non-empty, show a warning dialog listing what will be lost.
3. **Offer re-deploy** — After recreate completes, offer to re-deploy the previously installed extensions automatically.

## Implementation Notes
- `ScopeDockerConfig` already tracks `pushed_files` — similar pattern for extensions.
- The `deploy()` methods on each installer already return `DeployResult` — on success, update config.
- GUI recreate paths: `execute_update()` in `container_lifecycle.py`, compose rebuild in GUI actions.

## Status (2026-03-25)
**Partially addressed by Phase 3 Lifecycle Reconciliation:**
- ✅ Track deployed extensions — `config.extensions` with `ExtensionConfig` entries
- ✅ Offer re-deploy — `reconcile_extensions()` auto-re-deploys after recreate (state='installed' + missing → re-deploy)
- ⬜ Warn on recreate — GUI warning dialog before recreate not yet implemented (Phase 4/5 scope)
