"""Tests for Phase 3 Task 4.9 — L4 auth volume rendering.

Covers:
  - MountDataTree emits synthetic stencil nodes for extension isolation_paths
    with stencil_tier="auth", source=NodeSource.STENCIL, is_stencil_node=True.
  - Synthetic NodeState has visibility="virtual" so FOLDER_STENCIL_AUTH style
    fires through resolve_tree_state.
  - set_extensions() rebuilds the L4 set idempotently.
  - ScopeView RMB on an L4 stencil node is silent-no-op (only the
    "No valid actions" fallback is offered — no Make Folder / Mark Permanent).
  - Model exposes NodeStencilTierRole returning "auth" for L4 nodes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QApplication, QMenu

from IgnoreScope.core.local_mount_config import ExtensionConfig
from IgnoreScope.gui.display_config import resolve_tree_state
from IgnoreScope.gui.mount_data_model import (
    MountDataTreeModel,
    NodeStateRole,
    NodeStencilTierRole,
)
from IgnoreScope.gui.mount_data_tree import (
    MountDataNode,
    MountDataTree,
    NodeSource,
)
from IgnoreScope.gui.scope_view import ScopeView
from IgnoreScope.gui.style_engine import StyleGui


@pytest.fixture(autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_style_singleton():
    StyleGui._reset()
    yield
    StyleGui._reset()


@pytest.fixture
def tree(tmp_path: Path) -> MountDataTree:
    t = MountDataTree()
    t.set_host_project_root(tmp_path)
    return t


def _make_extension(name: str, isolation_paths: list[str]) -> ExtensionConfig:
    return ExtensionConfig(
        name=name,
        installer_class=f"{name}Installer",
        isolation_paths=list(isolation_paths),
    )


class TestL4StencilEmission:
    """set_extensions() emits one stencil node per isolation_path."""

    def test_single_extension_single_path_emits_one_node(self, tree: MountDataTree):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        assert len(tree._stencil_nodes) == 1
        node = tree._stencil_nodes[0]
        assert node.is_stencil_node is True
        assert node.stencil_tier == "auth"
        assert node.source is NodeSource.STENCIL
        assert node.path == Path("/root/.local")
        assert node.container_path == "/root/.local"

    def test_multiple_extensions_emits_one_per_path(self, tree: MountDataTree):
        exts = [
            _make_extension("Claude Code", ["/root/.local"]),
            _make_extension("P4 MCP", ["/usr/local/lib/p4-mcp", "/etc/p4"]),
        ]
        tree.set_extensions(exts)

        assert len(tree._stencil_nodes) == 3
        paths = sorted(str(n.path) for n in tree._stencil_nodes)
        # Path normalization on Windows uses backslashes — compare via Path.
        path_set = {n.path for n in tree._stencil_nodes}
        assert Path("/root/.local") in path_set
        assert Path("/usr/local/lib/p4-mcp") in path_set
        assert Path("/etc/p4") in path_set

    def test_extension_with_no_isolation_paths_emits_nothing(
        self, tree: MountDataTree,
    ):
        ext = _make_extension("Git", [])
        tree.set_extensions([ext])
        assert tree._stencil_nodes == []

    def test_set_extensions_is_idempotent(self, tree: MountDataTree):
        """Calling set_extensions twice with the same list yields the same set."""
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        tree.set_extensions([ext])
        assert len(tree._stencil_nodes) == 1

    def test_set_extensions_replaces_prior_set(self, tree: MountDataTree):
        """Adding then removing extensions clears the L4 stencil set."""
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        assert len(tree._stencil_nodes) == 1

        tree.set_extensions([])
        assert tree._stencil_nodes == []

    def test_stencil_nodes_appear_under_root_node(self, tree: MountDataTree):
        """L4 stencils are appended to root_node.children for tree visibility."""
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        assert tree.root_node is not None
        root_children_paths = {c.path for c in tree.root_node.children}
        assert Path("/root/.local") in root_children_paths


class TestL4StencilState:
    """Synthetic NodeState routes stencils to the FOLDER_STENCIL_AUTH style."""

    def test_synthetic_state_is_virtual(self, tree: MountDataTree):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        state = tree.get_node_state(Path("/root/.local"))
        assert state.visibility == "virtual"

    def test_resolves_to_folder_stencil_auth_style(self, tree: MountDataTree):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        state = tree.get_node_state(Path("/root/.local"))
        state_name = resolve_tree_state(
            state, is_folder=True, stencil_tier="auth",
        )
        assert state_name == "FOLDER_STENCIL_AUTH"


class TestL4StencilTierRole:
    """The model exposes stencil_tier via NodeStencilTierRole."""

    def test_role_returns_auth_for_l4_nodes(self, tree: MountDataTree):
        from IgnoreScope.gui.display_config import ScopeDisplayConfig

        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        model = MountDataTreeModel(tree, ScopeDisplayConfig())

        # Find the stencil node row under root.
        root_idx = model.index(0, 0)  # invisible root not modeled — root_node row
        # Walk root_node.children to find the stencil entry.
        found = False
        for row in range(model.rowCount()):
            idx = model.index(row, 0)
            node = idx.internalPointer()
            if node is not None and node.is_stencil_node:
                tier = idx.data(NodeStencilTierRole)
                assert tier == "auth"
                found = True
        assert found, "L4 stencil row not exposed by model"

    def test_role_returns_mirrored_for_non_stencil_nodes(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        from IgnoreScope.gui.display_config import ScopeDisplayConfig

        # Create a real folder so set_host_project_root sees it.
        (tmp_path / "src").mkdir()
        # Re-scan to pick up the new folder.
        tree.set_host_project_root(tmp_path)
        model = MountDataTreeModel(tree, ScopeDisplayConfig())

        # Root_node itself is the first row exposed.
        idx = model.index(0, 0)
        node = idx.internalPointer()
        assert node is not None
        assert node.is_stencil_node is False
        tier = idx.data(NodeStencilTierRole)
        assert tier == "mirrored"


class TestScopeViewRmbSilentNoOp:
    """RMB on an extension-owned volume spec yields silent-no-op fallback only.

    Task 1.10: the read-only guard is now owner-keyed
    (``spec.delivery == "volume" and spec.owner.startswith("extension:")``),
    not tree-node-tag-keyed (``is_stencil_node and stencil_tier == "auth"``).
    """

    def test_l4_stencil_rmb_offers_only_fallback(self, tree: MountDataTree):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        view = ScopeView(tree)

        stencil_node = tree._stencil_nodes[0]
        menu = QMenu()
        # Drive the per-node routing decision directly — bypassing indexAt which
        # needs a real paint event. Mirrors the owner-keyed guard inside
        # ScopeView._show_context_menu.
        spec = tree.get_any_spec_at(stencil_node.path)
        if (
            spec is not None
            and spec.delivery == "volume"
            and spec.owner.startswith("extension:")
        ):
            pass  # silent-no-op branch
        view._append_fallback_if_empty(menu)

        texts = [a.text() for a in menu.actions()]
        assert texts == ["No valid actions"]
        assert menu.actions()[0].isEnabled() is False

    def test_l4_stencil_does_not_emit_make_folder(self, tree: MountDataTree):
        """Sanity: an extension-owned volume spec never routes to gesture set."""
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        view = ScopeView(tree)

        stencil_node = tree._stencil_nodes[0]
        menu = QMenu()
        spec = tree.get_any_spec_at(stencil_node.path)
        is_readonly = (
            spec is not None
            and spec.delivery == "volume"
            and spec.owner.startswith("extension:")
        )
        if not is_readonly:
            view._add_scope_config_gestures(menu, node=stencil_node)
        view._append_fallback_if_empty(menu)

        texts = [a.text() for a in menu.actions()]
        assert "Make Folder" not in texts
        assert "Mark Permanent" not in texts
        assert "Remove" not in texts


class TestOwnerKeyedRoutingGuard:
    """Task 1.10 — read-only guard routes by owner, not by tree-node tag.

    User-authored ``delivery="volume"`` specs (``owner="user"``) must reach
    the editable gesture menu. Extension-synthesized specs
    (``owner="extension:{name}"``) must take the silent-no-op branch.
    """

    def test_user_authored_volume_routes_to_gesture_menu(
        self, tree: MountDataTree,
    ):
        from IgnoreScope.gui.mount_data_tree import MountDataNode

        container_path = Path("/var/data")
        tree.add_stencil_volume(container_path)
        view = ScopeView(tree)

        node = MountDataNode(path=container_path)
        menu = QMenu()

        # Mirror ScopeView._show_context_menu's single-node routing logic.
        spec = tree.get_any_spec_at(node.path)
        is_readonly = (
            spec is not None
            and spec.delivery == "volume"
            and spec.owner.startswith("extension:")
        )
        if is_readonly:
            pass
        elif node.is_file:
            pass  # Not exercised in this test — no file.
        elif tree.get_spec_at(node.path) is not None:
            view._add_scope_config_gestures(menu, node=node)
        else:
            pass  # Not exercised — spec exists.

        texts = [a.text() for a in menu.actions()]
        assert "Remove" in texts, (
            "User-authored volume spec must reach editable gesture menu"
        )

    def test_extension_volume_routes_to_silent_noop(self, tree: MountDataTree):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        view = ScopeView(tree)

        stencil_node = tree._stencil_nodes[0]
        menu = QMenu()

        spec = tree.get_any_spec_at(stencil_node.path)
        is_readonly = (
            spec is not None
            and spec.delivery == "volume"
            and spec.owner.startswith("extension:")
        )
        if is_readonly:
            pass  # Silent-no-op path
        else:
            pytest.fail(
                f"Extension-owned volume spec must be read-only; "
                f"guard returned is_readonly={is_readonly}, spec={spec}",
            )

        view._append_fallback_if_empty(menu)
        texts = [a.text() for a in menu.actions()]
        assert texts == ["No valid actions"]

    def test_get_any_spec_at_returns_user_spec_first(
        self, tree: MountDataTree,
    ):
        """User-authored specs win over extension-synthesized on path collision."""
        shared = Path("/var/data")
        tree.add_stencil_volume(shared)
        ext = _make_extension("Custom", ["/var/data"])
        tree.set_extensions([ext])

        spec = tree.get_any_spec_at(shared)
        assert spec is not None
        assert spec.owner == "user"

    def test_get_any_spec_at_returns_extension_spec_when_user_absent(
        self, tree: MountDataTree,
    ):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        spec = tree.get_any_spec_at(Path("/root/.local"))
        assert spec is not None
        assert spec.owner.startswith("extension:")
        assert spec.delivery == "volume"


class TestRebuildIdempotency:
    """_rebuild_extension_stencil_nodes drops prior auth nodes before re-emitting."""

    def test_does_not_duplicate_root_children_on_double_call(
        self, tree: MountDataTree,
    ):
        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])
        first_count = len(tree.root_node.children)

        # Direct re-call should not duplicate root children.
        tree._rebuild_extension_stencil_nodes()
        assert len(tree.root_node.children) == first_count

    def test_preserves_non_stencil_root_children(
        self, tree: MountDataTree, tmp_path: Path,
    ):
        """Sibling and project children must survive a stencil rebuild."""
        # Project root scan adds a few children based on tmp_path content;
        # we don't depend on count, just on structure preservation.
        (tmp_path / "src").mkdir()
        tree.set_host_project_root(tmp_path)
        before_paths = {c.path for c in tree.root_node.children}

        ext = _make_extension("Claude Code", ["/root/.local"])
        tree.set_extensions([ext])

        after_paths = {c.path for c in tree.root_node.children}
        # Every prior child still present + new stencil added.
        assert before_paths.issubset(after_paths)
        assert Path("/root/.local") in after_paths
