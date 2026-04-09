"""Container extension deployment for IgnoreScope containers.

Provides extensible framework for deploying extensions into containers.
Currently supported: Claude Code CLI, Git, P4 MCP Server, Workflow Setup.
"""

from .install_extension import ExtensionInstaller, DeployMethod, DeployResult
from .claude_extension import ClaudeInstaller
from .git_extension import GitInstaller
from .p4_mcp_extension import (
    P4McpInstaller,
    deploy_p4_mcp,
    verify_p4_mcp,
)
from .workflow_setup import WorkflowSetup

# Registry: installer_class string → constructor
_INSTALLER_REGISTRY: dict[str, type[ExtensionInstaller]] = {
    "ClaudeInstaller": ClaudeInstaller,
    "GitInstaller": GitInstaller,
    "P4McpInstaller": P4McpInstaller,
}


def get_installer(installer_class: str) -> ExtensionInstaller | None:
    """Resolve installer_class name to a default-constructed instance.

    Used by reconciliation to verify/re-deploy extensions from config.

    Args:
        installer_class: Class name string (e.g., "ClaudeInstaller")

    Returns:
        ExtensionInstaller instance, or None if unknown class name.
    """
    cls = _INSTALLER_REGISTRY.get(installer_class)
    if cls is None:
        return None
    return cls()


__all__ = [
    "ExtensionInstaller",
    "DeployMethod",
    "DeployResult",
    "ClaudeInstaller",
    "GitInstaller",
    "P4McpInstaller",
    "deploy_p4_mcp",
    "verify_p4_mcp",
    "WorkflowSetup",
    "get_installer",
]
