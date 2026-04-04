"""Docker-specific constants for IgnoreScope.

Extracted subset of IgnoreScope path_constants.py containing only
constants needed for Docker container management.
"""

# =============================================================================
# CONTAINER PATHS
# =============================================================================

# Default workspace path inside container
CONTAINER_WORKSPACE = "/workspace"

# Claude auth volume mount point
CONTAINER_CLAUDE_AUTH = "/root/.claude"


# =============================================================================
# CONTAINER PROJECT
# =============================================================================

# Container project directories (used instead of .claude/.ignore_scope)
CONTAINER_CLAUDE_DIR = ".llm"
CONTAINER_HOOKS_DIR = ".igs"
