"""Interactive CLI prompts for IgnoreScope configuration.

Provides interactive setup for creating Docker container configurations,
and command wrappers for CLI operations.
"""

import sys
from pathlib import Path
from typing import Set

from ..core.config import ScopeDockerConfig, SiblingMount, list_containers
from ..docker.names import build_docker_name
from .commands import (
    cmd_create, cmd_push, cmd_pull, cmd_remove,
    cmd_install_git, cmd_install_p4_mcp,
    cmd_list, cmd_status, cmd_cp,
    cmd_add_mount, cmd_convert,
    cmd_add_folder, cmd_mark_permanent, cmd_unmark_permanent,
)


def _parse_container_arg(args: list[str]) -> str:
    """Parse --container argument from command line args.

    Args:
        args: Command line arguments

    Returns:
        Container name or 'default' if not specified
    """
    for i, arg in enumerate(args):
        if arg == '--container' and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith('--container='):
            return arg.split('=', 1)[1]
    return "default"


def _prompt_yes_no(question: str, default: bool = False) -> bool:
    """Prompt user for yes/no response.

    Args:
        question: Question to ask
        default: Default response if user presses Enter

    Returns:
        True if yes, False if no
    """
    default_str = "Y/n" if default else "y/N"
    response = input(f"{question} ({default_str}): ").strip().lower()

    if response == '':
        return default
    return response in ('y', 'yes')


def _configure_sibling(sibling_num: int) -> SiblingMount | None:
    """Configure a single sibling mount interactively.

    Args:
        sibling_num: Number for display (1, 2, 3...)

    Returns:
        Configured SiblingMount or None if cancelled
    """
    print(f"\n--- Sibling Mount #{sibling_num} ---")

    # Get host path
    host_path_str = input("Host path (absolute path, or empty to cancel): ").strip()
    if not host_path_str:
        return None

    host_path = Path(host_path_str)
    if not host_path.is_absolute():
        print("  Error: Path must be absolute")
        return None
    if not host_path.exists():
        print(f"  Warning: Path does not exist: {host_path}")
        if not _prompt_yes_no("Continue anyway?", default=False):
            return None

    # Get container path
    default_container_path = f"/{host_path.name}"
    container_path_str = input(f"Container path ({default_container_path}): ").strip()
    container_path = container_path_str if container_path_str else default_container_path

    # Ensure container path starts with /
    if not container_path.startswith('/'):
        container_path = '/' + container_path

    sibling = SiblingMount(
        host_path=host_path,
        container_path=container_path,
    )

    # Check if there are folders to configure
    if not host_path.exists() or not host_path.is_dir():
        return sibling

    # List folders in sibling
    folders = sorted([f for f in host_path.iterdir() if f.is_dir() and not f.name.startswith('.')])
    if not folders:
        print("  No subfolders found in sibling path")
        return sibling

    # Mount folders
    print("\n  Select folders to mount (visible to container):")
    for folder in folders:
        if _prompt_yes_no(f"  Mount '{folder.name}'?", default=False):
            sibling.add_mount(folder)

    if not sibling.mounts:
        # If no specific mounts, the entire sibling is accessible
        return sibling

    # Masked folders
    mounted_subfolders: Set[Path] = set()
    for mount in sibling.mounts:
        if mount.is_dir():
            for item in mount.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    mounted_subfolders.add(item)

    if mounted_subfolders:
        print("\n  Select subfolders to mask (hidden from container):")
        for subfolder in sorted(mounted_subfolders):
            rel = subfolder.relative_to(host_path)
            if _prompt_yes_no(f"  Mask '{rel}'?", default=False):
                sibling.add_mask(subfolder)

    # Revealed folders
    if sibling.masked:
        masked_subfolders: Set[Path] = set()
        for masked_folder in sibling.masked:
            if masked_folder.is_dir():
                for item in masked_folder.iterdir():
                    if item.is_dir() and not item.name.startswith('.'):
                        masked_subfolders.add(item)

        if masked_subfolders:
            print("\n  Select subfolders to unmask (punch-through):")
            for subfolder in sorted(masked_subfolders):
                rel = subfolder.relative_to(host_path)
                if _prompt_yes_no(f"  Unmask '{rel}'?", default=False):
                    sibling.add_reveal(subfolder)

    return sibling


