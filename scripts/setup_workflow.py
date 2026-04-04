"""Set up a Claude workflow inside an IgnoreScope container.

Interactive entry point that prompts for project, scope, P4, and git
configuration, then runs the full 9-step setup sequence.

Usage:
    python scripts/setup_workflow.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve paths relative to this script's location
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# Add project root to sys.path so IgnoreScope package is importable
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from IgnoreScope.container_ext.workflow_setup import WorkflowSetup


def prompt(label: str, required: bool = True, default: str = "") -> str:
    """Prompt user for input with optional default."""
    suffix = f" [{default}]" if default else ""
    suffix += ": " if required else " (optional): "
    while True:
        value = input(f"  {label}{suffix}").strip()
        if not value and default:
            return default
        if not value and required:
            print(f"    {label} is required.")
            continue
        return value


def main() -> None:
    print("=" * 60)
    print("  Claude Workflow Setup — IgnoreScope Container")
    print("=" * 60)
    print()

    # --- Project + Scope ---
    print("Project Configuration:")
    raw_root = prompt("Host project root (e.g. S:\\MyGame)")
    host_project_root = Path(raw_root)
    if not host_project_root.is_dir():
        print(f"\n  ERROR: Directory not found: {host_project_root}")
        raise SystemExit(1)

    scope_name = prompt("Scope name", default="default")

    # --- P4 Connection ---
    print("\nPerforce Configuration:")
    p4port = prompt("P4PORT (e.g. ssl:perforce.example.com:1666)")
    p4user = prompt("P4USER")
    p4client = prompt("P4CLIENT (workspace name)")

    # --- Git Identity ---
    print("\nGit Identity (for container commits):")
    git_user = prompt("Git user name")
    git_email = prompt("Git email")

    # --- Optional GitHub ---
    print("\nGitHub Remote (optional — skip for local-only git):")
    github_url = prompt("GitHub remote URL", required=False)

    # --- Confirm ---
    print("\n" + "-" * 60)
    print(f"  Project:    {host_project_root}")
    print(f"  Scope:      {scope_name}")
    print(f"  P4PORT:     {p4port}")
    print(f"  P4USER:     {p4user}")
    print(f"  P4CLIENT:   {p4client}")
    print(f"  Git user:   {git_user} <{git_email}>")
    if github_url:
        print(f"  GitHub:     {github_url}")
    print("-" * 60)

    confirm = input("\n  Proceed? [Y/n]: ").strip().lower()
    if confirm and confirm != "y":
        print("  Aborted.")
        raise SystemExit(0)

    # --- Run setup ---
    setup = WorkflowSetup(
        host_project_root=host_project_root,
        scope_name=scope_name,
        p4port=p4port,
        p4user=p4user,
        p4client=p4client,
        git_user=git_user,
        git_email=git_email,
        github_remote_url=github_url,
    )

    print(f"\n  Container: {setup.container_name}")
    print(f"  Project dir: {setup.project_dir}")
    print(f"  Scope dir: {setup.scope_dir}")
    print()

    results = setup.run_full_setup()

    # --- Summary ---
    print("\n" + "=" * 60)
    all_ok = all(r.success for _, r in results)
    if all_ok:
        print("  All steps completed successfully!")
        print()
        print("  Next steps:")
        print(f"    1. Start container: docker start {setup.container_name}")
        print(f"    2. Launch Claude:   docker exec -it -w {setup.scope_dir} "
              f"{setup.container_name} /root/.local/bin/claude")
        print(f"    3. Inside Claude:   /init")
    else:
        failed_name, failed_result = results[-1]
        print(f"  Setup stopped at step: {failed_name}")
        print(f"  Error: {failed_result.message}")
        print()
        print("  Completed steps:")
        for name, result in results[:-1]:
            print(f"    {name}: {result.message}")

    print("=" * 60)


if __name__ == "__main__":
    main()
