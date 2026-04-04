# Feature: System Tray Phase 2 — Container Discovery + Tray Actions

## Problem Statement

Users managing multiple IgnoreScope containers across different projects must open the full GUI, load each project, and navigate menus to perform common actions like starting/stopping containers or launching terminals. This is especially painful when the GUI is minimized to tray — the tray icon only offers Show/Hide and Exit.

Phase 2 extends the system tray to discover all IgnoreScope containers system-wide and expose per-container actions directly from the tray context menu — without requiring a project to be loaded in the GUI.

## Success Criteria

- Right-click tray shows "Containers" submenu with all IgnoreScope containers discovered via Docker label filter
- Each container shows running status indicator (● running, ○ stopped)
- Per-container submenu provides: Start/Stop (context-aware), Terminal, Copy Terminal Cmd, Claude CLI, Copy Claude Cmd
- Recent-project containers display original project name + scope (e.g., "MyGame (dev)")
- Unmatched containers display parsed Docker name + scope (e.g., "mygame (dev)")
- Container discovery runs on `aboutToShow` (hover), not on a timer
- Docker unavailable gracefully shows "(Docker not available)" disabled item
- No containers found shows "(No containers found)" disabled item

## User Stories

- As a user with multiple containers, I want to see all my IgnoreScope containers in the tray menu so I can check their status at a glance
- As a user, I want to start/stop containers from the tray without opening the full GUI window
- As a user, I want to launch a terminal or Claude CLI into any container from the tray with one click
- As a user, I want to copy terminal/Claude commands to my clipboard for use in my own terminal
- As a user, I want containers from recent projects to show friendly names, not sanitized Docker names

## Acceptance Criteria

- [ ] Tray context menu has "Containers" submenu between Show/Hide and Exit
- [ ] Containers submenu populates on hover via `aboutToShow` signal
- [ ] All containers with `maintainer=IgnoreScope` Docker label are discovered
- [ ] Running containers show ● prefix, stopped show ○ prefix
- [ ] Per-container Start action starts a stopped container
- [ ] Per-container Stop action stops a running container
- [ ] Terminal action opens system terminal with `docker exec -it {name} /bin/bash`
- [ ] Copy Terminal Cmd copies correct command to clipboard
- [ ] Claude CLI action launches Claude in terminal (error if not installed, checked at click time)
- [ ] Copy Claude Cmd copies correct command to clipboard
- [ ] Containers matched via QSettings show original project name (case-preserved)
- [ ] Unmatched containers show parsed Docker name (lowercase)
- [ ] Docker not running → "(Docker not available)" disabled item
- [ ] No containers → "(No containers found)" disabled item
- [ ] `parse_docker_name()` function added to `docker/names.py`
- [ ] `list_ignorescope_containers()` function added to `docker/container_ops.py`
- [ ] Unit tests pass for discovery algorithm, name parsing, and container listing

## Out of Scope

- Async/threaded container discovery (future Phase 3 if latency measured as unacceptable)
- Caching of discovery results or TTL-based refresh
- Tray balloon notifications for container state changes (polling)
- Container creation/removal from tray (too destructive for context menu)
- Opening a project in the GUI window from tray container click
- Extracting terminal launch to shared utility (only if third callsite appears)

## Open Questions

- None — all design decisions resolved during specification
