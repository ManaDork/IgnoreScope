# Feature: Deploy P4 MCP Server (Linux) to Container

## Problem Statement

P4 MCP Server deployment to IgnoreScope containers currently requires a `/devenv` volume mount — workflow-specific infrastructure that ties the installer to a particular host setup. Users without this mount cannot install P4 MCP through IgnoreScope. This creates a boundary violation: a bundled extension depends on external workflow infrastructure to function.

## Success Criteria

- P4 MCP Server can be deployed to any IgnoreScope container without requiring a `/devenv` volume mount
- Deployment is driven by LLM-readable markdown instructions, not hardcoded Python scripts
- Claude Code can follow the instructions end-to-end using IgnoreScope's CLI
- Binary is transferred via IgnoreScope's push command (directory support required)

## User Stories

- As a user with an IgnoreScope container, I want to deploy P4 MCP Server without configuring a devenv volume mount, so that I can use Perforce MCP tools inside my container independently
- As Claude Code running on the host, I want clear markdown instructions for deploying P4 MCP, so that I can automate the process by following documented steps
- As Claude Code running inside a container, I want setup instructions co-located with the binary, so that I can complete installation after file transfer

## Acceptance Criteria

- [ ] `P4_MCP_LINUX_BUILD.md` exists at `{devenv}/mcp/p4-mcp-server/linux/` with build instructions
- [ ] `P4_MCP_LINUX_DEPLOY.md` exists at `{devenv}/mcp/p4-mcp-server/linux/` with host-side deploy workflow
- [ ] `P4_MCP_LINUX_SETUP.md` exists at `{devenv}/mcp/p4-mcp-server/linux/` with container-side setup steps
- [ ] IgnoreScope push supports directory transfer (prerequisite)
- [ ] DEPLOY.md uses IgnoreScope CLI to list containers and push files
- [ ] SETUP.md is pushed into the container alongside the binary
- [ ] Each document is self-contained and actionable by Claude Code

## Out of Scope

- `.p4config` / `.p4ignore` config deployment (deferred — COPY_PASTE.md feature)
- GUI "Install P4 MCP" menu item (blocked until independent install works)
- `-linux` binary suffix naming decision (address when SETUP.md is finalized)
- Automating the build phase (BUILD.md is reference documentation, not automated)

## Open Questions

- Should `P4_MCP_LINUX_DEPLOY.md` reference IgnoreScope by absolute install path or expect it on PATH?
- Container destination path: keep `/usr/local/lib/p4-mcp-server` or make configurable?
