"""LLM deployment for IgnoreScope containers.

Provides extensible framework for deploying LLMs into containers.
Currently supported: Claude Code CLI.
"""

from .deployer import LLMDeployer, DeployMethod, DeployResult
from .claude import (
    ClaudeDeployer,
    deploy_claude_native,
    deploy_claude_npm,
    verify_claude,
)

__all__ = [
    "LLMDeployer",
    "DeployMethod",
    "DeployResult",
    "ClaudeDeployer",
    "deploy_claude_native",
    "deploy_claude_npm",
    "verify_claude",
]
