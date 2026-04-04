"""Container pattern list widget — mount selector + ordered pattern list.

Embeds in ContainerRootPanel. Displays and manages gitignore-style
mask/unmask patterns for the selected MountSpecPath.

Ported from: E:/SANS/SansMachinatia/_workbench/archive/IgnoreScope/panels/pattern_list.py
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QLabel,
    QMenu,
    QInputDialog,
    QAbstractItemView,
)

from ..core.case_conflict import get_conflicting_indices
from ..core.pattern_conflict import get_ineffective_exception_indices

if TYPE_CHECKING:
    from ..core.mount_spec_path import MountSpecPath
    from .mount_data_tree import MountDataTree


class ContainerPatternListWidget(QWidget):
    """Mount selector + ordered pattern list.

    Shows patterns for the selected MountSpecPath. Supports:
    - Mount selector dropdown (populated from MountDataTree)
    - Pattern list with drag-to-reorder
    - RMB context menu (remove, add deny/exception)
    - Case conflict and ordering conflict warnings

    Undo/redo is handled by ConfigManager via tree.aboutToMutate signal.

    Signals:
        patternChanged: Emitted when patterns are modified (triggers tree recompute)
    """

    patternChanged = pyqtSignal()

    def __init__(self, tree: MountDataTree, parent: QWidget | None = None):
        super().__init__(parent)
        self._tree = tree
        self._current_spec: MountSpecPath | None = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # Mount selector
        selector_layout = QHBoxLayout()
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_label = QLabel("Mount:")
        selector_label.setObjectName("patternMountLabel")
        self._mount_combo = QComboBox()
        self._mount_combo.setObjectName("patternMountCombo")
        selector_layout.addWidget(selector_label)
        selector_layout.addWidget(self._mount_combo, stretch=1)
        layout.addLayout(selector_layout)

        # Pattern list
        self._list_widget = QListWidget()
        self._list_widget.setObjectName("patternListWidget")
        self._list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        layout.addWidget(self._list_widget, stretch=1)

        # Toolbar: undo/redo + status
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setObjectName("patternAddBtn")
        self._add_btn.setFixedWidth(50)

        self._status_label = QLabel("")
        self._status_label.setObjectName("patternStatusLabel")

        toolbar.addWidget(self._status_label, stretch=1)
        toolbar.addWidget(self._add_btn)
        layout.addLayout(toolbar)

    def _connect_signals(self) -> None:
        self._mount_combo.currentIndexChanged.connect(self._on_mount_changed)
        self._list_widget.customContextMenuRequested.connect(self._show_context_menu)
        # rowsMoved may not exist on all Qt models; use layoutChanged as fallback
        model = self._list_widget.model()
        if hasattr(model, 'rowsMoved'):
            model.rowsMoved.connect(self._on_rows_moved)
        self._add_btn.clicked.connect(self._add_pattern_dialog)
        self._list_widget.installEventFilter(self)

    # --- Mount Selector ---

    def refresh_mounts(self) -> None:
        """Rebuild mount selector from tree's mount_specs."""
        from pathlib import Path as _Path

        self._mount_combo.blockSignals(True)
        prev_root = (
            self._current_spec.mount_root if self._current_spec else None
        )

        self._mount_combo.clear()

        # Read mount_specs directly from tree
        host_root = getattr(self._tree, '_host_project_root', None) or _Path()
        specs = list(self._tree._mount_specs)

        # Compute container-side labels
        from ..core.hierarchy import to_container_path
        container_root = getattr(self._tree, '_container_root', '') or ''
        host_container_root = host_root.parent if host_root.parts else None

        # Derive container_root if not set (new scope, no config saved yet)
        if not container_root and host_container_root:
            container_root = f"/{host_container_root.name}"

        restore_idx = 0
        for i, ms in enumerate(specs):
            if container_root and host_container_root:
                label = to_container_path(ms.mount_root, container_root, host_container_root)
            else:
                label = str(ms.mount_root)
            self._mount_combo.addItem(label, ms)
            if prev_root and ms.mount_root == prev_root:
                restore_idx = i

        self._mount_combo.blockSignals(False)

        if self._mount_combo.count() > 0:
            self._mount_combo.setCurrentIndex(restore_idx)
            self._on_mount_changed(restore_idx)
        else:
            # No mounts — clear everything
            self._current_spec = None
            self._refresh_list()

    def select_mount(self, mount_root) -> None:
        """Select a specific mount in the dropdown (e.g., from tree click)."""
        for i in range(self._mount_combo.count()):
            ms = self._mount_combo.itemData(i)
            if ms and ms.mount_root == mount_root:
                self._mount_combo.setCurrentIndex(i)
                return

    def _on_mount_changed(self, index: int) -> None:
        ms = self._mount_combo.itemData(index) if index >= 0 else None
        self._current_spec = ms
        self._refresh_list()

    # --- Pattern List Display ---

    def _refresh_list(self) -> None:
        """Rebuild list from current mount_spec's patterns."""
        self._list_widget.blockSignals(True)
        self._list_widget.clear()

        if self._current_spec:
            if not self._current_spec.patterns:
                placeholder = QListWidgetItem("No Masked Files")
                placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
                self._list_widget.addItem(placeholder)
            else:
                # Get conflict indices for visual warnings
                warning_indices = get_conflicting_indices(self._current_spec.patterns)
                ineffective_indices = get_ineffective_exception_indices(
                    self._current_spec.patterns
                )

                for i, pattern in enumerate(self._current_spec.patterns):
                    item = QListWidgetItem(pattern)
                    if i in warning_indices:
                        item.setToolTip("Case conflict with another pattern")
                    if i in ineffective_indices:
                        item.setToolTip("Exception may be overridden by later deny pattern")
                    self._list_widget.addItem(item)

        self._list_widget.blockSignals(False)
        self._update_status()

    def _update_status(self) -> None:
        if not self._current_spec:
            self._status_label.setText("No mount selected")
            return
        count = len(self._current_spec.patterns)
        self._status_label.setText(f"{count} pattern{'s' if count != 1 else ''}")

    # --- Pattern Operations ---

    def _add_pattern(self, pattern: str, index: int | None = None) -> bool:
        """Add pattern to current mount_spec."""
        if not self._current_spec:
            return False
        self._tree.aboutToMutate.emit()
        if not self._current_spec.add_pattern(pattern, index):
            return False
        self._refresh_list()
        self.patternChanged.emit()
        return True

    def _remove_pattern(self, pattern: str) -> bool:
        """Remove pattern from current mount_spec."""
        if not self._current_spec:
            return False
        self._tree.aboutToMutate.emit()
        if not self._current_spec.remove_pattern(pattern):
            return False
        self._refresh_list()
        self.patternChanged.emit()
        return True

    def _move_pattern(self, from_idx: int, to_idx: int) -> bool:
        """Move pattern position."""
        if not self._current_spec:
            return False
        self._tree.aboutToMutate.emit()
        if not self._current_spec.move_pattern(from_idx, to_idx):
            return False
        self._refresh_list()
        self.patternChanged.emit()
        return True

    # --- Drag-to-Reorder ---

    def _on_rows_moved(self, *_args) -> None:
        """Handle QListWidget internal move completion."""
        if not self._current_spec:
            return
        new_patterns = []
        for i in range(self._list_widget.count()):
            item = self._list_widget.item(i)
            if item:
                new_patterns.append(item.text())
        if new_patterns != self._current_spec.patterns:
            self._tree.aboutToMutate.emit()
            self._current_spec.patterns[:] = new_patterns
            self._current_spec._invalidate_cache()
            self._refresh_list()
            self.patternChanged.emit()

    # --- Context Menu ---

    def _show_context_menu(self, pos) -> None:
        item = self._list_widget.itemAt(pos)
        if not item:
            return
        pattern = item.text()

        menu = QMenu(self)
        menu.addAction(f"  {pattern}").setEnabled(False)
        menu.addSeparator()

        remove_action = menu.addAction("Remove")
        remove_action.triggered.connect(lambda: self._remove_pattern(pattern))

        edit_action = menu.addAction("Edit...")
        edit_action.triggered.connect(lambda: self._edit_pattern_dialog(pattern))

        menu.exec(self._list_widget.mapToGlobal(pos))

    def _add_pattern_dialog(self) -> None:
        text, ok = QInputDialog.getText(
            self, "Add Pattern", "Gitignore pattern:",
        )
        if ok and text.strip():
            self._add_pattern(text.strip())

    def _edit_pattern_dialog(self, old_pattern: str) -> None:
        text, ok = QInputDialog.getText(
            self, "Edit Pattern", "Gitignore pattern:", text=old_pattern,
        )
        if ok and text.strip() and text.strip() != old_pattern:
            if not self._current_spec:
                return
            try:
                idx = self._current_spec.patterns.index(old_pattern)
            except ValueError:
                return
            self._current_spec.remove_pattern(old_pattern)
            self._current_spec.add_pattern(text.strip(), idx)
            self._current_spec._invalidate_cache()
            self._refresh_list()
            self.patternChanged.emit()

    # --- Event Filter (Delete key) ---

    def eventFilter(self, obj, event):
        if obj is self._list_widget:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.KeyPress:
                if event.key() == Qt.Key.Key_Delete:
                    current = self._list_widget.currentItem()
                    if current:
                        self._remove_pattern(current.text())
                    return True
        return super().eventFilter(obj, event)

    # --- Public API ---

    def refresh(self) -> None:
        """Full refresh — rebuild mounts and patterns."""
        self.refresh_mounts()

    def add_deny_for_folder(self, pattern: str) -> None:
        """Add a deny pattern (called from tree context menu)."""
        self._add_pattern(pattern)

    def add_exception_for_folder(self, pattern: str) -> None:
        """Add an exception pattern (called from tree context menu)."""
        self._add_pattern(pattern)
