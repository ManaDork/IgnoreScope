"""Regression test: marked-push drain must not collapse tree expansion.

Bug: ``_workbench/_bugs/push-collapses-localhost-tree.md``.

The drain calls ``ConfigManager.reload_current_scope`` to re-read pushed_files
from disk. The old code unconditionally ran ``_local_host.refresh()`` and
``_scope_view.refresh()`` — both ``MountDataTreeModel.refresh`` (i.e.
``beginResetModel()`` / ``endResetModel()``), which drops every persistent
index in both trees and dumps the user back at the root. The drain promotes
``pushed_files`` only; structure (mount specs, siblings, extension stencils)
is unchanged, so the model reset is unnecessary.

Fix surface:

  * ``MountDataTree.begin_batch`` / ``end_batch`` now gate ``mountSpecsChanged``
    symmetrically with ``stateChanged`` (so ``load_config``'s emit is absorbed
    when ``end_batch(emit=False)`` runs).
  * ``ConfigManager.reload_current_scope(data_only=True)`` skips
    ``_local_host.refresh()`` / ``_scope_view.refresh()`` and instead emits
    ``MountDataTree.stateChanged`` manually so the cheap
    ``_on_tree_changed → dataChanged`` and ``_update_config_viewer`` wiring
    fires without resetting the models.
  * ``FileOperationsHandler.drain_marked_push_now`` opts into ``data_only=True``;
    every other ``reload_current_scope`` caller stays on the default structural
    reload.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtWidgets import QApplication

from IgnoreScope.core.config import ScopeDockerConfig
from IgnoreScope.core.op_result import OpResult
from IgnoreScope.gui.config_manager import ConfigManager
from IgnoreScope.gui.file_ops_ui import FileOperationsHandler
from IgnoreScope.gui.mount_data_tree import MountDataTree

SCOPE = "dev"


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def host_file(tmp_path: Path) -> Path:
    f = tmp_path / "src" / "a.txt"
    f.parent.mkdir(parents=True)
    f.write_text("x", encoding="utf-8")
    return f


@pytest.fixture
def app(tmp_path: Path):
    """Assemble the minimum app surface the drain path touches.

    Real ``MountDataTree`` + real ``ConfigManager`` (so we exercise the actual
    ``reload_current_scope`` body and the ``mountSpecsChanged`` batch gating).
    ``_local_host`` / ``_scope_view`` are stubs whose ``_model.refresh`` is the
    model-level ``MountDataTreeModel.refresh`` that the bug spies on.
    """
    tree = MountDataTree()
    tree.set_host_project_root(tmp_path)

    stub = SimpleNamespace(
        host_project_root=tmp_path,
        _current_scope=SCOPE,
        _loading=False,
        _mount_data_tree=tree,
        _local_host=SimpleNamespace(
            refresh=MagicMock(),
            _model=SimpleNamespace(refresh=MagicMock()),
        ),
        _scope_view=SimpleNamespace(
            refresh=MagicMock(),
            _model=SimpleNamespace(refresh=MagicMock()),
        ),
        _update_config_viewer=MagicMock(),
        statusBar=MagicMock(),
        dev_mode=True,
    )
    stub.config_manager = ConfigManager(stub)  # type: ignore[arg-type]
    stub.file_ops_handler = FileOperationsHandler(stub)  # type: ignore[arg-type]
    return stub


def _make_config(host_project_root: Path, pushed: set[Path]) -> ScopeDockerConfig:
    """A bare ScopeDockerConfig with just the fields tree.load_config reads."""
    return ScopeDockerConfig(
        mount_specs=[],
        pushed_files=set(pushed),
        container_files=set(),
        scope_name=SCOPE,
        host_project_root=host_project_root,
        mirrored=True,
        siblings=[],
        extensions=[],
        show_hidden=False,
    )


def test_drain_marked_push_does_not_reset_models(app, host_file, tmp_path):
    """End-to-end: drain → reload_current_scope(data_only=True) preserves trees.

    Assertions follow the plan:

      * Model-level ``refresh`` is the ``beginResetModel`` wrapper. Spying here
        catches both direct view-level ``refresh()`` and the indirect path
        ``mountSpecsChanged → ScopeView.refresh → model.refresh()`` — proving
        the batch gating absorbed the structural signal.
      * ``stateChanged`` fires exactly once (manual emit at the tail of
        ``reload_current_scope(data_only=True)``) so the cheap repaint runs.
      * ``mountSpecsChanged`` fires zero times: the load_config emit is
        deferred by ``begin_batch``, then suppressed by ``end_batch(emit=False)``.
    """
    state_emits: list[None] = []
    mount_specs_emits: list[None] = []
    app._mount_data_tree.stateChanged.connect(lambda: state_emits.append(None))
    app._mount_data_tree.mountSpecsChanged.connect(
        lambda: mount_specs_emits.append(None),
    )

    fake_config = _make_config(tmp_path, pushed={host_file})

    def fake_drain(hpr, scope, **kw):
        # The real drain writes pushed_files to disk; here we just return success.
        return OpResult(success=True, message="Drained 1 file(s)")

    with patch("IgnoreScope.gui.file_ops_ui.QProgressDialog"), \
         patch(
             "IgnoreScope.gui.file_ops_ui.drain_marked_push",
             side_effect=fake_drain,
         ), \
         patch(
             "IgnoreScope.gui.config_manager.load_config",
             return_value=fake_config,
         ):
        result = app.file_ops_handler.drain_marked_push_now()

    assert result.success

    # No model-level resets in either tree (the bug).
    app._local_host._model.refresh.assert_not_called()
    app._scope_view._model.refresh.assert_not_called()
    # And no view-level refresh wrappers either — proves we took the
    # data_only branch, not the structural one.
    app._local_host.refresh.assert_not_called()
    app._scope_view.refresh.assert_not_called()

    # Cheap repaint chain fired exactly once.
    assert len(state_emits) == 1, (
        f"expected one stateChanged emit (manual tail); got {len(state_emits)}"
    )
    # Structural signal absorbed by batch gating.
    assert mount_specs_emits == [], (
        f"mountSpecsChanged must not fire on data_only reload; got "
        f"{len(mount_specs_emits)} emit(s)"
    )

    # Sanity: the promoted pushed entry actually landed in the tree.
    assert host_file in app._mount_data_tree._pushed_files


def test_reload_current_scope_default_path_still_resets(app, tmp_path):
    """Non-drain callers must keep the structural reset behaviour.

    The fix is scoped to the drain path. Anything that mutates mount specs
    (open project, switch scope, add/remove sibling, lifecycle post-op,
    extension deploy) still goes through the view-level refresh().
    """
    fake_config = _make_config(tmp_path, pushed=set())
    with patch(
        "IgnoreScope.gui.config_manager.load_config",
        return_value=fake_config,
    ):
        app.config_manager.reload_current_scope()  # default data_only=False

    app._local_host.refresh.assert_called_once()
    app._scope_view.refresh.assert_called_once()
    app._update_config_viewer.assert_called_once()
