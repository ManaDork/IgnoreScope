"""Container Root Panel — config header + collapsible JSON viewer.

Display-only panel showing a styled header frame ("Desktop Docker Scope Config")
and a collapsible read-only JSON preview. The header provides a right-click
context menu to open the config file location, and a left-click toggle to
expand/collapse the JSON viewer.

Data ownership: container_root lives on MountDataTree, not here.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal, Qt, QEvent
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QPlainTextEdit,
    QMenu,
    QSizePolicy,
)


class ContainerRootPanel(QWidget):
    """Header frame + collapsible JSON config viewer panel.

    Layout:
        QFrame (header_frame)          ← LMB toggle + RMB context menu
          └─ QLabel ("▼ Desktop Docker Scope Config")  ← mouse-transparent
        QPlainTextEdit (config_text_edit, read-only)   ← collapsible JSON preview

    Signals:
        openConfigLocationRequested: Emitted on RMB → "Open Config Location"
    """

    openConfigLocationRequested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("configPanel")
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget layout."""
        layout = QVBoxLayout(self)
        layout.setObjectName("config_panelLayout")
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(0)

        # ── Header frame ──
        self._header_frame = QFrame()
        self._header_frame.setObjectName("configHeaderFrame")
        self._header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(self._header_frame)
        header_layout.setObjectName("config_headerLayout")
        header_layout.setContentsMargins(6, 6, 6, 6)
        header_layout.setSpacing(6)

        self._header_label = QLabel("▼ Desktop Docker Scope Config")
        self._header_label.setObjectName("configHeaderLabel")
        self._header_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header_layout.addWidget(self._header_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        header_layout.addStretch()

        self._header_frame.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._header_frame.customContextMenuRequested.connect(self._show_header_context_menu)

        layout.addWidget(self._header_frame)
        self._header_frame.setCursor(Qt.CursorShape.PointingHandCursor)
        self._header_frame.installEventFilter(self)

        # ── Collapsible JSON viewer ──
        self._config_text_edit = QPlainTextEdit()
        self._config_text_edit.setReadOnly(True)
        self._config_text_edit.setObjectName("configViewerText")
        self._config_text_edit.setPlaceholderText("// No configuration loaded")
        layout.addWidget(self._config_text_edit, stretch=1)

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding,
        )

    # -- Config text property --

    @property
    def config_text(self) -> str:
        """Get the JSON preview text."""
        return self._config_text_edit.toPlainText()

    @config_text.setter
    def config_text(self, value: str) -> None:
        """Set the JSON preview text."""
        self._config_text_edit.setPlainText(value)

    # -- Collapse toggle --

    def _toggle_config_viewer(self) -> None:
        """Toggle the JSON viewer visibility.

        Sets maximumHeight to header-only when collapsed so the
        QSplitter reclaims space for the tree above.
        """
        visible = not self._config_text_edit.isVisible()
        self._config_text_edit.setVisible(visible)
        arrow = "▼" if visible else "▶"
        self._header_label.setText(f"{arrow} Desktop Docker Scope Config")
        if visible:
            self.setMaximumHeight(16777215)  # QWIDGETSIZE_MAX — unconstrained
        else:
            fm = self._header_label.fontMetrics()
            content_h = fm.height()
            hdr_m = self._header_frame.layout().contentsMargins()
            panel_m = self.layout().contentsMargins()
            # CSS border (1px) isn't reported by frameWidth(); hard-code to match QSS
            css_border = 1
            self.setMaximumHeight(
                panel_m.top() + panel_m.bottom()
                + 2 * css_border
                + hdr_m.top() + hdr_m.bottom()
                + content_h
            )

    # -- Event filter (header frame click) --

    def eventFilter(self, obj, event):
        if obj is self._header_frame and event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_config_viewer()
                return True
        return super().eventFilter(obj, event)

    # -- Context menu --

    def _show_header_context_menu(self, pos) -> None:
        """Show RMB context menu on header label."""
        menu = QMenu(self)
        action = menu.addAction("Open Config Location")
        action.triggered.connect(self.openConfigLocationRequested.emit)
        menu.exec(self._header_frame.mapToGlobal(pos))

    def clear(self) -> None:
        """Reset to defaults."""
        self._config_text_edit.clear()