from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QCheckBox,
)

from photoscanner.utils import get_torch_devices
from photoscanner.gui.gpu_setup_dialog import GPUSetupDialog


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(500, 250)

        self._settings = QSettings("PhotoScanner", "App")
        
        geometry = self._settings.value("settings_dlg_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        layout = QVBoxLayout()
        form = QFormLayout()

        # Device selection row
        device_layout = QHBoxLayout()
        self._device_combo = QComboBox()
        devices = get_torch_devices()
        self._device_combo.addItems(devices)
        
        # Default to CUDA if available and setting not set
        if not self._settings.contains("ai_device") and "cuda" in devices:
            current_device = "cuda"
        else:
            current_device = self._settings.value("ai_device", "cpu")

        if current_device in devices:
            self._device_combo.setCurrentText(str(current_device))
        else:
            self._device_combo.setCurrentText("cpu")

        device_layout.addWidget(self._device_combo)
        
        self.gpu_btn = QPushButton("Manage GPU...")
        self.gpu_btn.clicked.connect(self.open_gpu_setup)
        device_layout.addWidget(self.gpu_btn)
        
        form.addRow(QLabel("AI Inference Device:"), device_layout)
        
        # Confirmation settings
        self._chk_confirm_delete = QCheckBox("Confirm before deleting duplicates")
        # Default to True
        confirm_enabled = self._settings.value("confirm_delete", True, type=bool)
        self._chk_confirm_delete.setChecked(confirm_enabled)
        form.addRow(QLabel("Confirm Deletions:"), self._chk_confirm_delete)

        layout.addLayout(form)
        
        # Diagnostic info
        info_text = []
        try:
            import torch
            info_text.append(f"PyTorch version: {torch.__version__}")
            if torch.cuda.is_available():
                info_text.append(f"CUDA available: Yes ({torch.version.cuda})")
                info_text.append(f"GPU: {torch.cuda.get_device_name(0)}")
            else:
                info_text.append("CUDA available: No")
                info_text.append("To enable GPU, install PyTorch with CUDA support.")
        except ImportError as e:
            info_text.append("PyTorch not installed or failed to load.")
            info_text.append(f"Error: {e}")
            info_text.append("Install 'sentence-transformers' and 'torch' to enable AI features.")

        layout.addWidget(QLabel("<br>".join(info_text)))
        layout.addWidget(QLabel("<small>Note: GPU (cuda) requires NVIDIA drivers and PyTorch with CUDA support.</small>"))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setLayout(layout)

    def open_gpu_setup(self):
        dlg = GPUSetupDialog(self)
        dlg.exec()
        # Refresh device list after dialog closes (in case of successful install + restart)
        # Note: A real reload requires app restart, so we just prompt user in dialog.
        
    def closeEvent(self, event):
        self._settings.setValue("settings_dlg_geometry", self.saveGeometry())
        super().closeEvent(event)

    def accept(self) -> None:
        self._settings.setValue("ai_device", self._device_combo.currentText())
        self._settings.setValue("confirm_delete", self._chk_confirm_delete.isChecked())
        super().accept()
