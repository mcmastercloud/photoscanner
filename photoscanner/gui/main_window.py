from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMdiArea,
    QMdiSubWindow,
    QMessageBox,
)

from photoscanner.gui.label_images_window import LabelImagesWindow
from photoscanner.gui.scanner_window import ScannerWindow
from photoscanner.gui.settings_dialog import SettingsDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Scanner MDI")
        self.resize(1024, 768)

        self._mdi_area = QMdiArea()
        self._mdi_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._mdi_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setCentralWidget(self._mdi_area)

        self._create_actions()
        self._create_menus()
        
        # Restore window state
        from PySide6.QtCore import QSettings
        settings = QSettings("PhotoScanner", "App")
        geometry = settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        from PySide6.QtCore import QSettings
        settings = QSettings("PhotoScanner", "App")
        settings.setValue("window_geometry", self.saveGeometry())
        super().closeEvent(event)

    def _create_actions(self) -> None:
        # File actions
        self._exit_act = QAction("E&xit", self)
        self._exit_act.setShortcut("Ctrl+Q")
        self._exit_act.setStatusTip("Exit the application")
        self._exit_act.triggered.connect(QApplication.instance().quit)

        # Edit actions
        self._pref_act = QAction("&Preferences", self)
        self._pref_act.setStatusTip("Edit settings")
        self._pref_act.triggered.connect(self._open_settings)

        # Tools actions
        self._scanner_act = QAction("&Scanner", self)
        self._scanner_act.setStatusTip("Open Scanner Window")
        self._scanner_act.triggered.connect(self._open_scanner)

        self._label_act = QAction("&Label Images", self)
        self._label_act.setStatusTip("Open Label Images Window")
        self._label_act.triggered.connect(self._open_label_images)

    def _create_menus(self) -> None:
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._exit_act)

        self._edit_menu = self.menuBar().addMenu("&Edit")
        self._edit_menu.addAction(self._pref_act)

        self._tools_menu = self.menuBar().addMenu("&Tools")
        self._tools_menu.addAction(self._scanner_act)
        self._tools_menu.addAction(self._label_act)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.exec()

    def _open_scanner(self) -> None:
        # Check if already open? MDI allows multiples usually.
        # But maybe we want check
        w = ScannerWindow()
        sub = self._mdi_area.addSubWindow(w)
        sub.resize(w.size())
        w.show()
        sub.show()

    def _open_label_images(self) -> None:
        try:
            # Pause scanner if running
            scanner_win = None
            for sub in self._mdi_area.subWindowList():
                if isinstance(sub.widget(), ScannerWindow):
                    scanner_win = sub.widget()
                    scanner_win.pause_scanner()
                    break

            w = LabelImagesWindow()
            
            # Resume scanner when label window is closed
            if scanner_win:
                w.destroyed.connect(scanner_win.resume_scanner)

            sub = self._mdi_area.addSubWindow(w)
            sub.resize(w.size())
            w.show()
            sub.show()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open Label Images Window:\n{e}")
            import traceback
            traceback.print_exc()
