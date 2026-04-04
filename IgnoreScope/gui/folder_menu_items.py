"""Folder RMB menu item definitions for deny/exception pattern generation.

Generates gitignore-style patterns from a folder's path context.
Used by ContainerPatternListWidget and context menus to offer
pattern options when the user right-clicks a folder in the tree.

Ported from: E:/SANS/SansMachinatia/_workbench/archive/IgnoreScope/panels/folder_menu_items.py
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from pathspec.patterns.gitwildmatch import GitWildMatchPattern


class MenuItem(NamedTuple):
    """A menu item with label and pattern."""
    label: str
    pattern: str


class MenuSection(NamedTuple):
    """A section of menu items with optional header."""
    header: str | None
    items: list[MenuItem]


# Padding for aligning pattern column in menu labels
PAD = 25


def _escape_glob(text: str) -> str:
    """Escape glob special characters in path segments."""
    return GitWildMatchPattern.escape(text)


def get_deny_menu_items(
    folder_name: str,
    rel_path: str | None,
    parent_name: str | None,
    is_root: bool,
) -> list[MenuSection]:
    """Get deny pattern menu items for a folder.

    Args:
        folder_name: Name of the folder
        rel_path: Relative path from mount root (None for mount root itself)
        parent_name: Name of parent folder (None for root or direct children)
        is_root: Whether this is the mount root folder

    Returns:
        List of MenuSection with deny patterns
    """
    if is_root:
        return [MenuSection(None, [
            MenuItem(f'{"All at root":<{PAD}} *', '*'),
            MenuItem(f'{"Folders at root":<{PAD}} */', '*/'),
            MenuItem(f'{"Everything":<{PAD}} **', '**'),
        ])]

    esc_name = _escape_glob(folder_name)
    esc_path = _escape_glob(rel_path) if rel_path else None
    esc_parent = _escape_glob(parent_name) if parent_name else None

    sections = []

    any_label = f"Any '{folder_name}'"
    inside_any_label = f"Inside any '{folder_name}'"
    in_parent_label = f"In any '{parent_name}'" if parent_name else ""

    # Folder patterns (match the folder itself)
    folder_items = [
        MenuItem(f'{any_label:<{PAD}} {esc_name}/', f'{esc_name}/'),
    ]
    if esc_path:
        if esc_parent:
            exact_pattern = f'{esc_path}/'
            folder_items.append(
                MenuItem(f'{"This path only":<{PAD}} {exact_pattern}', exact_pattern)
            )
            folder_items.append(
                MenuItem(f'{in_parent_label:<{PAD}} **/{esc_parent}/{esc_name}/',
                         f'**/{esc_parent}/{esc_name}/')
            )
        else:
            exact_pattern = f'/{esc_path}/'
            folder_items.append(
                MenuItem(f'{"This path only":<{PAD}} {exact_pattern}', exact_pattern)
            )
    sections.append(MenuSection(None, folder_items))

    # Contents patterns (match files/folders inside)
    contents_items = [
        MenuItem(f'{inside_any_label:<{PAD}} {esc_name}/**', f'{esc_name}/**'),
    ]
    if esc_path:
        if esc_parent:
            contents_at_pattern = f'{esc_path}/**'
            contents_items.append(
                MenuItem(f'{"Inside this path":<{PAD}} {contents_at_pattern}', contents_at_pattern)
            )
            contents_items.append(
                MenuItem(f'{inside_parent_label:<{PAD}} **/{esc_parent}/{esc_name}/**',
                         f'**/{esc_parent}/{esc_name}/**')
            )
        else:
            contents_at_pattern = f'/{esc_path}/**'
            contents_items.append(
                MenuItem(f'{"Inside this path":<{PAD}} {contents_at_pattern}', contents_at_pattern)
            )
    sections.append(MenuSection(None, contents_items))

    return sections


def get_exception_menu_items(
    folder_name: str,
    rel_path: str,
    parent_name: str | None,
) -> list[MenuSection]:
    """Get exception pattern menu items for a masked folder.

    Args:
        folder_name: Name of the folder
        rel_path: Relative path from mount root
        parent_name: Name of parent folder (None for direct children of root)

    Returns:
        List of MenuSection with exception patterns (! prefix)
    """
    esc_name = _escape_glob(folder_name)
    esc_path = _escape_glob(rel_path)
    esc_parent = _escape_glob(parent_name) if parent_name else None

    any_label = f"Any '{folder_name}'"
    in_parent_label = f"In any '{parent_name}'" if parent_name else ""

    if esc_parent:
        exact_pattern = f'!{esc_path}/'
    else:
        exact_pattern = f'!/{esc_path}/'

    items = [
        MenuItem(f'{any_label:<{PAD}} !{esc_name}/', f'!{esc_name}/'),
        MenuItem(f'{"This path only":<{PAD}} {exact_pattern}', exact_pattern),
    ]

    if esc_parent:
        items.append(
            MenuItem(f'{in_parent_label:<{PAD}} !**/{esc_parent}/{esc_name}/',
                     f'!**/{esc_parent}/{esc_name}/')
        )

    return [MenuSection("Add Exception", items)]


def get_folder_info(
    path: Path, root: Path,
) -> tuple[str, str | None, str | None, bool]:
    """Extract folder info needed for menu item generation.

    Args:
        path: Path to the folder
        root: Mount root path

    Returns:
        Tuple of (folder_name, rel_path, parent_name, is_root)
    """
    folder_name = path.name
    is_root = (path == root)

    if is_root:
        return folder_name, None, None, True

    rel_path = str(path.relative_to(root)).replace('\\', '/')
    parent_name = path.parent.name if path.parent != root else None

    return folder_name, rel_path, parent_name, False


def build_all_deny_items(
    folder_name: str, rel_path: str | None,
    parent_name: str | None, is_root: bool,
) -> list[MenuItem]:
    """Flat list of all deny menu items (no section separators)."""
    sections = get_deny_menu_items(folder_name, rel_path, parent_name, is_root)
    items = []
    for section in sections:
        items.extend(section.items)
    return items


def build_all_exception_items(
    folder_name: str, rel_path: str,
    parent_name: str | None,
) -> list[MenuItem]:
    """Flat list of all exception menu items (no section headers)."""
    sections = get_exception_menu_items(folder_name, rel_path, parent_name)
    items = []
    for section in sections:
        items.extend(section.items)
    return items
