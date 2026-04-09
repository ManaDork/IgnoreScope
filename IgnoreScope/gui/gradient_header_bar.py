"""GradientHeaderBar — reusable gradient-painted header widget.

Base widget for all header bars in the app (title bar, dock titles,
config panel header). Inherits GradientBackgroundMixin for theme-driven
gradient painting.

Phase 1 of Fusion Custom Title Bar feature.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QSize
from PyQt6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QLabel,
    QPushButton,
)
from PyQt6.QtGui import QIcon, QMouseEvent, QContextMenuEvent

from .style_engine import GradientBackgroundMixin

BASE_HEADER_HEIGHT = 36


class GradientHeaderBar(GradientBackgroundMixin, QWidget):
    """Header bar with gradient background, label, and action buttons.

    Args:
        gradient_name: Key from theme.json ``"gradients"`` section.
        label_text: Text displayed on the left side of the header.
        parent: Optional parent widget.
    """

    clicked = pyqtSignal()
    contextMenuRequested = pyqtSignal(QPoint)

    def __init__(
        self,
        gradient_name: str,
        label_text: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._gradient_name = gradient_name

        # --- Layout ---
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.setSpacing(4)

        # Left-aligned label
        self._label = QLabel(label_text, self)
        self._label.setStyleSheet("background: transparent;")
        layout.addWidget(self._label)

        layout.addStretch()

        # Right-aligned action button area
        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(2)
        layout.addLayout(self._actions_layout)

    # ------------------------------------------------------------------
    # Height
    # ------------------------------------------------------------------

    @property
    def header_height(self) -> int:
        """DPI-scaled header height in pixels."""
        scale = self.logicalDpiX() / 96.0
        return round(BASE_HEADER_HEIGHT * scale)

    def sizeHint(self):
        return QSize(super().sizeHint().width(), self.header_height)

    def minimumSizeHint(self):
        return QSize(0, self.header_height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setFixedHeight(self.header_height)

    # ------------------------------------------------------------------
    # Label
    # ------------------------------------------------------------------

    def set_label_text(self, text: str):
        """Update the header label text."""
        self._label.setText(text)

    def label_text(self) -> str:
        """Return current label text."""
        return self._label.text()

    # ------------------------------------------------------------------
    # Action buttons
    # ------------------------------------------------------------------

    def add_action_button(
        self,
        icon: QIcon,
        tooltip: str,
        callback,
    ) -> QPushButton:
        """Add a button to the right-aligned action area.

        Args:
            icon: Button icon.
            tooltip: Tooltip text.
            callback: Slot connected to the button's ``clicked`` signal.

        Returns:
            The created QPushButton.
        """
        btn = QPushButton(self)
        btn.setIcon(icon)
        btn.setToolTip(tooltip)
        btn.setFlat(True)
        btn.setFixedSize(self.header_height - 4, self.header_height - 4)
        btn.setStyleSheet("background: transparent; border: none;")
        btn.clicked.connect(callback)
        self._actions_layout.addWidget(btn)
        return btn

    # ------------------------------------------------------------------
    # Events → signals
    # ------------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent):
        self.contextMenuRequested.emit(event.globalPos())
        super().contextMenuEvent(event)
