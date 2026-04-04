# Scope: Deploy P4 MCP Server (Linux) to Container

## Phases

### Phase 0: Prerequisite — Directory Push Support
Extend IgnoreScope's `push_file_to_container()` to accept directories.
- [x] Relax `is_file()` guard in `container_ops.py:585`
- [x] Handle directory path resolution for `docker cp`
- [ ] Test directory push works end-to-end
- **Estimated complexity:** S

### Phase 1: Instruction Documents
Create the three LLM-readable markdown files.
- [x] `P4_MCP_LINUX_BUILD.md` — Build reference (adapt from BUILD_LINUX_MCP.md)
- [x] `P4_MCP_LINUX_DEPLOY.md` — Host-side deploy + config workflows
- [x] `P4_MCP_LINUX_SETUP.md` — Container-side chmod/symlink/verify
- **Estimated complexity:** M

### Phase 2: GUI Integration (Future)
Add "Install P4 MCP" to Container Extensions menu.
- [ ] Blocked until Phase 0 + Phase 1 validated
- [ ] May require additional IgnoreScope CLI commands (list containers)
- **Estimated complexity:** M

## Task Breakdown

| # | Task | Depends On | Complexity | Phase |
|---|------|-----------|------------|-------|
| 1 | Extend `push_file_to_container()` for directories | — | S | 0 |
| 2 | Write `P4_MCP_LINUX_BUILD.md` | — | S | 1 |
| 3 | Write `P4_MCP_LINUX_DEPLOY.md` | Task 1 | M | 1 |
| 4 | Write `P4_MCP_LINUX_SETUP.md` | — | S | 1 |
| 5 | End-to-end validation: deploy to test container | Tasks 1-4 | M | 1 |
| 6 | GUI menu item (future) | Task 5 | M | 2 |

## Testing Strategy

- **Unit:** Test directory push in `container_ops.py` with mock `docker cp`
- **Integration:** Push the `linux/` directory to a running container, verify files arrive
- **Manual:** Follow DEPLOY.md → SETUP.md end-to-end, confirm `p4-mcp-server-linux --version` succeeds

## Deferred Items

| Item | Blocked By | Notes |
|------|-----------|-------|
| .p4config/.p4ignore config deployment | COPY_PASTE.md feature | Better handled via GUI configuration |
| `-linux` suffix naming | SETUP.md finalization | Cosmetic decision |
| ~~Container list CLI command~~ | ~~Separate feature~~ | DONE — `list` command added to CLI |