def _interactive_create(host_project_root: Path) -> ScopeDockerConfig:
    """Interactively build a ScopeDockerConfig.

    Prompts user for mounts, masked, and revealed folders.

    Args:
        host_project_root: Project root directory

    Returns:
        Configured ScopeDockerConfig instance
    """
    config = ScopeDockerConfig(host_project_root=host_project_root)

    print("\n=== IgnoreScope Configuration ===\n")

    # Container root name (derived from host_container_root by __post_init__)
    derived_root = config.container_root
    print("--- Container Root Path ---")
    print(f"Default: {derived_root}")
    custom_root = input(f"Container root path ({derived_root}): ").strip()
    if custom_root:
        # Ensure it starts with /
        if not custom_root.startswith('/'):
            custom_root = '/' + custom_root
        # Remove trailing slash
        custom_root = custom_root.rstrip('/')
        config.container_root = custom_root

    # Gather folders to consider
    print("\nScanning folders in project...")
    top_level = list(host_project_root.iterdir())
    folders = sorted([f for f in top_level if f.is_dir() and not f.name.startswith('.')])

    if not folders:
        print("No folders found in project")
        return config

    # Mount folders
    print("\n--- Mount Folders (visible to container) ---")
    for folder in folders:
        if _prompt_yes_no(f"Mount '{folder.name}'?", default=False):
            config.add_mount(folder)

    if not config.mounts:
        print("No mounts configured. Exiting.")
        return config

    # Masked folders (within mounted folders)
    print("\n--- Mask Folders (hidden from container) ---")
    print("(Select subfolders of mounted folders to mask)")

    mounted_subfolders: Set[Path] = set()
    for mount in config.mounts:
        for item in mount.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                mounted_subfolders.add(item)

    for subfolder in sorted(mounted_subfolders):
        if _prompt_yes_no(f"Mask '{subfolder.relative_to(host_project_root)}'?", default=False):
            config.add_mask(subfolder)

    # Revealed folders (within masked folders)
    if config.masked:
        print("\n--- Unmask Folders (re-expose within masks) ---")
        print("(Select subfolders of masked folders to unmask)")

        masked_subfolders: Set[Path] = set()
        for masked_folder in config.masked:
            for item in masked_folder.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    masked_subfolders.add(item)

        for subfolder in sorted(masked_subfolders):
            rel_path = subfolder.relative_to(host_project_root)
            if _prompt_yes_no(f"Unmask '{rel_path}'?", default=False):
                config.add_reveal(subfolder)

    # Sibling mounts (external directories)
    print("\n--- Sibling Mounts (external directories) ---")
    print("Mount folders outside project root as container siblings")
    print("(e.g., shared libraries at /shared/)")

    siblings = []
    sibling_num = 1
    while True:
        if not _prompt_yes_no(f"Add sibling mount?", default=False):
            break
        sibling = _configure_sibling(sibling_num)
        if sibling:
            siblings.append(sibling)
            sibling_num += 1
            print(f"  Added: {sibling.host_path} -> {sibling.container_path}")

    config.siblings = siblings

    # Scope name
    print("\n--- Scope Name ---")
    default_scope = "default"
    custom_name = input(f"Scope name ({default_scope}): ").strip()
    scope_name = custom_name if custom_name else default_scope
    config.scope_name = scope_name

    # Dev mode
    print("\n--- Pull Mode ---")
    dev_mode = _prompt_yes_no(
        "Safe mode: pull to ./Pulled/{timestamp}/ (non-destructive)?",
        default=True
    )
    config.dev_mode = dev_mode

    # Show summary
    docker_name = build_docker_name(host_project_root, config.scope_name)
    print("\n=== Configuration Summary ===")
    print(f"Scope: {config.scope_name}")
    print(f"Docker container: {docker_name}")
    print(f"Container root: {config.container_root}")
    print(f"Pull mode: {'Safe (./Pulled/)' if config.dev_mode else 'Production (overwrite)'}")
    print(f"Mounts: {len(config.mounts)}")
    print(f"Masked: {len(config.masked)}")
    print(f"Revealed: {len(config.revealed)}")
    print(f"Sibling mounts: {len(config.siblings)}")
    for sibling in config.siblings:
        print(f"  {sibling.host_path} -> {sibling.container_path}")

    if _prompt_yes_no("\nProceed with create?", default=True):
        return config

    return ScopeDockerConfig(host_project_root=host_project_root)


