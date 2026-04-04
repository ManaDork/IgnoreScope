# Feature: Workspace Isolation Volumes

## Problem Statement

Runtime-installed extensions (Claude CLI, Git, P4 MCP) are lost on container Update and Recreate because they install to the container's writable layer via `docker exec`, not into persistent named volumes. The extension refactor unified all three under `ExtensionInstaller.deploy_runtime()`, but this common code path writes to ephemeral storage. There is no mechanism to track what was installed, detect when it's missing, or re-apply it.

Additionally, when a project is fully mirrored (bind-mounted), host and container content can collide at the same paths — e.g., host `.git/` (P4-managed) vs container `.git/` (git-managed). These paths need **isolation** — container-owned volumes that overlay bind mounts with divergent content.

## Domain

**Isolation** = Asymmetric Behavior Environments — same path, different content/purpose between host and container.

Contrast with **Siblings** = Asymmetric Mapped Environments — different source path mapped to different target.

## Success Criteria

- Extensions persist through Update Container (named volumes survive `docker compose down`)
- Extensions auto-re-deploy on Recreate Container (config tracks desired state)
- Each extension is tracked as a `LocalMountConfig` in `scope_docker_desktop.json`
- Live View scan detects discrepancies between config state and container reality
- Discrepancies trigger reconciliation (deploy/no-op/remove)
- New [Isolate] column in Local Host Configuration tree for manual isolation paths
- Isolation volumes are Layer 4 (final overlay, nothing punches through)

## User Stories

- As a user, I want my Git installation to survive when I Update Container to add a new mount
- As a user, I want Claude CLI to auto-reinstall after Recreate Container without manual intervention
- As a user, I want to isolate `.git/` so my container's git repo is separate from the host's P4 workspace
- As a user, I want to see in the GUI which extensions are installed, pending, or need re-deployment

## Acceptance Criteria

- [ ] `LocalMountConfig` gains `state` field: `deploy`, `installed`, `remove`
- [ ] Each extension tracked as `LocalMountConfig` entry in config JSON
- [ ] Extension install paths declared as isolation volumes in compose generation
- [ ] Isolation volumes are Layer 4 (after bind mounts, masks, and reveals)
- [ ] Live View scan detects installed/missing binaries per extension config
- [ ] Reconciliation: `deploy` + missing → run install; `installed` + missing → re-deploy
- [ ] Update Container preserves extension volumes (existing behavior, now utilized)
- [ ] Recreate Container triggers re-deployment via reconciliation
- [ ] [Isolate] column in Local Host tree for user-controlled isolation paths
- [ ] Config persists seed method per isolation path (clone from host / start empty)

## Out of Scope

- Real-time file watching (scan is on-demand or lifecycle-triggered)
- Extension marketplace / plugin registry
- Custom Dockerfile modification (extensions install at runtime, not build time)
- Remove/uninstall UX (last phase — state='remove' tracked but UI deferred)

## Open Questions

- Should reconciliation run automatically on container start, or require user trigger?
- How does [Isolate] interact with [Mask] on the same path? (Mask hides, Isolate overrides — are they mutually exclusive?)
- Volume naming convention for isolation volumes: `iso_{ext_name}` or `iso_{sanitized_path}`?
- Should extension `LocalMountConfig` entries be visible in the Local Host tree or a separate panel?
