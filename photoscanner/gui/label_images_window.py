from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QSettings, QRectF, QTimer
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPen, QColor, QMouseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QSplitter,
    QTextEdit,
    QProgressBar,
    QScrollArea,
    QCheckBox,
)

from photoscanner.ai import EmbeddingModel, DEFAULT_LABELS, get_ai_availability, Detector
from photoscanner.db import PhotoDB, dumps_json
from photoscanner.scanner import IMAGE_EXTS


# Simple FlowLayout implementation for labels
from PySide6.QtWidgets import QLayout, QSizePolicy
class FlowLayout(QLayout):
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self.itemList = []

    def __del__(self):
        item = self.takeAt(0)
        while item:
            item = self.takeAt(0)

    def addItem(self, item):
        self.itemList.append(item)

    def count(self):
        return len(self.itemList)

    def itemAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self._do_layout(QRectF(0, 0, width, 0), True)
        return int(height)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self.itemList:
            wid = item.widget()
            space_x = spacing + wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
            space_y = spacing + wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)
            
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRectF(x, y, item.sizeHint().width(), item.sizeHint().height()).toRect())

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y()


class LabelTag(QWidget):
    removed = Signal(str) # label text
    clicked = Signal(str) # label text

    def __init__(self, text: str, is_existing: bool = False, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.text = text
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QHBoxLayout()
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)
        
        self.lbl = QLabel(text)
        self.lbl.setStyleSheet("color: white; font-weight: bold; font-size: 14px;")
        
        self.btn_close = QLabel("✕")
        self.btn_close.setStyleSheet("color: #ffcccc; font-weight: bold; font-size: 14px;")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout.addWidget(self.lbl)
        layout.addWidget(self.btn_close)
        self.setLayout(layout)
        
        bg_color = "#107c10" if is_existing else "#0078d4"
        hover_color = "#159e15" if is_existing else "#1084e0"
        
        self.setStyleSheet(f"""
            LabelTag {{
                background-color: {bg_color};
                border-radius: 16px;
            }}
            LabelTag:hover {{
                background-color: {hover_color};
            }}
        """)

    def mousePressEvent(self, event: QMouseEvent):
        # Check if clicked on X
        if self.btn_close.geometry().contains(event.pos()):
            self.removed.emit(self.text)
        else:
            self.clicked.emit(self.text)