def cmd_create_wrapper(host_project_root: Path) -> None:
    """Wrapper for create command with interactive setup."""
    config = _interactive_create(host_project_root)

    if not config:
        print("\nNo configuration. Exiting.")
        return

    print("\n=== Creating Container ===\n")
    success, msg = cmd_create(host_project_root, config)

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_push_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for push command."""
    scope_name = _parse_container_arg(args)
    # Filter out --container args from files list
    specific_files = [a for a in args[2:] if not a.startswith('--container') and a != scope_name]
    specific_files = specific_files if specific_files else None

    success, msg = cmd_push(host_project_root, scope_name, specific_files)

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_pull_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for pull command."""
    scope_name = _parse_container_arg(args)
    # Filter out --container args from files list
    specific_files = [a for a in args[2:] if not a.startswith('--container') and a != scope_name]
    specific_files = specific_files if specific_files else None

    success, msg = cmd_pull(host_project_root, scope_name, specific_files)

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_remove_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for remove command."""
    scope_name = _parse_container_arg(args)
    confirm = '--yes' in args or '-y' in args

    success, msg = cmd_remove(host_project_root, scope_name, confirm=confirm)

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_install_git_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for install-git command."""
    scope_name = _parse_container_arg(args)

    # Parse optional flags
    distro = "auto"
    configure = False
    name = ""
    email = ""
    project_dir = ""
    scope_dir = ""
    for i, arg in enumerate(args):
        if arg == '--distro' and i + 1 < len(args):
            distro = args[i + 1]
        elif arg.startswith('--distro='):
            distro = arg.split('=', 1)[1]
        elif arg == '--configure':
            configure = True
        elif arg == '--name' and i + 1 < len(args):
            name = args[i + 1]
        elif arg.startswith('--name='):
            name = arg.split('=', 1)[1]
        elif arg == '--email' and i + 1 < len(args):
            email = args[i + 1]
        elif arg.startswith('--email='):
            email = arg.split('=', 1)[1]
        elif arg == '--project-dir' and i + 1 < len(args):
            project_dir = args[i + 1]
        elif arg.startswith('--project-dir='):
            project_dir = arg.split('=', 1)[1]
        elif arg == '--scope-dir' and i + 1 < len(args):
            scope_dir = args[i + 1]
        elif arg.startswith('--scope-dir='):
            scope_dir = arg.split('=', 1)[1]

    success, msg = cmd_install_git(
        host_project_root, scope_name, distro, configure, name, email,
        project_dir, scope_dir,
    )

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_install_p4_mcp_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for install-p4-mcp command."""
    scope_name = _parse_container_arg(args)

    # Parse optional flags
    devenv_mount = "/devenv"
    project_dir = ""
    scope_dir = ""
    p4port = ""
    p4user = ""
    p4client = ""
    for i, arg in enumerate(args):
        if arg == '--devenv-mount' and i + 1 < len(args):
            devenv_mount = args[i + 1]
        elif arg.startswith('--devenv-mount='):
            devenv_mount = arg.split('=', 1)[1]
        elif arg == '--project-dir' and i + 1 < len(args):
            project_dir = args[i + 1]
        elif arg.startswith('--project-dir='):
            project_dir = arg.split('=', 1)[1]
        elif arg == '--scope-dir' and i + 1 < len(args):
            scope_dir = args[i + 1]
        elif arg.startswith('--scope-dir='):
            scope_dir = arg.split('=', 1)[1]
        elif arg == '--p4port' and i + 1 < len(args):
            p4port = args[i + 1]
        elif arg.startswith('--p4port='):
            p4port = arg.split('=', 1)[1]
        elif arg == '--p4user' and i + 1 < len(args):
            p4user = args[i + 1]
        elif arg.startswith('--p4user='):
            p4user = arg.split('=', 1)[1]
        elif arg == '--p4client' and i + 1 < len(args):
            p4client = args[i + 1]
        elif arg.startswith('--p4client='):
            p4client = arg.split('=', 1)[1]

    success, msg = cmd_install_p4_mcp(
        host_project_root, scope_name, devenv_mount,
        project_dir, scope_dir, p4port, p4user, p4client,
    )

    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def cmd_list_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for list command."""
    success, msg = cmd_list(host_project_root)
    print(msg)
    sys.exit(0 if success else 1)


