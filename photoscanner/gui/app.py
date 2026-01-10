from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from photoscanner.gui.main_window import MainWindow


def run() -> None:
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
