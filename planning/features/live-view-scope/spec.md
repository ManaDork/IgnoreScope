# Feature: Live View Mode — Scope Configuration

## Problem Statement

The Scope Configuration tree reads **only from the host filesystem**. Files and directories that exist inside the container but not on the host — copied files, container-created files, installed tools — are invisible. Users cannot see what's actually in their container without using `docker exec`.

File tracking (`pushed_files`) is file-centric and doesn't scale to directories or bulk content. A diff-based approach eliminates per-file tracking for ephemeral container content.

## Success Criteria

- Scope Configuration tree can display container-only files/folders with a distinct CONTAINER-ONLY visual state
- Container content is discovered by scanning the container filesystem and diffing against the host tree
- "Scan for New Files" action (existing disabled placeholder) triggers the scan
- Existing pushed file tracking is preserved — diff distinguishes pushed vs container-only

## User Stories

- As a user, I want to see what files exist inside my container so that I can verify deployments and inspect container state
- As a user, I want container-only files visually distinguished so that I know which files are ephemeral vs tracked
- As Claude Code inside a container, I want the host-side GUI to reflect files I've created so the user can see my work

## Acceptance Criteria

- [ ] "Scan for New Files" action in Scope Configuration header context menu (alongside Start/Stop)
- [ ] Action enabled when container is running
- [ ] Scan calls `scan_container_directory()` and returns container file list
- [ ] Diff engine identifies container-only files (exist in container, not on host)
- [ ] Container-only files appear in Scope tree as virtual nodes
- [ ] CONTAINER-ONLY gradient style renders distinctly (teal-gray, italic)
- [ ] Pushed files retain their existing visual state (not overwritten by scan)
- [ ] Scan results populate `_container_files` in MountDataTree

## Out of Scope

- Real-time file watching (scan is manual/on-demand)
- Editing container files from the GUI
- Automatic scan on container start
- Container-side file deletion from GUI (beyond existing Remove)

## Open Questions

- Should scan be recursive (full container tree) or scoped to mounted paths only?
- Performance: how to handle containers with thousands of files (e.g., node_modules)?
- Should scan results persist in config or be ephemeral (lost on GUI restart)?
