from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QPixmap, QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QFrame,
    QCheckBox,
    QGroupBox,
)

from photoscanner.db import PhotoDB
from photoscanner.utils import get_image_metadata, merge_image_metadata


class ImageItem(QFrame):
    selected = Signal(str)

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.path = path
        self.setFrameShape(QFrame.Shape.Box)
        self.setLineWidth(1)
        self._is_selected = False
        
        self._update_style()

        layout = QVBoxLayout()
        
        # Image
        self._lbl_img = QLabel()
        self._lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_img.setFixedSize(300, 300)
        self._lbl_img.setStyleSheet("background-color: #eee;")
        
        # Load thumbnail and get dims
        dims_text = "Unknown size"
        if os.path.exists(self.path):
            pix = QPixmap(self.path)
            if not pix.isNull():
                dims_text = f"{pix.width()} x {pix.height()}"
                pix = pix.scaled(
                    self._lbl_img.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._lbl_img.setPixmap(pix)
            else:
                self._lbl_img.setText("Invalid Image")
        else:
            self._lbl_img.setText("File not found")
        
        # Metadata
        p = Path(path)
        name = p.name
        ext = p.suffix.lower()
        parent_dir = str(p.parent)
        
        # Extra metadata
        meta = get_image_metadata(path)
        # Use defaults if keys missing (though utils now sets them mostly)
        device_info = meta.get("Device", "<MISSING>")
        gps_info = meta.get("GPS", "<MISSING>")
        date_info = meta.get("Date", "<MISSING>")

        # Labels
        lbl_name = QLabel(f"<b>{name}</b>")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_name.setWordWrap(True)

        lbl_dims = QLabel(dims_text)
        lbl_dims.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        
        meta_text = f"Ext: {ext}"
        meta_text += f"<br>Date: {date_info}"
        
        # Helper to format timestamps
        import datetime
        def fmt_ts(ts):
            return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')

        try:
            stat = p.stat()
            meta_text += f"<br>Created: {fmt_ts(stat.st_ctime)}"
            meta_text += f"<br>Modified: {fmt_ts(stat.st_mtime)}"
        except OSError:
            meta_text += f"<br>Created: <MISSING>"
            meta_text += f"<br>Modified: <MISSING>"

        meta_text += f"<br>Cam: {device_info}"
        meta_text += f"<br>GPS: {gps_info}"

        lbl_meta = QLabel(meta_text)
        lbl_meta.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_meta.setWordWrap(True)

        lbl_path = QLabel(parent_dir)
        lbl_path.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lbl_path.setWordWrap(True)
        lbl_path.setStyleSheet("color: #666; font-size: 10px;")

        layout.addWidget(self._lbl_img)
        layout.addWidget(lbl_name)
        layout.addWidget(lbl_dims)
        layout.addWidget(lbl_meta)
        layout.addWidget(lbl_path)
        layout.addStretch()
        
        self.setLayout(layout)

    def mousePressEvent(self, event):
        self.selected.emit(self.path)
        super().mousePressEvent(event)

    def set_selected(self, selected: bool):
        self._is_selected = selected
        self._update_style()

    def _update_style(self):
        if self._is_selected:
            # Green border as requested
            self.setStyleSheet("ImageItem { border: 4px solid #28a745; background-color: #e6ffec; }")
        else:
            self.setStyleSheet("ImageItem { border: 1px solid #ccc; background-color: transparent; }")


class ResolveDuplicatesDialog(QDialog):
    def __init__(self, db_path: Path, groups: list[list[str]] = None, start_index: int = 0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resolve Duplicates")
        self.resize(1200, 800)
        
        self._db_path = db_path
        # If groups is None, we use dynamic SQL mode (SHA256 only for now)
        self._groups = groups if groups is not None else []
        self._dynamic_mode = (groups is None)
        self._current_index = start_index
        
        self._selected_path: str | None = None
        self._items: list[ImageItem] = []

        # Main layout
        layout = QVBoxLayout()
        
        # --- Auto Selection Settings ---
        settings_group = QGroupBox("Auto-Select Criteria")
        settings_layout = QHBoxLayout()
        
        self.chk_older = QCheckBox("Prefer Older (Creation Date)")
        self.chk_larger = QCheckBox("Prefer Larger (Resolution/Size)")
        self.chk_deeper = QCheckBox("Prefer Deeper (Folder Depth)")
        
        # Load persisted settings
        self._settings = QSettings("PhotoScanner", "App")
        self.chk_older.setChecked(self._settings.value("auto_pref_older", False, type=bool))
        self.chk_larger.setChecked(self._settings.value("auto_pref_larger", False, type=bool))
        self.chk_deeper.setChecked(self._settings.value("auto_pref_deeper", False, type=bool))
        
        self.chk_older.stateChanged.connect(self._on_criteria_changed)
        self.chk_larger.stateChanged.connect(self._on_criteria_changed)
        self.chk_deeper.stateChanged.connect(self._on_criteria_changed)
        
        settings_layout.addWidget(self.chk_older)
        settings_layout.addWidget(self.chk_larger)
        settings_layout.addWidget(self.chk_deeper)
        settings_layout.addStretch()
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        # -------------------------------
        
        # Header / Navigation
        nav_layout = QHBoxLayout()
        self._btn_prev = QPushButton("<< Previous Group")
        self._lbl_group_info = QLabel()
        self._lbl_group_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_group_info.setStyleSheet("font-weight: bold; font-size: 14px;")
        self._btn_next = QPushButton("Next Group >>")
        
        nav_layout.addWidget(self._btn_prev)
        nav_layout.addStretch()
        nav_layout.addWidget(self._lbl_group_info)
        nav_layout.addStretch()
        nav_layout.addWidget(self._btn_next)
        layout.addLayout(nav_layout)


        # Instructions
        layout.addWidget(QLabel("Click on the image you want to KEEP. The others will be deleted."))

        # Scroll area for images
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._container = QWidget()
        self._grid = QHBoxLayout()
        self._grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._container.setLayout(self._grid)
        self._scroll.setWidget(self._container)
        layout.addWidget(self._scroll)

        # Action Buttons
        btn_layout = QHBoxLayout()
        self._btn_delete = QPushButton("Delete Others")
        self._btn_delete.setEnabled(False)
        self._btn_delete.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 8px;")
        
        self._btn_ignore = QPushButton("Ignore (Remove from DB)")
        self._btn_ignore.setToolTip("Removes these records from the database so they don't show as duplicates, but keeps files on disk.")
        
        self._btn_cancel = QPushButton("Close")
        
        btn_layout.addWidget(self._btn_ignore)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_delete)
        btn_layout.addWidget(self._btn_cancel)
        
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Connections
        self._btn_prev.clicked.connect(self._on_prev)
        self._btn_next.clicked.connect(self._on_next)
        self._btn_delete.clicked.connect(self._on_delete)
        self._btn_ignore.clicked.connect(self._on_ignore)
        self._btn_cancel.clicked.connect(self.accept) # Close acts as accept to refresh parent

        self._load_group()

    def _load_group(self):
        # Clear existing
        while self._grid.count():
            child = self._grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._items.clear()
        self._selected_path = None
        self._btn_delete.setEnabled(False)

        # Update Nav
        total = len(self._groups)
        if total == 0:
            self._lbl_group_info.setText("No duplicates found")
            self._btn_prev.setEnabled(False)
            self._btn_next.setEnabled(False)
            self._btn_ignore.setEnabled(False)
            return

        # Clamp index
        if self._current_index < 0: self._current_index = 0
        if self._current_index >= total: self._current_index = total - 1

        self._lbl_group_info.setText(f"Group {self._current_index + 1} of {total}")
        self._btn_prev.setEnabled(self._current_index > 0)
        self._btn_next.setEnabled(self._current_index < total - 1)
        self._btn_ignore.setEnabled(True)

        # Load images
        paths = self._groups[self._current_index]
        for p in paths:
            item = ImageItem(p)
            item.selected.connect(self._on_item_selected)
            self._grid.addWidget(item)
            self._items.append(item)


    def keyPressEvent(self, event: QKeyEvent):
        # Override to setup shortcut for Delete (minus key)
        if event.key() == Qt.Key_Minus:
            if self._btn_delete.isEnabled():
                self._on_delete()
                return
        super().keyPressEvent(event)

    def _on_criteria_changed(self):
        self._settings.setValue("auto_pref_older", self.chk_older.isChecked())
        self._settings.setValue("auto_pref_larger", self.chk_larger.isChecked())
        self._settings.setValue("auto_pref_deeper", self.chk_deeper.isChecked())
        self._run_auto_select()

    def _run_auto_select(self):
        """Logic for auto-selecting an image based on criteria."""
        if self._dynamic_mode:
            group = self._current_group_cache
        else:
            if self._current_index >= len(self._groups):
                return
            group = self._groups[self._current_index]
            
        if not group:
            return

        # Gather file stats
        candidates = []
        for path_str in group:
            p = Path(path_str)
            try:
                stat = p.stat()
                candidates.append({
                    "path": path_str,
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "depth": len(p.parts)
                })
            except OSError:
                continue
        
        if not candidates:
            return

        scores = {c['path']: 0 for c in candidates}
        active_criteria = 0
        
        # 1. Prefer Older (min mtime)
        if self.chk_older.isChecked():
            active_criteria += 1
            min_mtime = min(c['mtime'] for c in candidates)
            # Find those within 1 second of min (float precision)
            winners = [c for c in candidates if abs(c['mtime'] - min_mtime) < 1.0]
            for w in winners:
                scores[w['path']] += 1

        # 2. Prefer Larger (max size)
        if self.chk_larger.isChecked():
            active_criteria += 1
            max_size = max(c['size'] for c in candidates)
            winners = [c for c in candidates if c['size'] == max_size]
            for w in winners:
                scores[w['path']] += 1

        # 3. Prefer Deeper (max depth)
        if self.chk_deeper.isChecked():
            active_criteria += 1
            max_depth = max(c['depth'] for c in candidates)
            winners = [c for c in candidates if c['depth'] == max_depth]
            for w in winners:
                scores[w['path']] += 1

        if active_criteria == 0:
            return

        # Determine winner
        max_score = max(scores.values())
        if max_score == 0:
            self._select_none()
            return
            
        best = [k for k, v in scores.items() if v == max_score]
        
        if len(best) == 1:
            self._select_path(best[0])
        else:
            self._select_none()

    def _select_none(self):
        self._selected_path = None
        for item in self._items:
            item.set_selected(False)
        self._btn_delete.setEnabled(False)

    def _select_path(self, path: str):
        self._selected_path = path
        for item in self._items:
            item.set_selected(item.path == path)
        self._btn_delete.setEnabled(True)

    def _load_group(self):
        # Clear existing
        while self._grid.count():
            child = self._grid.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._items.clear()
        self._selected_path = None
        self._btn_delete.setEnabled(False)

        current_group = []

        if self._dynamic_mode:
            # Fetch from DB
            db = PhotoDB(self._db_path)
            # Offset is basically "which group are we viewing". 
            # If we delete a group, the NEXT group shifts into this offset.
            # So offset usually stays at 0 or moves if we Skip ("Next").
            # But the UI "next" increments _current_index.
            groups = db.get_duplicate_groups_sha256(limit=1, offset=self._current_index)
            db.close()
            
            if groups:
                # Convert ImageRecord to paths
                current_group = [r.path for r in groups[0]]
                self._current_group_cache = current_group # Helper for delete
                
                # We don't know total in dynamic mode easily without Count query. 
                # Let's say "Duplicate Group #X"
                self._lbl_group_info.setText(f"Duplicate Group #{self._current_index + 1} ({len(current_group)} images)")
            else:
                self._current_group_cache = []
                self._lbl_group_info.setText("No duplicates found (at this offset)")
        
        else:
            # Update Nav
            total = len(self._groups)
            if total == 0:
                self._lbl_group_info.setText("No duplicates found")
                self._btn_prev.setEnabled(False)
                self._btn_next.setEnabled(False)
                self._btn_ignore.setEnabled(False)
                return

            # Clamp index
            if self._current_index < 0: self._current_index = 0
            if self._current_index >= total: self._current_index = total - 1
            
            current_group = self._groups[self._current_index]
            self._lbl_group_info.setText(f"Group {self._current_index + 1} of {total} ({len(current_group)} images)")

        # Common rendering
        if not current_group:
             self._btn_delete.setEnabled(False)
             return
             
        for path in current_group:
            item = ImageItem(path)
            item.selected.connect(self._on_item_selected)
            self._grid.addWidget(item)
            self._items.append(item)
            
        # Try auto-select
        self._run_auto_select()

    def _on_prev(self):
        if self._current_index > 0:
            self._current_index -= 1
            self._load_group()

    def _on_next(self):
        if self._current_index < len(self._groups) - 1:
            self._current_index += 1
            self._load_group()

    def _on_item_selected(self, path: str):
        self._select_path(path)

    def _remove_current_group_from_list(self):
        if not self._dynamic_mode:
            del self._groups[self._current_index]
            # Index stays same unless it was the last one
            if self._current_index >= len(self._groups):
                self._current_index = len(self._groups) - 1
        else:
            # In dynamic mode, the group is gone from DB (removed), 
            # so the "next" group at the SAME offset is now the new group.
            # We don't advance index.
            pass
            
        self._load_group()

    def _on_delete(self):
        if not self._selected_path:
            return

        # Handle dynamic vs static group
        if self._dynamic_mode:
            # In dynamic, _groups only holds the CURRENT group temporarily?
            # Or we fetch it and put it in _groups[0]?
            # Let's say _load_group puts it in self._current_group_cache
            paths = self._current_group_cache
        else:
            paths = self._groups[self._current_index]

        to_delete = [p for p in paths if p != self._selected_path]
        
        # --- Resolution Safety Check ---
        # "If one of the images has a higher resolution, then it cannot be deleted."
        try:
            # Get dimensions of the kept image
            sel_pix = QPixmap(self._selected_path)
            sel_area = sel_pix.width() * sel_pix.height()
            
            for p in to_delete:
                 if not os.path.exists(p): 
                     continue
                 cand_pix = QPixmap(p)
                 cand_area = cand_pix.width() * cand_pix.height()
                 
                 # Using a small buffer for "strictly higher" effectively
                 if cand_area > sel_area:
                     msg = "You cannot delete an image with higher resolution than the one you are keeping.\n\n"
                     msg += f"Kept Image: {sel_pix.width()} x {sel_pix.height()}\n"
                     msg += f"Candidate to delete: {Path(p).name} ({cand_pix.width()} x {cand_pix.height()})\n\n"
                     msg += "Please select the higher resolution image to keep."
                     QMessageBox.critical(self, "Deletion Blocked", msg)
                     return

        except Exception as e:
            # If we fail to read dimensions (corrupt file?), safeguard or warn?
            # We'll log error but allow proceed if we can't determine, or block?
            # Safer to block if unsure?
            print(f"Safety constraint check failed: {e}")
            pass
        # -------------------------------
        
        # Check confirmation setting
        from PySide6.QtCore import QSettings
        settings = QSettings("PhotoScanner", "App")
        confirm = settings.value("confirm_delete", True, type=bool)
        
        if confirm:
            msg = f"Are you sure you want to delete {len(to_delete)} file(s)?\n\n" + "\n".join([Path(p).name for p in to_delete])
            if QMessageBox.question(self, "Confirm Delete", msg) != QMessageBox.StandardButton.Yes:
                return

        # 1. Merge Metadata
        merge_image_metadata(to_delete, self._selected_path)

        # 2. Delete File & Records
        db = PhotoDB(self._db_path)
        deleted_count = 0
        errors = []
        
        for p in to_delete:
            try:
                if os.path.exists(p):
                    os.remove(p)
                db.delete_image(p)
                deleted_count += 1
            except Exception as e:
                errors.append(f"{Path(p).name}: {e}")
        
        db.commit()
        db.close()

        if errors:
            QMessageBox.warning(self, "Delete Errors", "\n".join(errors))
        
        if deleted_count > 0:
            self._remove_current_group_from_list()

    def _on_ignore(self):
        # "In which case, it will be removed from the database too."
        if self._dynamic_mode:
            paths = self._current_group_cache
        else:
            paths = self._groups[self._current_index]
        
        msg = "This will remove these image records from the database (files will remain). Continue?"
        if QMessageBox.question(self, "Confirm Ignore", msg) != QMessageBox.StandardButton.Yes:
            return

        db = PhotoDB(self._db_path)
        for p in paths:
            db.delete_image(p)
        db.commit()
        db.close()

        self._remove_current_group_from_list()
