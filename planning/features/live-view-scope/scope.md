# Scope: Live View Mode — Scope Configuration

## Phases

### Phase 0: Prerequisites (done)
- [x] `container_only` field on NodeState
- [x] `FILE_CONTAINER_ONLY` / `FOLDER_CONTAINER_ONLY` style states
- [x] `"container_only"` color variable in tree_state_style.json
- [x] Glossary terms: copied, container_only

### Phase 1: Scan + Diff
Wire the existing infrastructure to populate container-only content.
- [ ] Add "Scan for New Files" to header context menu (enabled when running)
- [ ] Remove disabled placeholder from `_build_folder_menu()`
- [ ] Add `scanContainerRequested` signal, wire to `scan_container_directory()`
- [ ] Diff engine: container paths vs host paths → container-only set
- [ ] Populate `_container_files` from diff results
- **Estimated complexity:** M

### Phase 2: Virtual Node Rendering
Display container-only content in the Scope tree.
- [ ] Create virtual TreeNodes for container-only files/folders
- [ ] Integrate into tree model (canFetchMore, fetchMore)
- [ ] CONTAINER-ONLY gradient renders correctly
- [ ] Display filter proxy respects `display_virtual_nodes` setting
- **Estimated complexity:** L

### Phase 3: Interactions
Add operations on container-only files.
- [ ] RMB context menu for container-only files (Copy Path, Remove)
- [ ] Remove container-only file via `docker exec rm`
- [ ] Pull container-only file to host
- **Estimated complexity:** M

## Task Breakdown

| # | Task | Depends On | Complexity | Phase |
|---|------|-----------|------------|-------|
| 1 | Add "Scan for New Files" to header context menu + remove folder placeholder | — | S | 1 |
| 2 | Wire scanContainerRequested signal → scan_container_directory() | Task 1 | S | 1 |
| 3 | Build diff engine (container paths - host paths) | Task 2 | M | 1 |
| 4 | Populate _container_files from diff | Task 3 | S | 1 |
| 5 | Create virtual TreeNodes from container_files | Task 4 | M | 2 |
| 6 | Integrate virtual nodes into tree model | Task 5 | L | 2 |
| 7 | Verify CONTAINER-ONLY gradient renders | Task 6 | S | 2 |
| 8 | RMB context menu for container-only nodes | Task 7 | M | 3 |
| 9 | Remove/Pull operations for container-only | Task 8 | M | 3 |

## Testing Strategy

- **Unit:** Diff engine with mock host/container path sets
- **Unit:** Virtual node creation from container_files
- **Integration:** Scan a running container, verify diff populates correctly
- **Manual:** Visual verification of CONTAINER-ONLY gradient in Scope tree
- **Manual:** Scan → see container-only files → RMB → Copy Path

## Deferred Items

| Item | Notes |
|------|-------|
| Real-time file watching | On-demand scan is sufficient for MVP |
| Scan result persistence | Ephemeral for now; persist if users need it |
| Automatic scan on container start | Can be added after manual scan works |
| Performance optimization for large trees | Address after measuring actual scan times |
