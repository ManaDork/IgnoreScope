# Scope — Documentation & Project Code Review

## Phases

### Phase 1: Code Comments Audit
Trace code stacks per zone. Collect comments. Compare to behavior.
Deliverable: `planning/reviews/code-review-comments.md`

### Phase 2: Architecture Blueprints Audit
Compare each blueprint to current code.
Deliverable: `planning/reviews/code-review-blueprints.md`

### Phase 3: CLAUDE.md Audit
Check project CLAUDE.md accuracy.
Deliverable: `planning/reviews/code-review-claude-md.md`

## Execution

Each phase spawns exploration agents per zone in parallel. Agents trace stacks, collect comments, report findings. Findings consolidated into report.

**Phase 1 agent assignments:**
- Agent 1: Core (node_state, mount_spec_path, local_mount_config, hierarchy, config)
- Agent 2: GUI (display_config, style_engine, delegates, mount_data_tree, local_host_view, scope_view)
- Agent 3: Docker + CLI + Extensions (compose, container_lifecycle, commands, extensions)

**Phase 2:** Read each blueprint, compare against code found in Phase 1.

**Phase 3:** Read CLAUDE.md, cross-reference against Phase 1+2 findings.

## Task Breakdown

| # | Task | Phase | Complexity |
|---|------|-------|------------|
| 1 | Trace Core zone stacks + collect comments | 1 | Medium |
| 2 | Trace GUI zone stacks + collect comments | 1 | Medium |
| 3 | Trace Docker/CLI/Extensions stacks + collect comments | 1 | Medium |
| 4 | Consolidate Phase 1 findings into report | 1 | Low |
| 5 | Audit ARCHITECTUREGLOSSARY + COREFLOWCHART | 2 | Medium |
| 6 | Audit DATAFLOWCHART + MIRRORED_ALGORITHM | 2 | Medium |
| 7 | Audit GUI_STATE_STYLES + GUI_LAYOUT_SPECS + GUI_STRUCTURE | 2 | Medium |
| 8 | Consolidate Phase 2 findings into report | 2 | Low |
| 9 | Audit CLAUDE.md | 3 | Low |
| 10 | Final consolidated report | 3 | Low |
