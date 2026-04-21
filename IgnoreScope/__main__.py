"""CLI entry point for IgnoreScope.

Usage:
    python -m IgnoreScope gui [--project PATH]
    python -m IgnoreScope create [--project PATH]
    python -m IgnoreScope list [--project PATH]
    python -m IgnoreScope status [--container NAME]
    python -m IgnoreScope push [FILES...]
    python -m IgnoreScope pull [FILES...]
    python -m IgnoreScope cp <source> [<dest>]
    python -m IgnoreScope remove [--yes]
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .cli.interactive import (
    cmd_create_wrapper,
    cmd_push_wrapper,
    cmd_pull_wrapper,
    cmd_remove_wrapper,
    cmd_install_git_wrapper,
    cmd_install_p4_mcp_wrapper,
    cmd_list_wrapper,
    cmd_status_wrapper,
    cmd_cp_wrapper,
    cmd_add_mount_wrapper,
    cmd_convert_wrapper,
    print_usage,
)


def _get_host_project_root(args: list[str], require_default: bool = True) -> Optional[Path]:
    """Extract project root from --project flag or use current directory.

    Args:
        args: Command line arguments
        require_default: If True, return cwd when no --project flag; if False, return None

    Returns:
        Project root path, or None if not specified and require_default is False
    """
    if '--project' in args:
        idx = args.index('--project')
        if idx + 1 < len(args):
            return Path(args[idx + 1]).resolve()
    return Path.cwd() if require_default else None


def main() -> None:
    """Main CLI entry point."""
    command = sys.argv[1] if len(sys.argv) >= 2 else 'gui'

    if command in ('--help', '-h', 'help'):
        print_usage()
        sys.exit(0)

    try:
        if command == 'gui':
            # GUI doesn't require a project on startup
            host_project_root = _get_host_project_root(sys.argv, require_default=False)
            dev_mode = '--dev-mode' in sys.argv
            from .gui import run_app
            sys.exit(run_app(host_project_root, dev_mode=dev_mode))

        # Other commands require host_project_root
        host_project_root = _get_host_project_root(sys.argv)

        if command == 'create':
            cmd_create_wrapper(host_project_root)
        elif command == 'list':
            cmd_list_wrapper(host_project_root, sys.argv)
        elif command == 'status':
            cmd_status_wrapper(host_project_root, sys.argv)
        elif command == 'push':
            cmd_push_wrapper(host_project_root, sys.argv)
        elif command == 'pull':
            cmd_pull_wrapper(host_project_root, sys.argv)
        elif command == 'cp':
            cmd_cp_wrapper(host_project_root, sys.argv)
        elif command == 'remove':
            cmd_remove_wrapper(host_project_root, sys.argv)
        elif command == 'install-git':
            cmd_install_git_wrapper(host_project_root, sys.argv)
        elif command == 'install-p4-mcp':
            cmd_install_p4_mcp_wrapper(host_project_root, sys.argv)
        elif command == 'add-mount':
            cmd_add_mount_wrapper(host_project_root, sys.argv)
        elif command == 'convert':
            cmd_convert_wrapper(host_project_root, sys.argv)
        else:
            print(f"Unknown command: {command}\n")
            print_usage()
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nCancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
