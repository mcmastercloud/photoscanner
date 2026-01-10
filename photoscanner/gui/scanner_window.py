from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, QSettings
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from photoscanner.ai import Detector, EmbeddingModel, get_ai_availability
from photoscanner.db import PhotoDB
from photoscanner.gui.settings_dialog import SettingsDialog
from photoscanner.gui.resolve_dialog import ResolveDuplicatesDialog
from photoscanner.scanner import (
    ScanOptions,
    group_duplicates_by_phash,
    group_duplicates_by_sha256,
    scan_folders,
)


@dataclass(frozen=True)
class DuplicateRow:
    group_id: str
    best_path: str
    other_path: str
    method: str


import threading

class ScanWorker(QObject):
    progress = Signal(int, int, int, str)
    finished = Signal(int, int, int)
    error = Signal(str)

    def __init__(self, db_path: Path, folders: list[Path], options: ScanOptions, device: str, running_event: threading.Event):
        super().__init__()
        self._db_path = db_path
        self._folders = folders
        self._options = options
        self._device = device
        self._running_event = running_event

    def run(self) -> None:
        try:
            db = PhotoDB(self._db_path)
            embedding_model = None
            detector = None

            if self._options.compute_embeddings:
                embedding_model = EmbeddingModel(device=self._device)
            if self._options.detect_faces or self._options.detect_objects:
                detector = Detector()

            def cb(scanned: int, indexed: int, skipped: int, path: str) -> None:
                self.progress.emit(scanned, indexed, skipped, path)

            res = scan_folders(
                db,
                folders=self._folders,
                options=self._options,
                embedding_model=embedding_model,
                detector=detector,
                progress_cb=cb,
                running_event=self._running_event,
            )
            db.close()
            self.finished.emit(res.scanned, res.indexed, res.skipped)
        except Exception as e:
            self.error.emit(str(e))


class ScannerWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Photo Scanner - Find Duplicates")
        self.resize(900, 600)  # Default size

        self._db_path = Path.cwd() / "photoscanner.sqlite"
        self._running_event = threading.Event()
        self._running_event.set() # Start in running state

        self._settings = QSettings("PhotoScanner", "ScannerWindow")
        # Geometry restoration deferred to showEvent to handle MDI parent

        self._folders_list = QListWidget()
        self._folders_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        self._add_btn = QPushButton("Add folder")
        self._remove_btn = QPushButton("Remove selected")
        self._clear_db_btn = QPushButton("Clear Database")
        self._settings_btn = QPushButton("Settings")
        self._scan_btn = QPushButton("Scan")
        self._resolve_btn = QPushButton("Resolve All")
        self._resolve_btn.setStyleSheet("background-color: #0078d4; color: white; font-weight: bold;")

        self._emb_cb = QCheckBox("Compute embeddings (optional)")
        self._faces_cb = QCheckBox("Face detection (optional)")
        self._objects_cb = QCheckBox("Object detection (optional)")

        self._phash_threshold = QSpinBox()
        self._phash_threshold.setMinimum(0)
        self._phash_threshold.setMaximum(32)
        self._phash_threshold.setValue(6)

        self._dupes_table = QTableWidget(0, 4)
        self._dupes_table.setHorizontalHeaderLabels(["Group", "Best", "Duplicate", "Method"])
        self._dupes_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._dupes_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._dupes_table.itemDoubleClicked.connect(self._on_resolve_duplicates)

        self._status = QLabel("Ready")

        buttons = QHBoxLayout()
        buttons.addWidget(self._add_btn)
        buttons.addWidget(self._remove_btn)
        buttons.addWidget(self._clear_db_btn)
        buttons.addWidget(self._settings_btn)
        buttons.addStretch(1)
        buttons.addWidget(QLabel("pHash threshold"))
        buttons.addWidget(self._phash_threshold)
        buttons.addStretch(1)
        buttons.addWidget(self._resolve_btn)
        buttons.addWidget(self._scan_btn)

        opts = QHBoxLayout()
        opts.addWidget(self._emb_cb)
        opts.addWidget(self._faces_cb)
        opts.addWidget(self._objects_cb)
        opts.addStretch(1)

        root = QVBoxLayout()
        root.addWidget(QLabel("Folders"))
        root.addWidget(self._folders_list)
        root.addLayout(buttons)
        root.addLayout(opts)
        root.addWidget(QLabel("Duplicates (best image chosen by score)") )
        root.addWidget(self._dupes_table)
        root.addWidget(self._status)

        self.setLayout(root)

        self._add_btn.clicked.connect(self._on_add)
        self._clear_db_btn.clicked.connect(self._on_clear_db)
        self._settings_btn.clicked.connect(self._on_settings)
        self._scan_btn.clicked.connect(self._on_scan)
        self._resolve_btn.clicked.connect(self._on_resolve_all)

        self._refresh_ai_availability()
        self._load_initial_state()

        self._thread: QThread | None = None

    def _load_initial_state(self) -> None:
        db = PhotoDB(self._db_path)
        
        # Load folders
        folders = db.get_folders()
        for f in folders:
            self._folders_list.addItem(f)
            
        # Load duplicates
        self._refresh_duplicates_view()
        db.close()

    def _refresh_duplicates_view(self) -> None:
        # We need to open a new connection or use the existing one if passed?
        # _load_initial_state opens a db connection but closes it after calling this.
        # But this method might be called from elsewhere.
        # Let's make it self-contained or pass db.
        # Since _load_initial_state calls it, let's assume it should open its own connection 
        # OR we change _load_initial_state to not close it yet.
        # But wait, _load_initial_state calls db.close() AFTER this.
        # So if we open a new one here, it's fine (sqlite allows multiple connections).
        # However, to be safe and efficient, let's just open a new one.
        
        db = PhotoDB(self._db_path)
        records = list(db.iter_images())
        db.close()

        rows: list[DuplicateRow] = []

        sha_groups = group_duplicates_by_sha256(records)
        for g in sha_groups:
            best = g[0].path
            for other in g[1:]:
                rows.append(DuplicateRow(group_id=g[0].sha256[:12], best_path=best, other_path=other.path, method="sha256"))

        ph_groups = group_duplicates_by_phash(records, threshold=int(self._phash_threshold.value()))
        for idx, g in enumerate(ph_groups, start=1):
            best = g[0].path
            gid = f"phash-{idx}"
            for other in g[1:]:
                rows.append(DuplicateRow(group_id=gid, best_path=best, other_path=other.path, method="phash"))

        self._render_duplicates(rows)
        self._status.setText(f"Loaded {len(records)} images. Found {len(rows)} duplicate pairs.")

    def _on_clear_db(self) -> None:
        if QMessageBox.question(self, "Clear Database", "Are you sure you want to delete ALL records and folders from the database? This cannot be undone.") == QMessageBox.StandardButton.Yes:
            db = PhotoDB(self._db_path)
            db.clear_all()
            db.close()
            self._folders_list.clear()
            self._dupes_table.setRowCount(0)
            self._status.setText("Database cleared.")

    def _on_add(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if folder:
            # Check if already exists
            exists = False
            for i in range(self._folders_list.count()):
                if self._folders_list.item(i).text() == folder:
                    exists = True
                    break
            
            if not exists:
                self._folders_list.addItem(folder)
                db = PhotoDB(self._db_path)
                db.add_folder(folder)
                db.close()

    def _on_remove(self) -> None:
        db = PhotoDB(self._db_path)
        for item in self._folders_list.selectedItems():
            row = self._folders_list.row(item)
            path = item.text()
            self._folders_list.takeItem(row)
            db.remove_folder(path)
        db.commit()
        db.close()

    def _refresh_ai_availability(self) -> None:
        avail = get_ai_availability()
        if not avail.embeddings:
            self._emb_cb.setChecked(False)
            self._emb_cb.setEnabled(False)
            self._emb_cb.setToolTip("Embeddings unavailable: install sentence-transformers")
        if not avail.detection:
            self._faces_cb.setChecked(False)
            self._objects_cb.setChecked(False)
            self._faces_cb.setEnabled(False)
            self._objects_cb.setEnabled(False)
            self._faces_cb.setToolTip("Detection unavailable: install mediapipe opencv-python numpy")
            self._objects_cb.setToolTip("Detection unavailable: install mediapipe opencv-python numpy")


    def _on_settings(self) -> None:
        dlg = SettingsDialog(self)
        dlg.exec()

    def _get_folders(self) -> list[Path]:
        return [Path(self._folders_list.item(i).text()) for i in range(self._folders_list.count())]

    def _on_scan(self) -> None:
        folders = self._get_folders()
        if not folders:
            QMessageBox.information(self, "Photo Scanner", "Add at least one folder.")
            return

        options = ScanOptions(
            compute_embeddings=self._emb_cb.isChecked(),
            detect_faces=self._faces_cb.isChecked(),
            detect_objects=self._objects_cb.isChecked(),
        )

        self._scan_btn.setEnabled(False)
        self._status.setText("Scanning...")
        self._dupes_table.setRowCount(0)

        settings = QSettings("PhotoScanner", "App")
        device = settings.value("ai_device", "cpu")

        self._thread = QThread()
        self._worker = ScanWorker(self._db_path, folders, options, str(device), self._running_event)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)

        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        self._thread.start()

    def closeEvent(self, event):
        # Save geometry of the MDI subwindow (parent)
        p = self.parentWidget()
        if p:
            self._settings.setValue("mdi_geometry", p.saveGeometry())
        super().closeEvent(event)

    def showEvent(self, event):
        if not hasattr(self, "_geometry_restored"):
            geometry = self._settings.value("mdi_geometry")
            p = self.parentWidget()
            if geometry and p:
                p.restoreGeometry(geometry)
            self._geometry_restored = True
        super().showEvent(event)

    def _on_progress(self, scanned: int, indexed: int, skipped: int, path: str) -> None:
        self._status.setText(f"Scanned {scanned} | Indexed {indexed} | Skipped {skipped} | {path}")

    def _on_error(self, msg: str) -> None:
        self._scan_btn.setEnabled(True)
        QMessageBox.critical(self, "Scan failed", msg)
        self._status.setText("Error")

    def _on_finished(self, scanned: int, indexed: int, skipped: int) -> None:
        self._scan_btn.setEnabled(True)
        self._status.setText(f"Done. Scanned {scanned}, indexed {indexed}, skipped {skipped}. Finding duplicates...")

        db = PhotoDB(self._db_path)
        records = list(db.iter_images())
        db.close()

        rows: list[DuplicateRow] = []

        sha_groups = group_duplicates_by_sha256(records)
        for g in sha_groups:
            best = g[0].path
            for other in g[1:]:
                rows.append(DuplicateRow(group_id=g[0].sha256[:12], best_path=best, other_path=other.path, method="sha256"))

        ph_groups = group_duplicates_by_phash(records, threshold=int(self._phash_threshold.value()))
        for idx, g in enumerate(ph_groups, start=1):
            best = g[0].path
            gid = f"phash-{idx}"
            for other in g[1:]:
                rows.append(DuplicateRow(group_id=gid, best_path=best, other_path=other.path, method="phash"))

        self._render_duplicates(rows)
        self._status.setText(f"Done. Images: {len(records)} | Duplicate rows: {len(rows)}")

    def _render_duplicates(self, rows: list[DuplicateRow]) -> None:
        self._dupes_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._dupes_table.setItem(i, 0, QTableWidgetItem(r.group_id))
            self._dupes_table.setItem(i, 1, QTableWidgetItem(r.best_path))
            self._dupes_table.setItem(i, 2, QTableWidgetItem(r.other_path))
            self._dupes_table.setItem(i, 3, QTableWidgetItem(r.method))
        self._dupes_table.resizeColumnsToContents()

    def pause_scanner(self) -> None:
        """Pause the background scanning thread safely."""
        self._running_event.clear()

    def resume_scanner(self) -> None:
        """Resume the background scanning thread."""
        self._running_event.set()

    def _on_resolve_duplicates(self, item: QTableWidgetItem) -> None:
        self._on_resolve_all()  # Just go to dynamic mode now

    def _on_resolve_all(self):
        # Pause scanner during resolve dialog
        self.pause_scanner()
        try:
            # Open Dynamic Resolve Dialog
            # Note: Signature might vary based on recent changes. 
            # If it takes just (db_path, parent) and does dynamic query:
            # Resolving arguments: ResolveDuplicatesDialog(db_path, groups=None, start_index=0, parent=self)
            # Based on previous read_file.
            from photoscanner.gui.resolve_dialog import ResolveDuplicatesDialog
            dlg = ResolveDuplicatesDialog(self._db_path, groups=None, start_index=0, parent=self)
            dlg.exec()
        finally:
            self.resume_scanner()
        
        # Refresh t