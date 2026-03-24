"""Container workflow setup orchestrator.

Composes existing installers (ClaudeInstaller, GitInstaller) with new
container-specific setup steps to deploy a complete Claude workflow
into an IgnoreScope container.

Git architecture: --separate-git-dir per-scope in .ignore_scope/{scope}/.git/
P4 coexistence: .p4ignore hides git artifacts from Perforce.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .install_extension import DeployResult, DeployMethod
from .claude_extension import ClaudeInstaller
from .git_extension import GitInstaller
from .p4_mcp_extension import P4McpInstaller

# Template directory (sibling to this module)
_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class WorkflowSetup:
    """Orchestrates full workflow deployment into an IgnoreScope container.

    Composes existing installers — does NOT subclass ExtensionInstaller.
    Each install step returns a DeployResult. run_full_setup() executes
    all steps in order, stopping on first failure.
    """

    # Canonical P4 MCP binary path inside container
    P4_MCP_DEST = P4McpInstaller.SYMLINK_PATH

    def __init__(
        self,
        host_project_root: Path,
        scope_name: str,
        p4port: str,
        p4user: str,
        p4client: str,
        git_user: str = "",
        git_email: str = "",
        github_remote_url: str = "",
        devenv_mount: str = "/devenv",
    ) -> None:
        self.host_project_root = host_project_root
        self.scope_name = scope_name
        self.p4port = p4port
        self.p4user = p4user
        self.p4client = p4client
        self.git_user = git_user
        self.git_email = git_email
        self.github_remote_url = github_remote_url
        self.devenv_mount = devenv_mount

    # =========================================================================
    # Computed paths
    # =========================================================================

    @property
    def container_name(self) -> str:
        from ..docker import build_docker_name
        return build_docker_name(self.host_project_root, self.scope_name)

    @property
    def project_dir(self) -> str:
        """/{project_name} — git working tree + UE source."""
        return f"/{self.host_project_root.name}"

    @property
    def scope_dir(self) -> str:
        """/{project_name}/.ignore_scope/{scope_name} — workflow artifacts + git data."""
        return f"{self.project_dir}/.ignore_scope/{self.scope_name}"

    @property
    def git_dir(self) -> str:
        """Actual git database location (--separate-git-dir)."""
        return f"{self.scope_dir}/.git"

    # =========================================================================
    # Template rendering
    # =========================================================================

    def _render_template(self, template_name: str) -> str:
        """Read a template file and substitute placeholders.

        Uses str.replace() instead of .format() to avoid conflicts
        with JSON braces in templates like mcp.json.
        """
        template_path = _TEMPLATE_DIR / template_name
        content = template_path.read_text(encoding="utf-8")
        replacements = {
            "{project_name}": self.host_project_root.name,
            "{scope_name}": self.scope_name,
            "{scope_dir}": self.scope_dir,
            "{p4port}": self.p4port,
            "{p4user}": self.p4user,
            "{p4client}": self.p4client,
            "{p4_mcp_dest}": self.P4_MCP_DEST,
        }
        for token, value in replacements.items():
            content = content.replace(token, value)
        return content

    def _push_rendered_template(
        self,
        template_name: str,
        container_dest: str,
        target_filename: str | None = None,
    ) -> DeployResult:
        """Render a template and push it to the container.

        Args:
            template_name: Filename in templates/ directory.
            container_dest: Full container path for the output file.
            target_filename: Override filename for the temp file (cosmetic).

        Returns:
            DeployResult with success/failure.
        """
        from ..docker import push_file_to_container

        content = self._render_template(template_name)
        suffix = Path(target_filename or template_name).suffix or ".txt"

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=suffix,
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            success, msg = push_file_to_container(
                self.container_name, tmp_path, container_dest
            )
            if success:
                return DeployResult(
                    success=True,
                    message=f"Wrote {container_dest}",
                )
            return DeployResult(success=False, message=f"Push failed: {msg}")
        finally:
            tmp_path.unlink(missing_ok=True)

    # =========================================================================
    # Install steps (each returns DeployResult)
    # =========================================================================

    def install_system_deps(self) -> DeployResult:
        """Step 1: apt-get install curl, ca-certificates, nodejs, npm."""
        from ..docker import exec_in_container

        cmd = [
            'bash', '-c',
            'apt-get update && apt-get install -y --no-install-recommends '
            'curl ca-certificates nodejs npm '
            '&& rm -rf /var/lib/apt/lists/*',
        ]
        success, stdout, stderr = exec_in_container(
            self.container_name, cmd, timeout=120
        )
        if success:
            return DeployResult(success=True, message="System deps installed")
        return DeployResult(
            success=False,
            message=f"System deps failed: {stderr or stdout}",
        )

    def install_git(self) -> DeployResult:
        """Step 2: Install git via GitInstaller."""
        installer = GitInstaller()
        return installer.deploy(self.container_name)

    def install_p4_cli(self) -> DeployResult:
        """Step 3: Add Perforce apt repo and install helix-cli."""
        from ..docker import exec_in_container

        # Perforce provides an apt repo for Ubuntu/Debian.
        # gnupg is needed for apt-key; wget for key fetch.
        cmd = [
            'bash', '-c',
            'apt-get update '
            '&& apt-get install -y --no-install-recommends gnupg wget '
            '&& wget -qO - https://package.perforce.com/perforce.pubkey '
            '| gpg --dearmor -o /usr/share/keyrings/perforce-archive-keyring.gpg '
            '&& echo "deb [signed-by=/usr/share/keyrings/perforce-archive-keyring.gpg] '
            'https://package.perforce.com/apt/ubuntu focal release" '
            '> /etc/apt/sources.list.d/perforce.list '
            '&& apt-get update '
            '&& apt-get install -y --no-install-recommends helix-cli '
            '&& rm -rf /var/lib/apt/lists/*',
        ]
        success, stdout, stderr = exec_in_container(
            self.container_name, cmd, timeout=180
        )
        if success:
            return DeployResult(success=True, message="Perforce helix-cli installed")
        return DeployResult(
            success=False,
            message=f"P4 CLI install failed: {stderr or stdout}",
        )

    def stage_p4_mcp_binary(self) -> DeployResult:
        """Step 4: Copy P4 MCP server directory from /devenv mount, symlink into PATH.

        Delegates to P4McpInstaller which handles devenv check, copy, chmod,
        symlink, and verification.
        """
        installer = P4McpInstaller(devenv_mount=self.devenv_mount)
        return installer.deploy(self.container_name)

    def install_claude(self) -> DeployResult:
        """Step 5: Install Claude Code CLI via ClaudeInstaller."""
        installer = ClaudeInstaller()
        return installer.deploy_runtime(
            self.container_name, method=DeployMethod.MINIMAL, timeout=300
        )

    def install_bootstrap(self) -> DeployResult:
        """Step 6: Install agentic-bootstrap via npx."""
        from ..docker import exec_in_container

        cmd = [
            'bash', '-c',
            'npx --yes @studiomopoke/agentic-bootstrap install',
        ]
        success, stdout, stderr = exec_in_container(
            self.container_name, cmd, timeout=120
        )
        if success:
            return DeployResult(success=True, message="Bootstrap installed")
        return DeployResult(
            success=False,
            message=f"Bootstrap install failed: {stderr or stdout}",
        )

    def install_context_mode(self) -> DeployResult:
        """Step 7: Install context-mode plugin (MCP tools + hooks).

        Primary: `claude plugin add mksglu/context-mode`
        Fallback: manual MCP add + hook copy.
        """
        from ..docker import exec_in_container

        claude_bin = ClaudeInstaller.BINARY_PATH

        # Primary: plugin install (gets both MCP tools AND hooks)
        cmd = ['bash', '-c', f'{claude_bin} plugin add mksglu/context-mode']
        success, stdout, stderr = exec_in_container(
            self.container_name, cmd, timeout=120
        )
        if success:
            return DeployResult(
                success=True,
                message="context-mode plugin installed (MCP tools + hooks)",
            )

        # Fallback: MCP-only install (hooks won't auto-install)
        fallback_cmd = [
            'bash', '-c',
            f'{claude_bin} mcp add context-mode -- npx -y context-mode',
        ]
        fb_success, fb_stdout, fb_stderr = exec_in_container(
            self.container_name, fallback_cmd, timeout=60
        )
        if fb_success:
            return DeployResult(
                success=True,
                message="context-mode MCP added (fallback — hooks NOT installed, "
                        "copy .mjs hooks manually if needed)",
                details={"fallback": True},
            )

        return DeployResult(
            success=False,
            message=f"context-mode install failed: {stderr or stdout}; "
                    f"fallback also failed: {fb_stderr or fb_stdout}",
        )

    def write_workspace_files(self) -> DeployResult:
        """Step 8: Write seed files into scope dir + project root.

        Delegates per-tool config files to extension deploy_config() methods:
        - .gitignore → GitInstaller.deploy_config()
        - .p4config, .p4ignore → P4McpInstaller.deploy_config()
        Composite workflow templates (CLAUDE.md, .mcp.json) stay here.
        """
        from ..docker import ensure_container_directories, file_exists_in_container

        # Create directories first
        dirs = [
            self.scope_dir,
            f"{self.scope_dir}/.claude/commands",
            f"{self.scope_dir}/planning",
        ]
        dir_ok, dir_msg = ensure_container_directories(
            self.container_name, dirs
        )
        if not dir_ok:
            return DeployResult(
                success=False, message=f"Directory creation failed: {dir_msg}"
            )

        results: list[str] = []

        # --- Composite workflow templates (owned by WorkflowSetup) ---
        composite_files = [
            ("seed_claude_md.md", f"{self.scope_dir}/CLAUDE.md", "CLAUDE.md"),
            ("mcp.json", f"{self.scope_dir}/.mcp.json", ".mcp.json"),
        ]
        for tpl_name, dest, display in composite_files:
            result = self._push_rendered_template(tpl_name, dest, display)
            if not result.success:
                return DeployResult(
                    success=False,
                    message=f"Failed writing {display}: {result.message}",
                    details={"written": results},
                )
            results.append(display)

        # --- Per-tool configs delegated to extension deploy_config() ---
        context = {
            "scope_name": self.scope_name,
            "p4port": self.p4port,
            "p4user": self.p4user,
            "p4client": self.p4client,
        }

        # Check for existing .p4ignore (will be overwritten)
        p4ignore_existed = file_exists_in_container(
            self.container_name, f"{self.project_dir}/.p4ignore"
        )

        # P4 configs first — .p4ignore before .gitignore so P4 ignores
        # git artifacts before they appear on the host bind mount.
        p4_installer = P4McpInstaller(devenv_mount=self.devenv_mount)
        p4_results = p4_installer.deploy_config(
            self.container_name, context, self.project_dir, self.scope_dir,
        )
        for r in p4_results:
            if not r.success:
                return DeployResult(
                    success=False,
                    message=f"Failed writing P4 config: {r.message}",
                    details={"written": results},
                )
            display = ".p4config" if ".p4config" in r.message else ".p4ignore"
            note = " (overwritten)" if display == ".p4ignore" and p4ignore_existed else ""
            results.append(f"{display}{note}")

        # Git config
        git_installer = GitInstaller()
        git_results = git_installer.deploy_config(
            self.container_name, context, self.project_dir, self.scope_dir,
        )
        for r in git_results:
            if not r.success:
                return DeployResult(
                    success=False,
                    message=f"Failed writing Git config: {r.message}",
                    details={"written": results},
                )
            results.append(".gitignore")

        return DeployResult(
            success=True,
            message=f"Wrote {len(results)} workspace files",
            details={"written": results},
        )

    def setup_git(self) -> DeployResult:
        """Step 9: Initialize git with --separate-git-dir + configure identity.

        Git working tree = project root.
        Git database = .ignore_scope/{scope}/.git/ (per-scope isolation).
        Sets GIT_DIR and GIT_WORK_TREE via /etc/profile.d/ and /etc/environment.
        """
        from ..docker import exec_in_container

        # Init with --separate-git-dir so git DB lives in scope dir
        # This creates:
        #   /{Project}/.git  (file pointing to .ignore_scope/{scope}/.git)
        #   .ignore_scope/{scope}/.git/  (actual database)
        init_cmd = [
            'bash', '-c',
            f'cd "{self.project_dir}" '
            f'&& git init --separate-git-dir "{self.git_dir}"',
        ]
        success, stdout, stderr = exec_in_container(
            self.container_name, init_cmd, timeout=30
        )
        if not success:
            return DeployResult(
                success=False,
                message=f"git init failed: {stderr or stdout}",
            )

        # Set GIT_DIR + GIT_WORK_TREE via /etc/profile.d/ (login/interactive shells)
        # and /etc/environment (PAM-aware sessions).
        # The --separate-git-dir .git pointer file at project root is the primary
        # git discovery mechanism for non-login 'docker exec bash -c' sessions.
        env_cmd = [
            'bash', '-c',
            f'echo \'export GIT_DIR="{self.git_dir}"\' > /etc/profile.d/git-env.sh '
            f'&& echo \'export GIT_WORK_TREE="{self.project_dir}"\' >> /etc/profile.d/git-env.sh '
            f'&& chmod +x /etc/profile.d/git-env.sh '
            f'&& echo \'GIT_DIR="{self.git_dir}"\' >> /etc/environment '
            f'&& echo \'GIT_WORK_TREE="{self.project_dir}"\' >> /etc/environment',
        ]
        success, _, stderr = exec_in_container(
            self.container_name, env_cmd, timeout=10
        )
        if not success:
            return DeployResult(
                success=False,
                message=f"Failed setting git env vars: {stderr}",
            )

        # Configure identity
        if not self.git_user or not self.git_email:
            return DeployResult(
                success=False,
                message="Git user name and email are required for setup_git()",
            )
        installer = GitInstaller()
        id_ok, id_msg = installer.configure_identity(
            self.container_name, self.git_user, self.git_email
        )
        if not id_ok:
            return DeployResult(success=False, message=id_msg)

        # Add remote if provided
        if self.github_remote_url:
            remote_cmd = [
                'bash', '-c',
                f'export GIT_DIR="{self.git_dir}" '
                f'&& export GIT_WORK_TREE="{self.project_dir}" '
                f'&& git remote add origin "{self.github_remote_url}"',
            ]
            success, _, stderr = exec_in_container(
                self.container_name, remote_cmd, timeout=15
            )
            if not success:
                # Non-fatal: remote may already exist
                if "already exists" not in (stderr or ""):
                    return DeployResult(
                        success=False,
                        message=f"Failed adding remote: {stderr}",
                    )

        details = {"git_dir": self.git_dir, "work_tree": self.project_dir}
        if self.github_remote_url:
            details["remote"] = self.github_remote_url

        return DeployResult(
            success=True,
            message=f"Git initialized (separate-git-dir at {self.git_dir})",
            details=details,
        )

    # =========================================================================
    # Orchestrator
    # =========================================================================

    def run_full_setup(self) -> list[tuple[str, DeployResult]]:
        """Execute all steps in order. Stops on first failure.

        Returns:
            List of (step_name, DeployResult) tuples for all executed steps.
            Last entry is the failing step if any failed.
        """
        from ..docker import ensure_container_running

        # Pre-check: container must be running
        running, msg = ensure_container_running(self.container_name)
        if not running:
            return [("pre-check", DeployResult(
                success=False,
                message=f"Container '{self.container_name}' not available: {msg}",
            ))]

        steps: list[tuple[str, callable]] = [
            ("install_system_deps", self.install_system_deps),
            ("install_git", self.install_git),
            ("install_p4_cli", self.install_p4_cli),
            ("stage_p4_mcp_binary", self.stage_p4_mcp_binary),
            ("install_claude", self.install_claude),
            ("install_bootstrap", self.install_bootstrap),
            ("install_context_mode", self.install_context_mode),
            ("write_workspace_files", self.write_workspace_files),
            ("setup_git", self.setup_git),
        ]

        results: list[tuple[str, DeployResult]] = []
        for name, step_fn in steps:
            print(f"  [{name}] ...", end=" ", flush=True)
            result = step_fn()
            status = "OK" if result.success else "FAILED"
            print(status)
            results.append((name, result))
            if not result.success:
                break

        # Track workspace files in config so the system knows they exist
        if all(r.success for _, r in results):
            self._update_config_pushed_files()

        return results

    def _update_config_pushed_files(self) -> None:
        """Record workspace files written by setup in ScopeDockerConfig.

        Adds the workspace file paths to pushed_files so the system can
        track them for re-push on container recreate.
        """
        from ..core.config import load_config, save_config

        try:
            config = load_config(self.host_project_root, self.scope_name)
            workspace_paths = [
                self.host_project_root / ".ignore_scope" / self.scope_name / "CLAUDE.md",
                self.host_project_root / ".ignore_scope" / self.scope_name / ".mcp.json",
                self.host_project_root / ".ignore_scope" / self.scope_name / ".p4config",
                self.host_project_root / ".p4ignore",
                self.host_project_root / ".gitignore",
            ]
            config.pushed_files.update(workspace_paths)
            save_config(config)
        except Exception:
            # Non-fatal — config update is best-effort
            pass