def cmd_status_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for status command."""
    scope_name = _parse_container_arg(args)
    success, msg = cmd_status(host_project_root, scope_name)
    print(msg)
    sys.exit(0 if success else 1)


def _parse_flag_value(args: list[str], flag: str) -> str | None:
    """Extract ``--flag value`` or ``--flag=value`` from args. Returns None if absent."""
    for i, arg in enumerate(args):
        if arg == flag and i + 1 < len(args):
            return args[i + 1]
        if arg.startswith(f"{flag}="):
            return arg.split("=", 1)[1]
    return None


def _collect_positional(
    args: list[str],
    start: int = 2,
    bool_flags: set[str] | None = None,
) -> list[str]:
    """Collect non-flag positional args, skipping ``--flag value`` pairs.

    Args:
        args: argv-style list.
        start: index to begin scanning from (default 2 — past command name).
        bool_flags: flag names that take no value (e.g. ``{"--permanent"}``).
            These are skipped without consuming the next arg.
    """
    bool_flags = bool_flags or set()
    positional: list[str] = []
    skip_next = False
    for i, arg in enumerate(args[start:], start=start):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith("--"):
            if arg in bool_flags or "=" in arg:
                continue
            if i + 1 < len(args):
                skip_next = True
            continue
        positional.append(arg)
    return positional


def cmd_add_mount_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for add-mount command.

    Usage: python -m IgnoreScope add-mount <path> [--container NAME]
                                                   [--delivery bind|detached]
                                                   [--seed tree|folder]
    """
    scope_name = _parse_container_arg(args)
    delivery = _parse_flag_value(args, "--delivery") or "bind"
    seed = _parse_flag_value(args, "--seed") or "tree"

    positional = _collect_positional(args)
    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope add-mount [--container NAME] "
              "[--delivery bind|detached] [--seed tree|folder] <path>")
        sys.exit(1)

    path = Path(positional[0])
    success, msg = cmd_add_mount(host_project_root, scope_name, path, delivery, seed)
    print(f"[{'OK' if success else 'ERROR'}] {msg}")
    sys.exit(0 if success else 1)


def cmd_add_folder_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for add-folder command.

    Usage: python -m IgnoreScope add-folder <container_path> [--container NAME]
                                                              [--permanent | --volume]
    """
    scope_name = _parse_container_arg(args)
    permanent = "--permanent" in args
    volume = "--volume" in args

    positional = _collect_positional(
        args, bool_flags={"--permanent", "--volume"},
    )
    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope add-folder [--container NAME] "
              "[--permanent | --volume] <container_path>")
        sys.exit(1)

    container_path = Path(positional[0])
    success, msg = cmd_add_folder(
        host_project_root, scope_name, container_path,
        permanent=permanent, volume=volume,
    )
    print(f"[{'OK' if success else 'ERROR'}] {msg}")
    sys.exit(0 if success else 1)


def cmd_mark_permanent_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for mark-permanent command.

    Usage: python -m IgnoreScope mark-permanent <container_path> [--container NAME]
    """
    scope_name = _parse_container_arg(args)

    positional = _collect_positional(args)
    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope mark-permanent "
              "[--container NAME] <container_path>")
        sys.exit(1)

    container_path = Path(positional[0])
    success, msg = cmd_mark_permanent(host_project_root, scope_name, container_path)
    print(f"[{'OK' if success else 'ERROR'}] {msg}")
    sys.exit(0 if success else 1)


