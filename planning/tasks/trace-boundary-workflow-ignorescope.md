# Task: Trace Boundary — Workflow vs IgnoreScope

## Summary
Identify what belongs inside IgnoreScope (container management tool) vs. what is workflow automation (Claude+P4+Git orchestration) that should attach externally.

## Findings

### The Boundary Rule

**IgnoreScope owns**: Container creation, volume layering, visibility masking, push/pull file ops, and deploying bundled extensions (install-git, install-p4-mcp, deploy-claude).

**IgnoreScope does NOT own**: Orchestrating multi-tool workflows, writing workflow-specific config templates into containers, or sequencing a Claude+P4+Git development environment.

### WorkflowSetup Isolation Status

WorkflowSetup is **already isolated** from IgnoreScope's core:
- NOT imported by CLI, GUI, or core modules
- Only consumers: `scripts/setup_workflow.py` (standalone) + test suite
- Uses ONLY public generic APIs (docker ops, extension installers, core config)
- No private/internal access

### What's IN Scope (Keep in IgnoreScope)

| Component | Why |
|---|---|
| Extension installer ABC (`install_extension.py`) | Generic framework for any extension |
| `ClaudeInstaller`, `GitInstaller`, `P4McpInstaller` | Bundled extensions — common tools |
| CLI `install-git`, `install-p4-mcp` | User-initiated extension deployment |
| GUI "Deploy Claude", "Install Git" | Same, via GUI |
| Docker API wrappers (`exec_in_container`, etc.) | Core container ops |
| Config system (`pushed_files`, load/save) | State tracking |

### What's OUT of Scope (Should Be External)

| Component | Current Location | Why External |
|---|---|---|
| `WorkflowSetup` class | `container_ext/workflow_setup.py` | 9-step orchestrator for specific Claude+P4+Git workflow |
| Templates (5 files) | `container_ext/templates/` | Workflow-specific config (mcp.json, p4config, seed_claude_md, gitignore, p4ignore) |
| `scripts/setup_workflow.py` | `scripts/` | Interactive workflow CLI |
| `_update_config_pushed_files()` | Inside WorkflowSetup | Writes workflow's files into IgnoreScope's pushed_files config |

### The One Coupling Point

`WorkflowSetup._update_config_pushed_files()` writes 5 file paths into `ScopeDockerConfig.pushed_files` so IgnoreScope's push/pull knows about them. This is the ONLY place workflow automation mutates IgnoreScope state.

**Resolution**: When externalized, the workflow script can call `load_config()` / `save_config()` directly — these are public APIs. No special coupling needed.

### API Surface for External Consumers

IgnoreScope's stable public APIs (already used by WorkflowSetup):

```
# container_ext (extensions)
ExtensionInstaller, DeployMethod, DeployResult
ClaudeInstaller, GitInstaller, P4McpInstaller

# docker (container ops)
exec_in_container(), push_file_to_container(), pull_file_from_container()
ensure_container_running(), ensure_container_directories()
build_docker_name(), file_exists_in_container()

# core.config (state)
ScopeDockerConfig, load_config(), save_config()
```

### Decision Needed

**p4ignore and gitignore templates**: These are hybrid — they solve a real technical problem (P4+git coexistence using .ignore_scope/{scope} paths) but are hardcoded to the workflow. Options:
1. Keep in IgnoreScope as generic VCS isolation templates
2. Extract with WorkflowSetup as workflow-specific

## Acceptance Criteria
- [x] Boundary documented with clear in/out classification
- [x] ~~No code changes~~ → Scope expanded: code refactoring implemented the boundary
- [x] Decision recorded on p4ignore/gitignore template ownership → extension-owned (migrated into installer classes)
- [x] P4McpInstaller created — mirrors GitInstaller pattern
- [x] Templates migrated from files to class constants (gitignore → GitInstaller, p4config/p4ignore → P4McpInstaller)
- [x] WorkflowSetup delegates to extension deploy methods
- [x] CLI install-p4-mcp command wired
- [x] Comprehensive test coverage (807 lines new tests)

## Notes
- WorkflowSetup test suite (`test_workflow_setup.py`) would move with the class
- `container-workflow-phase0-report.md` and `container-workflow-phase2.md` in `.claude/TODOs/` describe the workflow — these are workflow docs, not IgnoreScope docs
- The Phase 2 TODO can be marked as "delivered but externalization pending"
