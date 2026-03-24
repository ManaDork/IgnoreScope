# {project_name} — Claude Workflow

## Project
- **Root:** /{project_name}
- **Scope:** .ignore_scope/{scope_name}/
- **VCS:** P4 (team publish) + git (development scratchpad)

## P4 Connection
- **P4PORT:** {p4port}
- **P4USER:** {p4user}
- **P4CLIENT:** {p4client}

## Git Architecture
- Working tree: /{project_name}/
- Git database: .ignore_scope/{scope_name}/.git/ (--separate-git-dir)
- .gitignore blanket-ignores *, use `git add -f` for files you modify
- GIT_DIR and GIT_WORK_TREE are set in container env

## Setup
Run `/init` to complete workflow setup:
1. Verify MCP servers (P4, context-mode)
2. Install context-mode plugin (MCP tools + hooks)
3. Run `/bootstrap` (zones, planning, git conventions, commands)
4. Coordinator Hierarchy appended to this file
5. Initial git commit of all generated artifacts