def cmd_unmark_permanent_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for unmark-permanent command.

    Usage: python -m IgnoreScope unmark-permanent <container_path> [--container NAME]
    """
    scope_name = _parse_container_arg(args)

    positional = _collect_positional(args)
    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope unmark-permanent "
              "[--container NAME] <container_path>")
        sys.exit(1)

    container_path = Path(positional[0])
    success, msg = cmd_unmark_permanent(host_project_root, scope_name, container_path)
    print(f"[{'OK' if success else 'ERROR'}] {msg}")
    sys.exit(0 if success else 1)


def cmd_convert_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for convert command.

    Usage: python -m IgnoreScope convert <path> --to {bind,detached}
                                         [--container NAME]
    """
    scope_name = _parse_container_arg(args)
    target = _parse_flag_value(args, "--to")
    if target is None:
        print("[ERROR] --to {bind,detached} is required")
        sys.exit(1)

    positional = _collect_positional(args)
    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope convert [--container NAME] "
              "<path> --to {bind,detached}")
        sys.exit(1)

    path = Path(positional[0])
    success, msg = cmd_convert(host_project_root, scope_name, path, target)
    print(f"[{'OK' if success else 'ERROR'}] {msg}")
    sys.exit(0 if success else 1)


def cmd_cp_wrapper(host_project_root: Path, args: list[str]) -> None:
    """Wrapper for cp command."""
    scope_name = _parse_container_arg(args)

    # Collect positional args (source and optional dest) — skip flags
    positional = []
    skip_next = False
    for i, arg in enumerate(args[2:], start=2):
        if skip_next:
            skip_next = False
            continue
        if arg.startswith('--'):
            if '=' not in arg and i + 1 < len(args):
                skip_next = True
            continue
        positional.append(arg)

    if not positional:
        print("[ERROR] Usage: python -m IgnoreScope cp [--container NAME] <source> [<dest>]")
        sys.exit(1)

    source = positional[0]
    dest = positional[1] if len(positional) > 1 else ""

    success, msg = cmd_cp(host_project_root, scope_name, source, dest)
    if success:
        print(f"[OK] {msg}")
        sys.exit(0)
    else:
        print(f"[ERROR] {msg}")
        sys.exit(1)


