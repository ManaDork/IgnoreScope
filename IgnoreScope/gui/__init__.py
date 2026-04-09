"""PyQt GUI for IgnoreScope configuration.

Provides a graphical interface for configuring Docker container visibility
with QDockWidget-based docking layout. See GUI_LAYOUT_SPECS.md
for the target layout specification.

Previous experimental implementation archived to gui/_archive/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def run_app(
    host_project_root: Optional[Path] = None,
    *,
    dev_mode: bool = False,
) -> int:
    """Launch the GUI. Minimal stub for Layout Phase visual testing."""
    import sys
    import faulthandler
    faulthandler.enable()

    from PyQt6.QtWidgets import QApplication, QStyleFactory
    from .app import IgnoreScopeApp

    from .icons import build_app_icon

    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setWindowIcon(build_app_icon())
    window = IgnoreScopeApp(
        host_project_root=host_project_root,
        dev_mode=dev_mode,
    )
    window.show()
    return app.exec()
