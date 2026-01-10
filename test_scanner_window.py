import sys
from PySide6.QtWidgets import QApplication
from photoscanner.gui.scanner_window import ScannerWindow

app = QApplication(sys.argv)
try:
    w = ScannerWindow()
    print("ScannerWindow instantiated successfully")
except Exception as e:
    print(f"Error instantiating ScannerWindow: {e}")
