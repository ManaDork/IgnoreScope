"""Container extension deployment for IgnoreScope containers.

Provides extensible framework for deploying extensions into containers.
Currently supported: Claude Code CLI, Git, P4 MCP Server, Workflow Setup.
"""

from .install_extension import ExtensionInstaller, DeployMethod, DeployResult
from .claude_extension import (
    ClaudeInstaller,
    deploy_claude,
    verify_claude,
)
from .git_extension import (
    GitInstaller,
    deploy_git,
    verify_git,
)
from .p4_mcp_extension import (
    P4McpInstaller,
    deploy_p4_mcp,
    verify_p4_mcp,
)
from .workflow_setup import WorkflowSetup

__all__ = [
    "ExtensionInstaller",
    "DeployMethod",
    "DeployResult",
    "ClaudeInstaller",
    "deploy_claude",
    "verify_claude",
    "GitInstaller",
    "deploy_git",
    "verify_git",
    "P4McpInstaller",
    "deploy_p4_mcp",
    "verify_p4_mcp",
    "WorkflowSetup",
]
