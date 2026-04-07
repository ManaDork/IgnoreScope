# Scope — Style Polish Round 2

## Phases (execution order — reordered from spec)

### Batch A: NodeState Changes

Add `is_mount_root` to NodeState, `virtual_type` to MountDataNode. Must come first — truth tables depend on these fields.

### Batch B: Color System + State Split

Rename JSON variables to categorical system. Split MASKED from MOUNTED_MASKED. Split VIRTUAL into three subtypes. Rewrite truth tables using new NodeState fields.

### Batch C: Inherited + Ancestor Colors

Add inherited.* and ancestor.* color variables. Compute dimmer/less-saturated variants. Wire into gradient assignments.

### Batch D: Architecture Doc Updates

Update ARCHITECTUREGLOSSARY, GUI_STATE_STYLES, COREFLOWCHART.

## Deferred

- Pushed file special treatment
- File font color differentiation (TBD)
- File P3 sync state
- Container Scope panel separate overrides (ensure capability only)
- FILE_HOST_ORPHAN implementation

## Task Breakdown

| # | Task | Depends On | Complexity |
|---|------|-----------|------------|
| 1 | Rename tree_state_style.json variables to categorical system | — | Low |
| 2 | Update tree_state_font.json with new text entries | — | Low |
| 3 | Update display_config.py _FOLDER_STATE_DEFS with new variable names | 1, 2 | Medium |
| 4 | Update display_config.py _FILE_STATE_DEFS with new variable names | 1, 2 | Low |
| 5 | Update FOLDER_STATE_TABLE — add FOLDER_MASKED, split VIRTUAL types | 3 | Medium |
| 6 | Add inherited.* and ancestor.* color values to JSON | 1 | Low |
| 7 | Wire inherited/ancestor colors into gradient assignments | 3, 6 | Medium |
| 8 | Add `is_mount_root` to NodeState + compute_node_state() | — | Medium |
| 9 | Add `virtual_type` to MountDataNode for volume/auth/mirrored distinction | — | Medium |
| 10 | Update truth table to use is_mount_root for MOUNTED_MASKED | 5, 8 | Medium |
| 11 | Update truth table to use virtual_type for VIRTUAL subtypes | 5, 9 | Medium |
| 12 | Verify style_engine.py resolves dotted variable names | 1 | Low |
| 13 | Update ARCHITECTUREGLOSSARY.md | 5, 10, 11 | Low |
| 14 | Update GUI_STATE_STYLES.md | 3, 4, 7 | Low |
| 15 | Update COREFLOWCHART.md | 8, 11 | Low |

### Batch Grouping (execution order)

**Batch A:** Tasks 8-9 (NodeState first)
**Batch B:** Tasks 1-5, 10-12 (Colors + state split, uses new NodeState fields)
**Batch C:** Tasks 6-7 (Inherited/ancestor)
**Batch D:** Tasks 13-15 (Docs)
