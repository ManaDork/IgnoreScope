"""New scope creation dialog.

NewScopeDialog: Custom dialog for creating a new container scope.
"""

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLineEdit,
    QCheckBox,
    QDialogButtonBox,
)


class NewScopeDialog(QDialog):
    """Dialog for creating a new container scope.

    Provides:
    - Scope name input (default: "dev")
    - Checkbox for mirrored parent directory creation
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._name_input: QLineEdit
        self._mirror_checkbox: QCheckBox

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog layout."""
        self.setWindowTitle("New Scope")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        # Scope name input  # TODO Make Nice Name (2-28-2026)
        self._name_input = QLineEdit("dev")
        self._name_input.selectAll()
        layout.addRow("Scope name:", self._name_input)

        # Mirror directories checkbox
        self._mirror_checkbox = QCheckBox("Create mirrored parent directories (mkdir -p)")
        self._mirror_checkbox.setChecked(True)
        layout.addRow(self._mirror_checkbox)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    @property
    def scope_name(self) -> str:
        """Get the entered scope name, sanitized for Docker + filesystem safety."""
        from ..docker.names import sanitize_scope_name
        return sanitize_scope_name(self._name_input.text().strip())

    @property
    def mirror_dirs(self) -> bool:
        """Get whether mirrored parent directories should be created."""
        return self._mirror_checkbox.isChecked()