def print_usage() -> None:
    """Print usage information."""
    print("""
IgnoreScope: Docker container management with masked folders

Usage:
    python -m IgnoreScope gui [--project PATH]
    python -m IgnoreScope create [--project PATH]
    python -m IgnoreScope list [--project PATH]
    python -m IgnoreScope status [--project PATH] [--container NAME]
    python -m IgnoreScope push [--project PATH] [--container NAME] [FILES...]
    python -m IgnoreScope pull [--project PATH] [--container NAME] [FILES...]
    python -m IgnoreScope cp [--project PATH] [--container NAME] <source> [<dest>]
    python -m IgnoreScope remove [--project PATH] [--container NAME] [--yes]
    python -m IgnoreScope install-git [--project PATH] [--container NAME] [--distro auto|debian|alpine]
                                      [--project-dir DIR] [--scope-dir DIR]
    python -m IgnoreScope install-p4-mcp [--project PATH] [--container NAME] [--devenv-mount PATH]
                                         [--project-dir DIR] [--scope-dir DIR]
                                         [--p4port HOST] [--p4user USER] [--p4client WS]
    python -m IgnoreScope add-mount [--project PATH] [--container NAME]
                                    [--delivery bind|detached] [--seed tree|folder] <path>
    python -m IgnoreScope add-folder [--project PATH] [--container NAME]
                                     [--permanent | --volume] <container_path>
    python -m IgnoreScope mark-permanent [--project PATH] [--container NAME] <container_path>
    python -m IgnoreScope unmark-permanent [--project PATH] [--container NAME] <container_path>
    python -m IgnoreScope convert [--project PATH] [--container NAME]
                                  <path> --to {bind,detached}

Commands:
    gui              Launch graphical configuration editor (PyQt6)
    create           Interactive CLI setup: mounts, masks, reveals
    list             List all containers for a project with status
    status           Show detailed status of a single container
    push             Push tracked files to container (workflow — tracks files)
    pull             Pull tracked files from container (./Pulled/ or overwrite)
    cp               Copy file or directory to container (raw docker cp — no tracking)
    remove           Remove container and volumes
    install-git      Install Git into a running container
    install-p4-mcp   Install P4 MCP Server from devenv mount
    add-mount        Add a mount spec — Mount / Virtual Mount / Virtual Folder (host-backed)
    add-folder       Add a container-only folder spec — Make Folder / Permanent / Volume
    mark-permanent   Set preserve_on_update=True on a detached folder spec
    unmark-permanent Set preserve_on_update=False on a detached folder spec
    convert          Flip a mount spec's delivery (bind <-> detached)

Options:
    --project PATH     Project root directory (default: current directory)
    --container NAME   Container name (default: 'default')
    --yes             Skip confirmation prompts
    -y                Short form of --yes
    --distro TYPE     Distro type for install-git (auto, debian, alpine)
    --configure       Also configure git identity (requires --name, --email)
    --name NAME       Git user.name (with --configure)
    --email EMAIL     Git user.email (with --configure)
    --devenv-mount PATH  Container devenv mount path for install-p4-mcp (default: /devenv)
    --delivery MODE    Mount delivery mode for add-mount (bind or detached; default: bind)
    --seed MODE        Content seed for add-mount (tree or folder; default: tree).
                       'folder' requires --delivery detached (Virtual Folder gesture).
    --permanent        add-folder: soft-permanent (preserve_on_update=True; cp out/in across update)
    --volume           add-folder: hard-permanent named Docker volume (delivery=volume)
    --to MODE          Target delivery mode for convert (bind or detached; required)

  Config Deploy Options (optional — deploys default config files after binary install):
    --project-dir DIR   Container project root (e.g. /MyProject)
    --scope-dir DIR     Container scope dir (e.g. /MyProject/.ignore_scope/dev)
    --p4port HOST       Perforce server address (install-p4-mcp only)
    --p4user USER       Perforce username (install-p4-mcp only)
    --p4client WS       Perforce workspace name (install-p4-mcp only)

Config Location:
    {project_root}/.ignore_scope/{scope_name}/scope_docker_desktop.json

Examples:
    python -m IgnoreScope gui
    python -m IgnoreScope gui --project E:\\MyProject
    python -m IgnoreScope create
    python -m IgnoreScope list
    python -m IgnoreScope list --project E:\\MyProject
    python -m IgnoreScope status --container dev
    python -m IgnoreScope push --container dev config.ini
    python -m IgnoreScope pull --container prod
    python -m IgnoreScope cp --container dev C:\\tools\\binary /usr/local/bin/binary
    python -m IgnoreScope cp --container dev C:\\tools\\mydir /opt/mydir
    python -m IgnoreScope remove --container dev --yes
    python -m IgnoreScope install-git --container dev
    python -m IgnoreScope install-git --container dev --project-dir /MyProject --scope-dir /MyProject/.ignore_scope/dev
    python -m IgnoreScope install-p4-mcp --container dev
    python -m IgnoreScope install-p4-mcp --container dev --devenv-mount /custom
    python -m IgnoreScope install-p4-mcp --container dev --project-dir /MyProject --scope-dir /MyProject/.ignore_scope/dev --p4port ssl:perforce:1666 --p4user myuser --p4client myworkspace
""".strip())
