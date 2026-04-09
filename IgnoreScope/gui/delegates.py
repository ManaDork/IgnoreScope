"""Gradient-based delegates for state-driven row painting.

GradientDelegate: Base that clears backgroundBrush so manually-painted
gradients survive super().paint(). Provides shared text-styling and
gradient-painting methods; subclasses override _get_row_width().

TreeStyleDelegate: Full tree delegate parameterized by TreeDisplayConfig.
Reads NodeStateRole from the model, resolves visual state via truth tables,
paints 4-layer rows (gradient -> overlay -> text -> symbols).

HistoryDelegate: List delegate parameterized by ListDisplayConfig.
Reads HistoryStateRole from the model, resolves visual state,
paints 3-layer rows (gradient -> overlay -> text). No symbols.

Config-parameterized delegates — state derivation via resolve_tree_state().
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QModelIndex, QEvent, QRect
from PyQt6.QtGui import QBrush, QColor, QPalette, QFontMetrics
from PyQt6.QtWidgets import QStyledItemDelegate, QStyle, QStyleOptionViewItem

from .display_config import TreeDisplayConfig, ColumnDef, resolve_tree_state
from .list_display_config import ListDisplayConfig
from .mount_data_model import NodeStateRole, NodeIsFileRole
from .session_history import HistoryStateRole
from .style_engine import StyleGui, StateStyleClass


# ── GradientDelegate (Base) ──────────────────────────────────────

class GradientDelegate(QStyledItemDelegate):
    """Base delegate that preserves gradient backgrounds.

    QStyledItemDelegate.paint() calls initStyleOption() internally, which
    reads BackgroundRole and sets backgroundBrush. The style then paints
    that solid brush OVER any gradient we painted in paint().

    Fix: Clear backgroundBrush after the base populates it.

    Shared methods (DRY — extracted from Tree + History):
      _apply_text_style  — text color + bold + italic
      _paint_gradient    — full-row gradient via _get_row_width() hook
      _get_row_width     — base returns option.rect.width(); override in subclass
    """

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> None:
        """Clear background brush so paint()'s gradient isn't overwritten."""
        super().initStyleOption(option, index)
        option.backgroundBrush = QBrush()  # CRITICAL — see MEMORY.md

    def _apply_text_style(
        self, option: QStyleOptionViewItem,
        style: StateStyleClass, config,
    ) -> None:
        """Apply text color + font weight + italic from resolved style."""
        text_hex = config.resolve_text_color(style.font)
        text_color = QColor(text_hex)
        option.palette.setColor(QPalette.ColorRole.Text, text_color)
        option.palette.setColor(
            QPalette.ColorRole.HighlightedText, text_color,
        )
        if style.font.weight == "bold":
            option.font.setBold(True)
        if style.font.italic:
            option.font.setItalic(True)

    def _paint_state_overlay(
        self, painter, option: QStyleOptionViewItem,
    ) -> None:
        """Paint hover/selected overlay on top of gradient background."""
        sg = StyleGui.instance()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, sg.selection_color())
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, sg.hover_color())

    def _get_row_width(self, option: QStyleOptionViewItem) -> int:
        """Return full-row width for gradient painting. Override in subclasses."""
        return option.rect.width()

    def _paint_gradient(
        self,
        painter,
        option: QStyleOptionViewItem,
        style: StateStyleClass,
    ) -> None:
        """Paint full-row gradient from StateStyleClass.

        Uses _get_row_width() hook for view-appropriate width.
        Subclasses must set self._config with a color_vars attribute.
        Applies row_gradient_opacity from theme.json to allow widget
        gradient bleed-through.
        """
        gradient_class = style.gradient
        total_width = self._get_row_width(option)

        sg = StyleGui.instance()
        qt_gradient = sg.build_gradient(
            gradient_class, self._config.color_vars, total_width,
            x_offset=option.rect.x(),
        )
        row_opacity = sg.row_gradient_opacity
        if row_opacity < 255:
            painter.setOpacity(row_opacity / 255.0)
        painter.fillRect(option.rect, QBrush(qt_gradient))
        if row_opacity < 255:
            painter.setOpacity(1.0)


# ── TreeStyleDelegate ────────────────────────────────────────────

class TreeStyleDelegate(GradientDelegate):
    """Config-driven delegate for tree views.

    Constructor takes a TreeDisplayConfig — no TreeContext enum.
    Resolves visual state from NodeStateRole via resolve_tree_state(),
    then looks up StateStyleClass in config.state_styles.

    Paint order (4-layer):
      1. Gradient background (full-row width via header().length())
      2. Selection/hover overlay (semi-transparent)
      3. Text via super().paint() (backgroundBrush cleared)
      4. Custom symbols on columns with symbol_type
    """

    def __init__(
        self, config: TreeDisplayConfig, parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._sg = StyleGui.instance()
        self._click_toggle_enabled: bool = False

    @property
    def click_toggle_enabled(self) -> bool:
        return self._click_toggle_enabled

    @click_toggle_enabled.setter
    def click_toggle_enabled(self, value: bool) -> None:
        self._click_toggle_enabled = value

    # ── Style Resolution ──────────────────────────────────────────

    def _resolve_style(self, index: QModelIndex) -> StateStyleClass | None:
        """Resolve NodeStateRole -> state name -> StateStyleClass."""
        if not index.isValid():
            return None
        node_state = index.data(NodeStateRole)
        if node_state is None:
            return None
        is_file = index.data(NodeIsFileRole)
        if is_file is None:
            return None
        state_name = resolve_tree_state(node_state, not is_file)
        return self._config.state_styles.get(state_name)

    # ── initStyleOption ───────────────────────────────────────────

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> None:
        """Set text color + font + suppress native checkbox."""
        super().initStyleOption(option, index)  # GradientDelegate clears brush
        if not index.isValid():
            return

        style = getattr(self, '_cached_style', None)
        if style is None:
            style = self._resolve_style(index)
        if style is not None:
            self._apply_text_style(option, style, self._config)

        # Suppress native checkbox for custom symbol columns
        col_idx = index.column()
        if col_idx < len(self._config.columns):
            col_def = self._config.columns[col_idx]
            if col_def.symbol_type is not None:
                option.features &= (
                    ~QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
                )

        # Our 4-layer paint system owns all visual state.
        # Strip selection/hover so PE_PanelItemViewItem doesn't paint
        # competing highlights (disabled palette uses grayed-out color
        # that overwrites Layer 2's uniform overlay).
        # Restore State_Enabled so text uses normal palette group
        # (_apply_text_style already sets correct colors for all states).
        option.state &= ~(
            QStyle.StateFlag.State_Selected
            | QStyle.StateFlag.State_MouseOver
        )
        option.state |= QStyle.StateFlag.State_Enabled

    # ── Row Width ─────────────────────────────────────────────────

    def _get_row_width(self, option: QStyleOptionViewItem) -> int:
        """Full-row width via header for multi-column trees."""
        view = option.widget
        if view is not None and hasattr(view, "header"):
            return view.header().length()
        return option.rect.width()

    # ── paint ─────────────────────────────────────────────────────

    def paint(self, painter, option, index) -> None:
        """4-layer paint: gradient -> overlay -> text -> symbols."""
        if not index.isValid():
            return
        style = self._resolve_style(index)

        # Resolve column def once (used for focus suppression + symbol painting)
        col_def = None
        col_idx = index.column()
        if col_idx < len(self._config.columns):
            col_def = self._config.columns[col_idx]

        # Suppress focus rect on all columns — prevents white square artifact
        option.state &= ~QStyle.StateFlag.State_HasFocus

        # Layer 1: gradient background
        if style is not None and style.gradient is not None:
            self._paint_gradient(painter, option, style)

        # Layer 2: selection overlay
        # NOTE: isSelected() gates on ItemIsEnabled (Qt internal).
        # Column 0 (name) is always enabled — use it as row-selection proxy.
        view = option.widget
        if view is not None and hasattr(view, 'selectionModel'):
            sel_model = view.selectionModel()
            if sel_model is not None and sel_model.isSelected(
                index.siblingAtColumn(0),
            ):
                painter.fillRect(option.rect, self._sg.selection_color())

        # Layer 3: text (backgroundBrush cleared via MRO -> GradientDelegate)
        # Cache resolved style so initStyleOption() skips redundant resolution
        self._cached_style = style
        super().paint(painter, option, index)
        self._cached_style = None

        # Layer 4: custom symbols
        if col_def is not None and col_def.symbol_type is not None:
            self._paint_symbol(painter, option, index, col_def)

    # ── Symbols ───────────────────────────────────────────────────

    def _paint_symbol(
        self,
        painter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
        col_def: ColumnDef,
    ) -> None:
        """Dispatch symbol painting based on column symbol_type."""
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)

        if col_def.symbol_type == "check":
            if check_state == Qt.CheckState.Checked:
                color = QColor(self._sg.palette_color("frost_3"))
                self._draw_centered_symbol(
                    painter, option.rect, color, "\u2713", font_bump=1,
                )

        elif col_def.symbol_type == "pushed_status":
            is_file = index.data(NodeIsFileRole)
            if not is_file:
                return  # folders: blank cell
            if check_state == Qt.CheckState.Checked:
                color = QColor(self._sg.palette_color("frost_3"))
                self._draw_centered_symbol(
                    painter, option.rect, color, "\u25CF",
                )
            else:
                color = QColor(self._sg.palette_color("snow_storm_0"))
                self._draw_centered_symbol(
                    painter, option.rect, color, "\u25CB",
                )

    @staticmethod
    def _draw_centered_symbol(
        painter, rect: QRect, color: QColor, symbol: str, font_bump: int = 0,
    ) -> None:
        """Draw a centered unicode symbol in the given rect."""
        painter.save()
        painter.setPen(color)
        font = painter.font()
        if font_bump:
            font.setPointSize(font.pointSize() + font_bump)
            painter.setFont(font)
        fm = QFontMetrics(font)
        text_w = fm.horizontalAdvance(symbol)
        text_h = fm.ascent()
        x = rect.x() + (rect.width() - text_w) // 2
        y = rect.y() + (rect.height() + text_h) // 2 - fm.descent()
        painter.drawText(x, y, symbol)
        painter.restore()

    # ── Editor Event (Click Toggle) ───────────────────────────────

    def editorEvent(self, event, model, option, index) -> bool:
        """Handle clicks on suppressed checkbox columns.

        Multi-select aware: if the clicked item is part of an active
        selection, the toggled state is applied to ALL selected items
        in the same column via model.begin_batch()/end_batch().
        """
        if not index.isValid():
            return False
        col_idx = index.column()
        if col_idx >= len(self._config.columns):
            return super().editorEvent(event, model, option, index)

        col_def = self._config.columns[col_idx]
        if not col_def.checkable:
            return super().editorEvent(event, model, option, index)

        # pushed_status is file-only — block folder clicks
        if col_def.symbol_type == "pushed_status":
            is_file = index.data(NodeIsFileRole)
            if not is_file:
                return False

        # Block left-click press on checkable columns — prevents native visual artifact
        if (event.type() == QEvent.Type.MouseButtonPress
                and event.button() == Qt.MouseButton.LeftButton):
            return True

        if (event.type() != QEvent.Type.MouseButtonRelease
                or event.button() != Qt.MouseButton.LeftButton):
            return super().editorEvent(event, model, option, index)

        # Gate: consume click without toggling when disabled
        if not self._click_toggle_enabled:
            return True

        flags = model.flags(index)
        if not (flags & Qt.ItemFlag.ItemIsUserCheckable):
            return False
        if not (flags & Qt.ItemFlag.ItemIsEnabled):
            return False

        current = index.data(Qt.ItemDataRole.CheckStateRole)
        if current is None:
            return False

        new_state = (
            Qt.CheckState.Unchecked
            if current == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

        # ── Multi-select batch toggle ─────────────────────────
        view = self.parent()
        if view is not None and hasattr(view, "selectionModel"):
            selected = view.selectionModel().selectedRows(col_idx)
            if len(selected) > 1 and any(
                idx.row() == index.row()
                and idx.parent() == index.parent()
                for idx in selected
            ):
                model.begin_batch()
                try:
                    for sel_idx in selected:
                        sel_flags = model.flags(sel_idx)
                        if not (sel_flags & Qt.ItemFlag.ItemIsUserCheckable):
                            continue
                        if not (sel_flags & Qt.ItemFlag.ItemIsEnabled):
                            continue
                        model.setData(
                            sel_idx, new_state,
                            Qt.ItemDataRole.CheckStateRole,
                        )
                finally:
                    model.end_batch()
                return True

        return model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)


# ── HistoryDelegate ──────────────────────────────────────────────

class HistoryDelegate(GradientDelegate):
    """Config-driven delegate for the Session History list panel.

    Constructor takes a ListDisplayConfig — not TreeDisplayConfig.
    Resolves visual state from HistoryStateRole via state_styles lookup.

    Paint order (3-layer — no symbols):
      1. Gradient background (full widget width)
      2. Selection/hover overlay (semi-transparent)
      3. Text via super().paint() (backgroundBrush cleared)
    """

    def __init__(
        self, config: ListDisplayConfig, parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._sg = StyleGui.instance()

    # ── Style Resolution ──────────────────────────────────────────

    def _resolve_style(self, index: QModelIndex) -> StateStyleClass | None:
        """Resolve HistoryStateRole -> state name -> StateStyleClass."""
        if not index.isValid():
            return None
        state_name = index.data(HistoryStateRole)
        if state_name is None:
            return None
        return self._config.state_styles.get(state_name)

    # ── initStyleOption ───────────────────────────────────────────

    def initStyleOption(
        self, option: QStyleOptionViewItem, index: QModelIndex,
    ) -> None:
        """Set text color + font from resolved style."""
        super().initStyleOption(option, index)  # GradientDelegate clears brush
        if not index.isValid():
            return

        style = self._resolve_style(index)
        if style is not None:
            self._apply_text_style(option, style, self._config)

    # ── Row Width ─────────────────────────────────────────────────

    def _get_row_width(self, option: QStyleOptionViewItem) -> int:
        """Full widget width for single-column list views."""
        view = option.widget
        if view is not None:
            return view.viewport().width()
        return option.rect.width()

    # ── paint ─────────────────────────────────────────────────────

    def paint(self, painter, option, index) -> None:
        """3-layer paint: gradient -> overlay -> text."""
        if not index.isValid():
            return
        style = self._resolve_style(index)

        # Layer 1: gradient background
        if style is not None and style.gradient is not None:
            self._paint_gradient(painter, option, style)

        # Layer 2: selection/hover overlay
        self._paint_state_overlay(painter, option)

        # Layer 3: text (backgroundBrush cleared via MRO -> GradientDelegate)
        super().paint(painter, option, index)
