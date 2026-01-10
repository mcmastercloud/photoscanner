from __future__ import annotations

import sys
from PySide6.QtCore import QProcess, QByteArray
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QProgressBar,
    QMessageBox,
)

class GPUSetupDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("GPU Support Setup")
        self.resize(600, 400)

        layout = QVBoxLayout()
        
        self.info_label = QLabel(
            "Detecting environment...\n"
        )
        layout.addWidget(self.info_label)

        self.install_btn = QPushButton("Install NVIDIA CUDA Support (approx. 3GB)")
        self.install_btn.clicked.connect(self.start_installation)
        self.install_btn.setEnabled(False)
        layout.addWidget(self.install_btn)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0) # Indeterminate
        self.progress.hide()
        layout.addWidget(self.progress)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        layout.addWidget(self.close_btn)

        self.setLayout(layout)
        
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        self.check_status()

    def check_status(self):
        try:
            import torch
            version = torch.__version__
            cuda = torch.cuda.is_available()
            
            status = f"Python Executable: {sys.executable}\n"
            status += f"Current PyTorch Version: {version}\n"
            status += f"CUDA Available: {'Yes' if cuda else 'No'}\n"
            
            if cuda:
                status += "\nYour GPU is correctly detected."
                self.install_btn.setText("Reinstall CUDA Support")
            else:
                status += "\nGPU detection FAILED. You are likely using the CPU-only version of PyTorch."
            
            self.info_label.setText(status)
            self.install_btn.setEnabled(True)

        except ImportError:
            self.info_label.setText("PyTorch is not installed.")
            self.install_btn.setEnabled(True)

    def start_installation(self):
        confirm = QMessageBox.question(
            self, 
            "Confirm Installation", 
            "This will download and install PyTorch with CUDA support (~3GB).\n"
            "This process depends on your internet speed and may take several minutes.\n\n"
            "Do you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.install_btn.setEnabled(False)
        self.close_btn.setEnabled(False)
        self.progress.show()
        self.log_output.clear()
        self.log_output.append("Starting installation...\n")

        # Uninstall first to be safe? Or just force install.
        # Force install is safer 
        cmd = sys.executable
        args = [
            "-m", "pip", "install", 
            "torch==2.9.1+cu128", 
            "torchvision==0.24.1+cu128", 
            "--index-url", "https://download.pytorch.org/whl/cu128",
            "--force-reinstall"
        ]
        
        self.log_output.append(f"Running: {cmd} {' '.join(args)}\n")
        self.process.start(cmd, args)

    def handle_stdout(self):
        data = self.process.readAllStandardOutput()
        text = data.data().decode('utf-8', errors='ignore')
        self.log_output.moveCursor(self.log_output.textCursor().End)
        self.log_output.insertPlainText(text)
        self.log_output.ensureCursorVisible()

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        text = data.data().decode('utf-8', errors='ignore')
        self.log_output.moveCursor(self.log_output.textCursor().End)
        self.log_output.insertPlainText(text)
        self.log_output.ensureCursorVisible()

    def process_finished(self, exit_code, exit_status):
        self.progress.hide()
        self.close_btn.setEnabled(True)
        self.install_btn.setEnabled(True)
        
        if exit_code == 0:
            QMessageBox.information(self, "Success", "Installation completed!\nPlease RESTART the application to apply changes.")
            self.log_output.append("\nSUCCESS. Please restart the application.")
        else:
            QMessageBox.critical(self, "Error", f"Installation failed with exit code {exit_code}.")
            self.log_output.append("\nFAILED.")