class ImagePreview(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: #eee; border: 1px solid #ccc;")
        self.setFixedSize(250, 250)
        self._bbox: dict | None = None # {xmin, ymin, width, height} 0-1 relative
        self._all_bboxes: list[dict] = []
        self._show_all = False

    def set_bbox(self, bbox: dict | None):
        self._show_all = False
        self._bbox = bbox
        self.update()

    def set_all_bboxes(self, bboxes: list[dict]):
        self._all_bboxes = bboxes
        self._show_all = True
        self.update()
    
    def clear_all_mode(self):
        self._show_all = False
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if (self._bbox or self._show_all) and self.pixmap() and not self.pixmap().isNull():
            painter = QPainter(self)
            
            pm = self.pixmap()
            pm_w = pm.width()
            pm_h = pm.height()
            
            off_x = (self.width() - pm_w) / 2
            off_y = (self.height() - pm_h) / 2
            
            boxes_to_draw = []
            if self._show_all:
                for b in self._all_bboxes:
                    # Color differentiation?
                    boxes_to_draw.append((b, QColor("blue")))
                if self._bbox: # Highlight valid selection on top
                    boxes_to_draw.append((self._bbox, QColor("red")))
            else:
                if self._bbox:
                    boxes_to_draw.append((self._bbox, QColor("red")))

            for bbox, color in boxes_to_draw:
                painter.setPen(QPen(color, 2 if color.name() == "#0000ff" else 3))
                x = off_x + bbox["xmin"] * pm_w
                y = off_y + bbox["ymin"] * pm_h
                w = bbox["width"] * pm_w
                h = bbox["height"] * pm_h
                painter.drawRect(x, y, w, h)


class ThumbnailLoader(QThread):
    image_loaded = Signal(str, QIcon)  # path, icon
    finished = Signal()

    def __init__(self, folder: Path, icon_size: int = 128):
        super().__init__()
        self.folder = folder
        self.icon_size = icon_size
        self._stop = False

    def run(self):
        if not self.folder.exists():
            return
        
        # List all files first
        files = []
        try:
            for f in os.listdir(self.folder):
                p = self.folder / f
                if p.suffix.lower() in IMAGE_EXTS:
                    files.append(p)
        except Exception:
            pass

        for p in files:
            if self._stop:
                break
            
            pix = QPixmap(str(p))
            if not pix.isNull():
                pix = pix.scaled(
                    self.icon_size, self.icon_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self.image_loaded.emit(str(p), QIcon(pix))
        
        self.finished.emit()

    def stop(self):
        self._stop = True


class LabelingWorker(QThread):
    finished = Signal(list, str) # list of dicts, error_msg
    error = Signal(str)

    def __init__(self, path: Path, device: str):
        super().__init__()
        self.path = path
        self.device = device

    def run(self):
        try:
            import time
            settings = QSettings("PhotoScanner", "App")
            
            # Check for recent failure
            failure_ts = settings.value("ai_failure_timestamp", 0, type=float)
            if time.time() - failure_ts < 3600: # 60 minutes
                self.device = "cpu"
            
            detector = Detector()
            
            try:
                res = detector.analyze_file(self.path, faces=False, objects=True, device=self.device)
            except Exception as e:
                # Check if it's a CUDA/device error and we are not on CPU
                if self.device != "cpu":
                    print(f"AI Error on {self.device}: {e}. Falling back to CPU.")
                    # Log failure
                    settings.setValue("ai_failure_timestamp", time.time())
                    # Retry on CPU
                    self.device = "cpu"
                    res = detector.analyze_file(self.path, faces=False, objects=True, device="cpu")
                else:
                    raise e
            
            objects = res.get("objects", [])
            err = res.get("error", "")
            
            self.finished.emit(objects, err)
            
        except Exception as e:
            self.error.emit(str(e))


class XmpDisplayDialog(QDialog):
    def __init__(self, xmp_data: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("XMP Data")
        self.resize(600, 800)
        
        # Restore Geometry
        self._settings = QSettings("PhotoScanner", "XmpViewer")
        geom = self._settings.value("geometry")
        if geom:
            self.restoreGeometry(geom)

        layout = QVBoxLayout(self)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(xmp_data)
        self.text_edit.setReadOnly(True)
        self.text_edit.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        
        layout.addWidget(self.text_edit)
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def closeEvent(self, event):
        self._settings.setValue("geometry", self.saveGeometry())
        super().closeEvent(event)



class LabelImagesWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Label Images")
        self.resize(1000, 700)

        self._db_path = Path.cwd() / "photoscanner.sqlite"
        self._current_folder: Path | None = None
        self._current_image: Path | None = None
        self._loader: ThumbnailLoader | None = None
        self._labeler: LabelingWorker | None = None

        # Load settings
        self._settings = QSettings("PhotoScanner", "LabelImages")
        # Geometry restoration deferred to showEvent
        
        last_folder = self._settings.value("last_folder")
        
        # UI Components
        self._btn_select_folder = QPushButton("Select Folder")
        self._lbl_folder = QLabel("No folder selected")
        
        self._list_widget = QListWidget()
        self._list_widget.setViewMode(QListWidget.ViewMode.IconMode)
        self._list_widget.setIconSize(QSize(128, 128))
        self._list_widget.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list_widget.setSpacing(10)
        self._list_widget.setMovement(QListWidget.Movement.Static)

        # Metadata Panel
        self._meta_panel = QWidget()
        self._meta_layout = QVBoxLayout()
        self._meta_panel.setLayout(self._meta_layout)
        
        self._lbl_preview = ImagePreview()
        
        self._lbl_filename = QLabel("Select an image")
        self._lbl_filename.setWordWrap(True)
        self._lbl_filename.setStyleSheet("font-weight: bold;")
        
        self._lbl_info = QLabel()
        self._lbl_info.setWordWrap(True)
        
        self._lbl_date = QLabel()
        self._lbl_date.setWordWrap(True)
        
        self._lbl_geo = QLabel()
        self._lbl_geo.setWordWrap(True)
        self._lbl_geo.setOpenExternalLinks(True)
        
        # Labels container
        self._labels_container = QWidget()
        self._labels_layout = FlowLayout(self._labels_container)
        self._labels_scroll = QScrollArea()
        self._labels_scroll.setWidget(self._labels_container)
        self._labels_scroll.setWidgetResizable(True)
        self._labels_scroll.setMaximumHeight(150)
        
        self._btn_save_labels = QPushButton("Save Labels")
        self._btn_suggest = QPushButton("Suggest Labels (AI)")
        self._btn_view_xmp = QPushButton("View XMP")
        self._chk_show_all = QCheckBox("Show all boxes")
        
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setRange(0, 0) # Indeterminate

        self._meta_layout.addWidget(QLabel("Preview:"))
        self._meta_layout.addWidget(self._lbl_preview)
        self._meta_layout.addWidget(self._chk_show_all)
        self._meta_layout.addWidget(self._lbl_filename)
        self._meta_layout.addWidget(self._lbl_info)
        self._meta_layout.addWidget(self._lbl_date)
        self._meta_layout.addWidget(self._lbl_geo)
        self._meta_layout.addWidget(QLabel("Labels:"))
        self._meta_layout.addWidget(self._labels_scroll)
        self._meta_layout.addWidget(self._btn_save_labels)
        self._meta_layout.addWidget(self._btn_suggest)
        self._meta_layout.addWidget(self._btn_view_xmp)
        self._meta_layout.addWidget(self._progress)
        self._meta_layout.addStretch()
        
        self._current_labels: list[dict] = [] # {label, score, bbox}

        # Main Layout
        # main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Header
        header_widget = QWidget()
        header_widget.setFixedHeight(60)
        top_bar = QHBoxLayout(header_widget)
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.addWidget(self._btn_select_folder)
        top_bar.addWidget(self._lbl_folder)
        top_bar.addStretch()
        
        # Right panel fixed width
        self._meta_panel.setFixedWidth(300)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._list_widget)
        splitter.addWidget(self._meta_panel)
        # Make left side (index 0) take all available space
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setCollapsible(1, False)
        
        main_layout.addWidget(header_widget)
        main_layout.addWidget(splitter)
        
        # Notification Label
        self._lbl_notification = QLabel("")
        self._lbl_notification.setStyleSheet("QLabel { background-color: #333; color: white; padding: 5px; border-radius: 4px; }")
        self._lbl_notification.setVisible(False)
        self._lbl_notification.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._lbl_notification)
        
        self.setLayout(main_layout)

        # Connections
        self._btn_select_folder.clicked.connect(self._on_select_folder)
        self._list_widget.itemClicked.connect(self._on_item_clicked)
        self._btn_suggest.clicked.connect(self._on_suggest)
        self._btn_view_xmp.clicked.connect(self._on_view_xmp)
        self._btn_save_labels.clicked.connect(self._on_save)

        self._chk_show_all.toggled.connect(self._on_show_all_toggled)
        # Check AI
        avail = get_ai_availability()
        if not avail.embeddings:
            self._btn_suggest.setEnabled(False)
            self._btn_suggest.setToolTip(f"AI unavailable: {avail.embeddings_reason}")

        if last_folder and os.path.exists(last_folder):
            self._load_folder(last_folder)

    def closeEvent(self, event):
        # Save geometry of the MDI subwindow (parent)
        p = self.parentWidget()
        if p:
            self._settings.setValue("mdi_geometry", p.saveGeometry())
            
        if self._current_folder:
            self._settings.setValue("last_folder", str(self._current_folder))
        super().closeEvent(event)

    def showEvent(self, event):
        if not hasattr(self, "_geometry_restored"):
            geometry = self._settings.value("mdi_geometry")
            p = self.parentWidget()
            if geometry and p:
                p.restoreGeometry(geometry)
            self._geometry_restored = True
        super().showEvent(event)

    def _on_select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder")
        if not folder:
            return
        self._load_folder(folder)

    def _load_folder(self, folder: str):
        self._current_folder = Path(folder)
        self._lbl_folder.setText(folder)
        self._list_widget.clear()
        
        if self._loader:
            self._loader.stop()
            self._loader.wait()
        
        self._loader = ThumbnailLoader(self._current_folder)
        self._loader.image_loaded.connect(self._add_thumbnail)
        self._loader.start()

    def _add_thumbnail(self, path: str, icon: QIcon):
        item = QListWidgetItem(Path(path).name)
        item.setIcon(icon)
        item.setData(Qt.ItemDataRole.UserRole, path)
        self._list_widget.addItem(item)

    def _on_item_clicked(self, item: QListWidgetItem):
        path_str = item.data(Qt.ItemDataRole.UserRole)
        self._current_image = Path(path_str)
        
        # Load preview
        pix = QPixmap(path_str)
        if not pix.isNull():
            pix = pix.scaled(
                self._lbl_preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self._lbl_preview.setPixmap(pix)
            self._lbl_info.setText(f"{pix.width()} x {pix.height()} | {os.path.getsize(path_str) // 1024} KB")
        else:
            self._lbl_preview.setText("Invalid Image")
            self._lbl_info.setText("")

        self._lbl_filename.setText(self._current_image.name)
        
        # Extract Metadata (Date & GPS)
        date_str = "Unknown Date"
        geo_str = ""
        
        try:
            from PIL import Image, ExifTags
            with Image.open(self._current_image) as img:
                exif = img._getexif()
                if exif:
                    # Date
                    # 36867 is DateTimeOriginal, 306 is DateTime
                    dt = exif.get(36867) or exif.get(306)
                    if dt:
                        date_str = str(dt)
                    
                    # GPS
                    # 34853 is GPSInfo
                    gps_info = exif.get(34853)
                    if gps_info:
                        def convert_to_degrees(value):
                            d = float(value[0])
                            m = float(value[1])
                            s = float(value[2])
                            return d + (m / 60.0) + (s / 3600.0)

                        lat = None
                        lon = None
                        
                        if 2 in gps_info and 4 in gps_info:
                            lat = convert_to_degrees(gps_info[2])
                            lon = convert_to_degrees(gps_info[4])
                            
                            if gps_info.get(1) == 'S': lat = -lat
                            if gps_info.get(3) == 'W': lon = -lon
                            
                            url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
                            geo_str = f'<a href="{url}">Location: {lat:.4f}, {lon:.4f}</a>'

        except Exception as e:
            print(f"Metadata error: {e}")
            
        self._lbl_date.setText(f"Date: {date_str}")
        self._lbl_geo.setText(geo_str)

        # Load labels from XMP (including BBoxes from Iptc4xmpExt)
        self._current_labels = []
        try:
            self._current_labels = self._read_xmp_labels(self._current_image)
        except Exception as e:
            print(f"XMP read error: {e}")
        
        self._refresh_labels_ui()

    def _read_xmp_labels(self, path: Path) -> list[dict]:
        import pyexiv2 # type: ignore
        from xml.etree import ElementTree as ET
        from collections import defaultdict
        
        # Define Namespaces
        NS_MAP = {
            'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            'dc': "http://purl.org/dc/elements/1.1/",
            'mwg-rs': "http://www.metadataworkinggroup.com/schemas/regions/",
            'stArea': "http://ns.adobe.com/xmp/sType/Area#",
            'stDim': "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
            'stReg': "http://ns.adobe.com/xmp/sType/Region#",
            'Iptc4xmpExt': "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
        }

        # Register namespace globally before reading to prevent XMP Toolkit errors
        try:
            for prefix, uri in NS_MAP.items():
                pyexiv2.registerNs(uri, prefix)
        except Exception:
            pass

        final_list = []
        found_regions = defaultdict(list) # label -> list of bboxes
        
        with pyexiv2.Image(str(path)) as img:
            # 1. Read simple dc:subject
            try:
                xmp_dict = img.read_xmp()
            except Exception as e:
                print(f"pyexiv2 read_xmp warning: {e}")
                xmp_dict = {}

            subjects = set(xmp_dict.get("Xmp.dc.subject", []))

            # 2. Read Regions from raw XML
            try:
                raw_xml = img.read_raw_xmp()
                if raw_xml:
                    for prefix, uri in NS_MAP.items():
                        ET.register_namespace(prefix, uri)

                    root = ET.fromstring(raw_xml)
                    
                    # Locate RDF root
                    rdf = root.find('.//rdf:RDF', NS_MAP)
                    if rdf is None:
                        if root.tag.endswith('RDF'):
                            rdf = root
                    
                    if rdf is not None:
                        # Find all Descriptions and iterate
                        for desc in rdf.findall('.//rdf:Description', NS_MAP):
                            
                            # --- MWG Regions ---
                            for mwg_regions in desc.findall('.//mwg-rs:Regions', NS_MAP):
                                rlist = mwg_regions.find('mwg-rs:RegionList', NS_MAP)
                                if rlist is not None:
                                    # Support Bag and Seq
                                    containers = []
                                    containers.extend(rlist.findall('rdf:Bag', NS_MAP))
                                    containers.extend(rlist.findall('rdf:Seq', NS_MAP))
                                    
                                    for container in containers:
                                        for li in container.findall('rdf:li', NS_MAP):
                                            # Search context: li or nested Description
                                            search_root = li
                                            nested = li.find('rdf:Description', NS_MAP)
                                            if nested is not None:
                                                search_root = nested

                                            # --- 1. Find Label Name ---
                                            label_name = None
                                            
                                            # Check child element first
                                            name_el = search_root.find('stReg:Name', NS_MAP)
                                            if name_el is not None:
                                                label_name = name_el.text
                                            
                                            # Check attribute if not found
                                            if label_name is None:
                                                # Attribute key needs full URI
                                                streg_ns = NS_MAP['stReg']
                                                label_name = search_root.get(f"{{{streg_ns}}}Name")
                                            
                                            # --- 2. Find Area ---
                                            area = search_root.find('stReg:Area', NS_MAP)
                                            bbox = None
                                            
                                            if area is not None and label_name:
                                                # Helper to get value from attribute or child element
                                                def get_val(elem, ns_prefix, local_name):
                                                    # Try attribute
                                                    ns_uri = NS_MAP[ns_prefix]
                                                    val = elem.get(f"{{{ns_uri}}}{local_name}")
                                                    if val is not None:
                                                        return val
                                                    # Try child
                                                    child = elem.find(f"{ns_prefix}:{local_name}", NS_MAP)
                                                    if child is not None:
                                                        return child.text
                                                    return None

                                                unit_text = get_val(area, 'stArea', 'unit')
                                                
                                                if unit_text and unit_text.strip().lower() == 'normalized':
                                                    try:
                                                        cx = float(get_val(area, 'stArea', 'x'))
                                                        cy = float(get_val(area, 'stArea', 'y'))
                                                        w = float(get_val(area, 'stArea', 'w'))
                                                        h = float(get_val(area, 'stArea', 'h'))
                                                        
                                                        # Convert Center to Top-Left
                                                        xmin = cx - (w / 2.0)
                                                        ymin = cy - (h / 2.0)
                                                        bbox = {"xmin": xmin, "ymin": ymin, "width": w, "height": h}
                                                    except (ValueError, AttributeError, TypeError):
                                                        pass
                                            
                                            if label_name and bbox:
                                                found_regions[label_name].append(bbox)

                            # --- Legacy Iptc4xmpExt Regions ---
                            for iptc_regions in desc.findall('.//Iptc4xmpExt:ImageRegion', NS_MAP):
                                containers = []
                                containers.extend(iptc_regions.findall('rdf:Bag', NS_MAP))
                                containers.extend(iptc_regions.findall('rdf:Seq', NS_MAP))
                                
                                for container in containers:
                                    for li in container.findall('rdf:li', NS_MAP):
                                        # Name
                                        label_name = None
                                        name_elem = li.find('.//Iptc4xmpExt:Name', NS_MAP)
                                        if name_elem is not None:
                                            alt = name_elem.find('rdf:Alt', NS_MAP)
                                            if alt is not None:
                                                first_li = alt.find('rdf:li', NS_MAP)
                                                if first_li is not None:
                                                    label_name = first_li.text
                                            else:
                                                label_name = name_elem.text
                                        
                                        # Boundary
                                        boundary = li.find('Iptc4xmpExt:RegionBoundary', NS_MAP)
                                        bbox = None
                                        if boundary is not None and label_name:
                                            unit = boundary.find('Iptc4xmpExt:rbUnit', NS_MAP)
                                            if unit is not None and unit.text == 'relative':
                                                try:
                                                    x = float(boundary.find('Iptc4xmpExt:rbX', NS_MAP).text)
                                                    y = float(boundary.find('Iptc4xmpExt:rbY', NS_MAP).text)
                                                    w = float(boundary.find('Iptc4xmpExt:rbW', NS_MAP).text)
                                                    h = float(boundary.find('Iptc4xmpExt:rbH', NS_MAP).text)
                                                    bbox = {"xmin": x, "ymin": y, "width": w, "height": h}
                                                except (ValueError, AttributeError):
                                                    pass
                                                
                                        if label_name and bbox:
                                            found_regions[label_name].append(bbox)

            except Exception as e:
                print(f"XMP Region parse error: {e}")

        # Process found regions and apply suffixes
        for label, bboxes in found_regions.items():
            # Spatial sort
            bboxes.sort(key=lambda b: (b['ymin'], b['xmin']))
            
            for idx, bbox in enumerate(bboxes):
                # Apply suffix if multiple instances of same base label
                if len(bboxes) > 1:
                    display_label = f"{label}-{idx+1:02d}"
                else:
                    display_label = label
                    
                final_list.append({
                    "label": display_label,
                    "score": 1.0, 
                    "bbox": bbox,
                    "is_existing": True
                })

        # Add remaining subjects that were not covered by regions
        # We consider a subject "covered" if parsing regions for that label existed
        # (regardless of suffixing). 
        # If I have region "Person", I effectively have subject "Person".
        # If I have region "Person-01", did I mean "Person"?
        # For safety, let's just add all subjects that are NOT in the final_list labels.
        # But if we suffixed them, "Person" is not in "Person-01".
        
        # Simple heuristic: If simple subject is present, check if any region "starts with" it?
        # Or just simply: add them. Duplicates are better than data loss.
        # But filter exact matches.
        
        region_labels = set(o["label"] for o in final_list)
        # Any region "derived" from label X makes X "covered"?
        # If we have "Person-01", we assume "Person" is accounted for.
        
        covered_bases = set(found_regions.keys())
        
        for s in subjects:
            if s not in region_labels and s not in covered_bases:
                 final_list.append({
                    "label": s,
                    "score": 1.0,
                    "bbox": None,
                    "is_existing": True
                })
            
        return final_list

    def _merge_region(self, labels_map, label_name, bbox):
        obj = {
            "label": label_name,
            "score": 1.0,
            "bbox": bbox,
            "is_existing": True
        }
        
        # Logic: if we have "simple" placeholders (bbox=None) for this label,
        # assume this region corresponds to one of them.
        found_placeholder = False
        if label_name in labels_map:
            for existing in labels_map[label_name]:
                if existing["bbox"] is None:
                    existing["bbox"] = bbox
                    found_placeholder = True
                    break
        
        if not found_placeholder:
            if label_name not in labels_map:
                labels_map[label_name] = []
            labels_map[label_name].append(obj)


    def _refresh_labels_ui(self):
        # Clear layout
        while self._labels_layout.count():
            item = self._labels_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        # Group by label for suffix generation
        from collections import defaultdict
        groups = defaultdict(list)
        for obj in self._current_labels:
            groups[obj["label"]].append(obj)
            
        final_list = []
        for label, items in groups.items():
            if len(items) > 1:
                # Sort: items with bbox first, then sorted by ymin, xmin
                def sort_key(x):
                    b = x.get("bbox")
                    if b:
                        # ymin (top), xmin (left)
                        return (0, b["ymin"], b["xmin"])
                    return (1, 0, 0)
                
                items.sort(key=sort_key)
                
                for idx, obj in enumerate(items, 1):
                    final_list.append((obj, f"{label}-{idx:02d}"))
            else:
                final_list.append((items[0], label))

        # Sort final list alphabetically by text
        final_list.sort(key=lambda x: x[1])

        for obj, text in final_list:
            is_existing = obj.get("is_existing", False)
            tag = LabelTag(text, is_existing=is_existing)
            tag.removed.connect(lambda _, o=obj: self._on_object_removed(o))
            tag.clicked.connect(lambda _, o=obj: self._on_object_clicked(o))
            self._labels_layout.addWidget(tag)
        
        # Reset view unless Show All is on?
        if self._chk_show_all.isChecked():
            self._update_show_all()
        else:
            self._lbl_preview.set_bbox(None)

    def _on_show_all_toggled(self, checked: bool):
        if checked:
            self._update_show_all()
        else:
            self._lbl_preview.clear_all_mode()

    def _update_show_all(self):
        bboxes = [o["bbox"] for o in self._current_labels if o.get("bbox")]
        self._lbl_preview.set_all_bboxes(bboxes)

    def _on_object_removed(self, obj: dict):
        # Remove specific object instance
        if obj in self._current_labels:
            self._current_labels.remove(obj)
            self._refresh_labels_ui()

    def _on_object_clicked(self, obj: dict):
        # Show bbox for specific object
        bbox = obj.get("bbox")
        if bbox:
            # If showing all, disable it to focus on this one
            if self._chk_show_all.isChecked():
                self._chk_show_all.setChecked(False)
            
            self._lbl_preview.set_bbox(bbox)

    # Deprecated but keeping for safety if referenced elsewhere (unlikely)
    def _on_tag_removed(self, text: str):
        pass

    def _on_tag_clicked(self, text: str):
        pass

    def _on_view_xmp(self):
        if not self._current_image or not self._current_image.exists():
            return
        
        try:
            import pyexiv2 # type: ignore
            # Register namespace just in case
            try:
                pyexiv2.registerNs('http://iptc.org/std/Iptc4xmpExt/2008-02-29/', 'Iptc4xmpExt')
            except Exception:
                pass

            data = ""
            with pyexiv2.Image(str(self._current_image)) as img:
                data = img.read_raw_xmp()
            
            if not data:
                data = "No XMP data found."
            else:
                try:
                    import xml.dom.minidom
                    # Attempt to pretty print
                    dom = xml.dom.minidom.parseString(data)
                    data = dom.toprettyxml()
                except Exception:
                    pass # Keep raw if parsing fails

            dlg = XmpDisplayDialog(data, self)
            dlg.exec()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read XMP: {e}")

    def _on_suggest(self):
        if not self._current_image:
            return
        
        self._btn_suggest.setEnabled(False)
        self._btn_suggest.setText("Analyzing...")
        self._progress.setVisible(True)
        
        settings = QSettings("PhotoScanner", "App")
        device = settings.value("ai_device", "cpu")
        
        self._labeler = LabelingWorker(self._current_image, str(device))
        self._labeler.finished.connect(self._on_labels_ready)
        self._labeler.error.connect(self._on_label_error)
        self._labeler.start()

    def _on_labels_ready(self, objects: list[dict], error_msg: str):
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("Suggest Labels (AI)")
        self._progress.setVisible(False)
        
        if error_msg:
            QMessageBox.warning(self, "AI Warning", error_msg)
            return
        elif not objects:
            QMessageBox.information(self, "AI", "No objects detected.")
            return
        
        # Deduplicate Logic
        def calculate_iou(bbox1, bbox2):
             x1 = bbox1.get('xmin', 0)
             y1 = bbox1.get('ymin', 0)
             w1 = bbox1.get('width', 0)
             h1 = bbox1.get('height', 0)
             
             x2 = bbox2.get('xmin', 0)
             y2 = bbox2.get('ymin', 0)
             w2 = bbox2.get('width', 0)
             h2 = bbox2.get('height', 0)
             
             ix1 = max(x1, x2)
             iy1 = max(y1, y2)
             ix2 = min(x1 + w1, x2 + w2)
             iy2 = min(y1 + h1, y2 + h2)
             
             iw = max(0, ix2 - ix1)
             ih = max(0, iy2 - iy1)
             intersection = iw * ih
             
             union = (w1 * h1) + (w2 * h2) - intersection
             if union <= 0: return 0
             return intersection / union

        def get_base_label(l):
            import re
            m = re.match(r"^(.*)-\d+$", l)
            return m.group(1) if m else l

        added_count = 0
        for obj in objects:
            new_label = obj["label"]
            new_bbox = obj.get("bbox")
            
            is_duplicate = False
            for existing in self._current_labels:
                existing_label = existing["label"]
                existing_bbox = existing.get("bbox")
                
                # Check label match (case-insensitive base label)
                if get_base_label(existing_label).lower() == get_base_label(new_label).lower():
                    # If both have bboxes, check IoU
                    if existing_bbox and new_bbox:
                        if calculate_iou(existing_bbox, new_bbox) > 0.5:
                            is_duplicate = True
                            break
                    # If existing has no bbox, but we found the label -> treat as duplicate per user request
                    elif not existing_bbox:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                self._current_labels.append(obj)
                added_count += 1
        
        self._refresh_labels_ui()
        
        if added_count == 0:
            self._lbl_notification.setText("No new labels found.")
            self._lbl_notification.setVisible(True)
            QTimer.singleShot(3000, lambda: self._lbl_notification.setVisible(False))

    def _on_label_error(self, msg: str):
        self._btn_suggest.setEnabled(True)
        self._btn_suggest.setText("Suggest Labels (AI)")
        self._progress.setVisible(False)
        QMessageBox.warning(self, "AI Error", msg)

    def _on_save(self):
        if not self._current_image:
            return
            
        # Save to DB
        json_str = dumps_json(self._current_labels)
        
        db = PhotoDB(self._db_path)
        
        record = db.get_image(str(self._current_image))
        if not record:
            # Auto-add logic (simplified)
            from photoscanner.scanner import sha256_file
            import imagehash
            from PIL import Image
            
            s256 = sha256_file(self._current_image)
            try:
                with Image.open(self._current_image) as img:
                    ph = str(imagehash.phash(img))
                    w, h = img.size
            except:
                ph = "0" * 16
                w, h = 0, 0
            
            from photoscanner.db import ImageRecord
            
            new_record = ImageRecord(
                path=str(self._current_image),
                sha256=s256,
                phash=ph,
                width=w,
                height=h,
                file_size=os.path.getsize(self._current_image),
                mtime_ns=os.stat(self._current_image).st_mtime_ns,
                score=0.0,
                embedding=None,
                faces_json=None,
                objects_json=json_str
            )
            db.upsert_image(new_record)
        else:
            db.update_image_objects(str(self._current_image), json_str)
            
        db.close()

        # Write XMP
        try:
            self._write_xmp(self._current_image, self._current_labels)
            QMessageBox.information(self, "Saved", "Labels saved to database and XMP.")
        except ImportError:
            QMessageBox.information(self, "Saved", "Labels saved to database.\n(Install 'pyexiv2' to enable XMP writing)")
        except Exception as e:
            QMessageBox.warning(self, "XMP Error", f"Saved to DB, but failed to write XMP: {e}")

    def _write_xmp(self, path: Path, objects: list[dict]):
        import pyexiv2 # type: ignore
        from xml.etree import ElementTree as ET
        import re

        # Define Namespaces
        NS_MAP = {
            'x': "adobe:ns:meta/",
            'rdf': "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
            'dc': "http://purl.org/dc/elements/1.1/",
            'mwg-rs': "http://www.metadataworkinggroup.com/schemas/regions/",
            'stArea': "http://ns.adobe.com/xmp/sType/Area#",
            'stDim': "http://ns.adobe.com/xap/1.0/sType/Dimensions#",
            'stReg': "http://ns.adobe.com/xmp/sType/Region#"
        }

        # Register namespaces globally for pyexiv2
        try:
            for prefix, uri in NS_MAP.items():
                pyexiv2.registerNs(uri, prefix)
        except Exception:
            pass

        # Extract unique labels
        labels = sorted(list(set(o["label"] for o in objects)))
        
        # Filter objects with bounding boxes for Regions
        region_objects = [o for o in objects if o.get("bbox")]

        with pyexiv2.Image(str(path)) as img:
            # Get Image Dimensions for mwg-rs:AppliedToDimensions
            # Try getting from EXIF or guess (pyexiv2 might not yield easy w/h directly from XMP object)
            # but we can rely on our UI's preview or skip dimensions if strictly necessary.
            # However, the user example includes it, and it's good practice for MWG.
            # We already loaded QPixmap for this image in UI, but we are in a method that takes path.
            # Let's verify if we can get it from PIL quickly.
            
            img_w, img_h = 0, 0
            try:
                # pyexiv2 provides pixelWidth/Height? accessors?
                # Using PIL is safer for dimensions if accessible.
                from PIL import Image
                with Image.open(path) as pil_img:
                    img_w, img_h = pil_img.size
            except:
                pass

            raw_xmp = img.read_raw_xmp()
            
            # Create basic skeleton if missing
            if not raw_xmp:
                raw_xmp = """<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 5.6.0">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:mwg-rs="http://www.metadataworkinggroup.com/schemas/regions/"
    xmlns:stDim="http://ns.adobe.com/xap/1.0/sType/Dimensions#"
    xmlns:stArea="http://ns.adobe.com/xmp/sType/Area#"
    xmlns:stReg="http://ns.adobe.com/xmp/sType/Region#">
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""

            # Register namespaces for ET
            for prefix, uri in NS_MAP.items():
                ET.register_namespace(prefix, uri)
                
            try:
                root = ET.fromstring(raw_xmp)
                rdf = root.find('rdf:RDF', NS_MAP)
                if rdf is None:
                    # Try locally scoped finding without namespace logic if needed
                    rdf = root.find('{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF')
                
                if rdf is None:
                    rdf = ET.SubElement(root, f"{{{NS_MAP['rdf']}}}RDF")

                # Find Description
                desc = None
                for d in rdf.findall('rdf:Description', NS_MAP):
                    desc = d
                    break
                
                if desc is None:
                    desc = ET.SubElement(rdf, f"{{{NS_MAP['rdf']}}}Description")
                    desc.set(f"{{{NS_MAP['rdf']}}}about", "")

                # 1. Update Keywords (dc:subject)
                subject = desc.find('dc:subject', NS_MAP)
                if subject is not None:
                    desc.remove(subject)
                
                if labels:
                    subject = ET.SubElement(desc, f"{{{NS_MAP['dc']}}}subject")
                    bag = ET.SubElement(subject, f"{{{NS_MAP['rdf']}}}Bag")
                    for label in labels:
                        li = ET.SubElement(bag, f"{{{NS_MAP['rdf']}}}li")
                        li.text = label

                # 2. Update Image Regions (mwg-rs:Regions) - REMOVE OLD Extension logic if present
                # Remove Iptc4xmpExt logic if it exists (cleanup)
                old_ns = "http://iptc.org/std/Iptc4xmpExt/2008-02-29/"
                old_regions = desc.find(f"{{{old_ns}}}ImageRegion")
                if old_regions is not None:
                    desc.remove(old_regions)
                
                regions = desc.find('mwg-rs:Regions', NS_MAP)
                if regions is not None:
                    desc.remove(regions)
                
                if region_objects:
                    regions = ET.SubElement(desc, f"{{{NS_MAP['mwg-rs']}}}Regions")
                    regions.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
                    
                    # AppliedToDimensions
                    if img_w > 0 and img_h > 0:
                        dims = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}AppliedToDimensions")
                        dims.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
                        
                        w_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}w")
                        w_el.text = str(img_w)
                        h_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}h")
                        h_el.text = str(img_h)
                        unit_el = ET.SubElement(dims, f"{{{NS_MAP['stDim']}}}unit")
                        unit_el.text = "pixel"

                    # RegionList
                    rlist = ET.SubElement(regions, f"{{{NS_MAP['mwg-rs']}}}RegionList")
                    bag = ET.SubElement(rlist, f"{{{NS_MAP['rdf']}}}Bag")
                    
                    for obj in region_objects:
                        li = ET.SubElement(bag, f"{{{NS_MAP['rdf']}}}li")
                        li.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
                        
                        # stReg:Name (Label)
                        name_el = ET.SubElement(li, f"{{{NS_MAP['stReg']}}}Name")
                        name_el.text = obj["label"]
                        
                        # stReg:Type (e.g. Face)
                        # Default to "Face" per user request example, or verify via logic.
                        # Since we don't store type, we'll hardcode "Face" or map if possible.
                        # User example says "Subject A", Type "Face".
                        type_el = ET.SubElement(li, f"{{{NS_MAP['stReg']}}}Type")
                        type_el.text = "Face" 

                        # stReg:Area
                        bbox = obj["bbox"]
                        area = ET.SubElement(li, f"{{{NS_MAP['stReg']}}}Area")
                        area.set(f"{{{NS_MAP['rdf']}}}parseType", "Resource")
                        
                        # Convert Top-Left (xmin, ymin, w, h) to Center (x, y, w, h)
                        # bbox is relative 0-1
                        cx = bbox['xmin'] + (bbox['width'] / 2.0)
                        cy = bbox['ymin'] + (bbox['height'] / 2.0)
                        
                        def add_area_field(name, val):
                            e = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}{name}")
                            e.text = f"{val:.6f}"
                        
                        add_area_field("x", cx)
                        add_area_field("y", cy)
                        add_area_field("w", bbox['width'])
                        add_area_field("h", bbox['height'])
                        
                        unit_el = ET.SubElement(area, f"{{{NS_MAP['stArea']}}}unit")
                        unit_el.text = "normalized"

                # Serialize back
                ET.register_namespace("x", NS_MAP["x"])
                ET.register_namespace("rdf", NS_MAP["rdf"])
                ET.register_namespace("dc", NS_MAP["dc"])
                ET.register_namespace("mwg-rs", NS_MAP["mwg-rs"])
                ET.register_namespace("stDim", NS_MAP["stDim"])
                ET.register_namespace("stArea", NS_MAP["stArea"])
                ET.register_namespace("stReg", NS_MAP["stReg"])

                new_xml = ET.tostring(root, encoding='utf-8').decode('utf-8')
                
                # Verify and cleanup XML declaration if needed
                # (ET might add <?xml ...?> which is valid but sometimes XMP packets don't want it inside the packet wrapper)
                # But tostring usually doesn't add it unless requested.
                
                img.modify_raw_xmp(new_xml)
                
            except Exception as e:
                print(f"XML parsing error: {e}")
                import traceback
                traceback.print_exc()
                # Fallback to simple subject modification if XML fails
                img.modify_xmp({"Xmp.dc.subject": labels})