"""Icon loader for IgnoreScope branding assets.

Builds a multi-resolution QIcon from the PNGs in gui/icons/.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtGui import QIcon, QPixmap

_ICONS_DIR = Path(__file__).resolve().parent / "icons"

_SIZES = [16, 32, 48, 64, 128, 256, 512]


def build_app_icon() -> QIcon:
    """Build QIcon with QPixmap entries for each available resolution."""
    icon = QIcon()
    for size in _SIZES:
        if size == 512:
            filename = "ignore_scope_square_512.png"
        else:
            filename = f"ignore_scope_square_512_{size}.png"
        path = _ICONS_DIR / filename
        if path.exists():
            icon.addPixmap(QPixmap(str(path)))
    return icon
