import math
import sys
import os
import cv2
import numpy as np
import colorsys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QScrollArea, QFileDialog, QFrame,
                             QSplitter, QComboBox, QToolBar, QLayout, QSlider, QCheckBox)
from PyQt6.QtCore import Qt, QMimeData, QSize, pyqtSignal, QPoint, QUrl, QRect, QEvent, QTimer
from PyQt6.QtGui import QPixmap, QImage, QDrag, QColor, QPalette, QShortcut, QKeySequence

class DropZone(QLabel):
    fileDropped = pyqtSignal(str)

    def __init__(self, text, multiple=False):
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.multiple = multiple
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #555;
                border-radius: 10px;
                background-color: #2b2b2b;
                color: #eee;
                font-size: 16px;
                min-height: 80px;
            }
            QLabel:hover {
                border-color: #0078d7;
                background-color: #333;
                color: #fff;
            }
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.multiple:
                files, _ = QFileDialog.getOpenFileNames(self, "Select Edited Images", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                for f in files:
                    self.fileDropped.emit(f)
            else:
                file, _ = QFileDialog.getOpenFileName(self, "Select Base Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
                if file:
                    self.fileDropped.emit(file)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                self.fileDropped.emit(f)
                if not self.multiple:
                    break

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
        if index >= 0 and index < len(self.itemList):
            return self.itemList[index]
        return None

    def takeAt(self, index):
        if index >= 0 and index < len(self.itemList):
            return self.itemList.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        height = self.doLayout(QRect(0, 0, width, 0), True)
        return height

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self.itemList:
            wid = item.widget()
            if wid and wid.isHidden():
                continue
            size = size.expandedTo(item.minimumSize())
        size += QSize(2 * self.contentsMargins().top(), 2 * self.contentsMargins().top())
        return size

    def doLayout(self, rect, testOnly):
        x = rect.x()
        y = rect.y()
        lineHeight = 0

        for item in self.itemList:
            wid = item.widget()
            if wid and wid.isHidden():
                continue
            spaceX = self.spacing()
            spaceY = self.spacing()
            nextX = x + item.sizeHint().width() + spaceX
            if nextX - spaceX > rect.right() and lineHeight > 0:
                x = rect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())

        return y + lineHeight - rect.y()

class ThumbnailItem(QFrame):
    clicked = pyqtSignal(int)
    hovered = pyqtSignal(int)
    unhovered = pyqtSignal()
    settingsChanged = pyqtSignal(int)

    def __init__(self, pixmap, region_id, thumb_size=110):
        super().__init__()
        self.region_id = region_id
        self.selected = False
        self.thumb_size = thumb_size
        self.edge_margin = 0
        self.shape_type = "Overlap"
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 4)
        self.layout.setSpacing(2)
        
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_thumbnail(pixmap)
        self.layout.addWidget(self.label)
        
        # Controls Row
        ctrl_layout = QHBoxLayout()
        self.minus_btn = QPushButton("-")
        self.minus_btn.setFixedSize(20, 20)
        self.minus_btn.setAutoRepeat(True)
        self.minus_btn.setAutoRepeatDelay(300)
        self.minus_btn.setAutoRepeatInterval(50)
        self.minus_btn.clicked.connect(self.decrease_edge)
        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(20, 20)
        self.plus_btn.setAutoRepeat(True)
        self.plus_btn.setAutoRepeatDelay(300)
        self.plus_btn.setAutoRepeatInterval(50)
        self.plus_btn.clicked.connect(self.increase_edge)
        
        ctrl_layout.addWidget(self.minus_btn)
        ctrl_layout.addWidget(QLabel("Edge"))
        ctrl_layout.addWidget(self.plus_btn)
        self.layout.addLayout(ctrl_layout)
        
        self.shape_combo = QComboBox()
        self.shape_combo.addItems(["Overlap", "Tight Fit", "Rectangle", "Circle"])
        self.shape_combo.currentTextChanged.connect(self.on_shape_changed)
        self.layout.addWidget(self.shape_combo)
        
        self.update_size()
        self.setStyleSheet("""
            QFrame { border: 2px solid transparent; background: #3c3f41; border-radius: 5px; }
            QLabel { background: transparent; color: #eee; }
            QPushButton { background: #555; border-radius: 3px; font-weight: bold; color: white; }
            QComboBox { background: #555; color: white; border-radius: 3px; font-size: 10px; }
        """)

    def update_thumbnail(self, pixmap):
        self.pixmap = pixmap
        scaled = pixmap.scaled(self.thumb_size, self.thumb_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.label.setPixmap(scaled)

    def update_size(self):
        # Height needs to account for controls
        self.setFixedSize(self.thumb_size + 20, self.thumb_size + 80)
        self.update_thumbnail(self.pixmap)

    def mousePressEvent(self, event):
        self.selected = not self.selected
        self.update_border()
        self.clicked.emit(self.region_id)

    def enterEvent(self, event):
        self.hovered.emit(self.region_id)
        if not self.selected:
            self.setStyleSheet(self.styleSheet().replace("border: 2px solid transparent;", "border: 2px solid #555;"))

    def leaveEvent(self, event):
        self.unhovered.emit()
        self.update_border()

    def update_border(self):
        if self.selected:
            self.setStyleSheet(self.styleSheet().replace("border: 2px solid transparent;", "border: 2px solid #0078d7;").replace("border: 2px solid #555;", "border: 2px solid #0078d7;"))
        else:
            style = self.styleSheet()
            # Reset to transparent
            for b in ["border: 2px solid #0078d7;", "border: 2px solid #555;"]:
                style = style.replace(b, "border: 2px solid transparent;")
            self.setStyleSheet(style)

    def increase_edge(self):
        self.edge_margin += 1
        self.settingsChanged.emit(self.region_id)

    def decrease_edge(self):
        if self.edge_margin > -20:
            self.edge_margin -= 1
            self.settingsChanged.emit(self.region_id)

    def on_shape_changed(self, shape):
        self.shape_type = shape
        self.settingsChanged.emit(self.region_id)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bag o' Pix")
        self.resize(1000, 800)
        
        # Dark Mode Palette
        palette = QPalette()
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Window, QColor(43, 43, 43))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Base, QColor(60, 63, 65))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.AlternateBase, QColor(43, 43, 43))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Text, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Button, QColor(60, 63, 65))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.ColorGroup.All, QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        self.setPalette(palette)
        self.setStyleSheet("QLabel { color: #eee; }")

        self.base_image_path = None
        self.edited_images_paths = []
        self.found_regions = []
        self.current_preview_pixmap = None
        self.thumb_size = 110
        self.hovered_region_id = None
        self.min_region_size = 0
        self.max_region_size = 1000000
        self.preview_zoom = 1.0
        self.pulse_fade = 0
        self.pulse_angle = 0
        self.base_img = None

        self.setup_ui()
        self.setup_shortcuts()
        
        self.pulse_timer = QTimer()
        self.pulse_timer.timeout.connect(self.update_pulse)
        self.pulse_timer.start(50)

    def setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl++"), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+="), self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self, self.zoom_out)

    def wheelEvent(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            super().wheelEvent(event)

    def eventFilter(self, source, event):
        if event.type() == QEvent.Type.Wheel:
            mods = event.modifiers()
            delta = event.angleDelta().y()

            # Intercept Wheel event in thumbnails area if CTRL is held
            if source is self.scroll_area.viewport() and mods == Qt.KeyboardModifier.ControlModifier:
                if delta > 0:
                    self.zoom_in()
                else:
                    self.zoom_out()
                return True # Event handled, do not scroll
            
            # Intercept Wheel event in preview area for Zoom (CTRL) and Horizontal Scroll (SHIFT)
            if source is self.preview_scroll.viewport():
                if mods == Qt.KeyboardModifier.ControlModifier:
                    if delta > 0:
                        new_zoom = min(5.0, self.preview_zoom + 0.1)
                    else:
                        new_zoom = max(0.1, self.preview_zoom - 0.1)
                    self.zoom_slider.setValue(int(new_zoom * 100))
                    return True
                elif mods == Qt.KeyboardModifier.ShiftModifier:
                    hbar = self.preview_scroll.horizontalScrollBar()
                    hbar.setValue(hbar.value() - delta)
                    return True
                    
        return super().eventFilter(source, event)

    def on_preview_zoom_slider_changed(self, value):
        if not hasattr(self, '_setting_zoom_from_fit') or not self._setting_zoom_from_fit:
            if self.fit_checkbox.isChecked():
                self.fit_checkbox.blockSignals(True)
                self.fit_checkbox.setChecked(False)
                self.fit_checkbox.blockSignals(False)
        self.preview_zoom = value / 100.0
        self.zoom_status_label.setText(f"{value}%")
        self.update_preview()

    def on_fit_checkbox_changed(self, state):
        if state == Qt.CheckState.Checked.value:
            self.apply_fit_to_window()

    def apply_fit_to_window(self):
        if not self.current_preview_pixmap:
            return
        
        available_width = self.preview_scroll.viewport().width() - 4 # Small margin
        available_height = self.preview_scroll.viewport().height() - 4
        
        img_width = self.current_preview_pixmap.width()
        img_height = self.current_preview_pixmap.height()
        
        if img_width <= 0 or img_height <= 0:
            return
            
        zoom_w = available_width / img_width
        zoom_h = available_height / img_height
        zoom = min(zoom_w, zoom_h)
        
        # Clamp to slider range (10% to 500%)
        zoom = max(0.1, min(5.0, zoom))
        
        self._setting_zoom_from_fit = True
        self.zoom_slider.setValue(int(zoom * 100))
        self._setting_zoom_from_fit = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'fit_checkbox') and self.fit_checkbox.isChecked():
            # Delay slightly or call directly to ensure viewport size is updated
            QTimer.singleShot(0, self.apply_fit_to_window)

    def zoom_in(self):
        self.thumb_size = min(300, self.thumb_size + 20)
        self.update_thumbnails_size()

    def zoom_out(self):
        self.thumb_size = max(60, self.thumb_size - 20)
        self.update_thumbnails_size()

    def update_thumbnails_size(self):
        for i in range(self.thumbnails_layout.count()):
            item = self.thumbnails_layout.itemAt(i).widget()
            if isinstance(item, ThumbnailItem):
                item.thumb_size = self.thumb_size
                item.update_size()
        self.thumbnails_layout.invalidate()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Row: Base and Edited Sections
        top_row_layout = QHBoxLayout()

        # Base Image Section
        self.base_drop_zone = DropZone("Base Image\nDrop here or Click")
        self.base_drop_zone.fileDropped.connect(self.set_base_image)
        self.base_drop_zone.setFixedHeight(80)
        top_row_layout.addWidget(self.base_drop_zone, 1)

        # Edited Images Section
        edited_layout = QVBoxLayout()
        self.edited_drop_zone = DropZone("Edited Images\nDrop here or Click", multiple=True)
        self.edited_drop_zone.fileDropped.connect(self.append_edited_image)
        self.edited_drop_zone.setFixedHeight(40)
        edited_layout.addWidget(self.edited_drop_zone)
        
        reset_hbox = QHBoxLayout()

        self.edited_list_label = QLabel("No images added")
        reset_hbox.addWidget(self.edited_list_label)
        reset_hbox.addStretch()

        self.reset_btn = QPushButton("X Reset")
        self.reset_btn.setStyleSheet("background-color: #a00; color: white; font-weight: bold; padding: 5px;")
        self.reset_btn.clicked.connect(self.reset_edited_images)
        reset_hbox.addWidget(self.reset_btn)

        edited_layout.addLayout(reset_hbox)
        
        top_row_layout.addLayout(edited_layout, 1)
        main_layout.addLayout(top_row_layout)

        # Results area with Splitter
        self.results_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Left: Thumbnails Section
        thumb_container = QWidget()
        thumb_vbox = QVBoxLayout(thumb_container)
        thumb_vbox.setContentsMargins(0, 0, 0, 0)
        
        self.toolbar = QToolBar()
        self.toolbar.setStyleSheet("color: white")
        self.toolbar.addAction("Zoom +", self.zoom_in)
        self.toolbar.addAction("Zoom -", self.zoom_out)
        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel(" Min: "))
        self.min_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.min_size_slider.setRange(0, 10000)
        self.min_size_slider.setFixedWidth(100)
        self.min_size_slider.valueChanged.connect(self.on_min_size_changed)
        self.toolbar.addWidget(self.min_size_slider)
        
        self.toolbar.addWidget(QLabel(" Max: "))
        self.max_size_slider = QSlider(Qt.Orientation.Horizontal)
        self.max_size_slider.setRange(0, 10000)
        self.max_size_slider.setFixedWidth(100)
        self.max_size_slider.setValue(10000)
        self.max_size_slider.valueChanged.connect(self.on_max_size_changed)
        self.toolbar.addWidget(self.max_size_slider)
        
        thumb_vbox.addWidget(self.toolbar)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { border: none; background-color: #2b2b2b; }
            QScrollBar:vertical {
                background: #2b2b2b;
                width: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:vertical {
                background: #444;
                min-height: 20px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: #2b2b2b;
                height: 12px;
                margin: 0px 0px 0px 0px;
            }
            QScrollBar::handle:horizontal {
                background: #444;
                min-width: 20px;
                border-radius: 5px;
                margin: 2px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                width: 0px;
            }
        """)
        self.thumbnails_widget = QWidget()
        self.thumbnails_widget.setStyleSheet("background-color: #2b2b2b;")
        self.thumbnails_layout = FlowLayout(self.thumbnails_widget, spacing=10)
        self.scroll_area.setWidget(self.thumbnails_widget)
        # Install event filter to thumbnails area to handle CTRL+Wheel zoom without scrolling
        self.scroll_area.viewport().installEventFilter(self)
        thumb_vbox.addWidget(self.scroll_area)
        
        self.results_splitter.addWidget(thumb_container)

        # Right: Preview Section
        preview_container = QWidget()
        preview_vbox = QVBoxLayout(preview_container)
        
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setStyleSheet("border: 1px solid #555; background-color: #1e1e1e;")
        
        self.preview_label = QLabel("Final Preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setAcceptDrops(False)
        self.preview_label.setStyleSheet("border: none; background-color: transparent;")
        self.preview_label.setMinimumSize(400, 400)
        self.preview_label.mousePressEvent = self.copy_preview_to_clipboard
        self.preview_label.mouseMoveEvent = self.start_drag_preview
        
        self.preview_scroll.setWidget(self.preview_label)
        preview_vbox.addWidget(self.preview_scroll, 1)
        self.preview_scroll.viewport().installEventFilter(self)
        
        btn_layout = QHBoxLayout()
        btn_layout.addWidget(QLabel("Zoom:"))
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(10, 500)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(150)
        self.zoom_slider.valueChanged.connect(self.on_preview_zoom_slider_changed)
        btn_layout.addWidget(self.zoom_slider)
        
        self.zoom_status_label = QLabel("100%")
        btn_layout.addWidget(self.zoom_status_label)
        
        self.fit_checkbox = QCheckBox("Fit to Window")
        self.fit_checkbox.setStyleSheet("color: white;")
        self.fit_checkbox.stateChanged.connect(self.on_fit_checkbox_changed)
        self.fit_checkbox.setChecked(True)
        btn_layout.addWidget(self.fit_checkbox)
        
        btn_layout.addStretch()
        
        self.save_btn = QPushButton("Save PNG")
        self.save_btn.clicked.connect(self.save_preview)
        self.save_btn.setFixedHeight(30)
        self.save_btn.setFixedWidth(100)
        self.save_btn.setStyleSheet("""
            QPushButton { 
                background-color: #3c3f41; 
                color: white; 
                border: 1px solid #555; 
                border-radius: 4px;
                padding: 4px;
            }
            QPushButton:hover {
                background-color: #4c5052;
                border-color: #0078d7;
            }
        """)
        btn_layout.addWidget(self.save_btn)
        
        preview_vbox.addLayout(btn_layout)
        
        self.results_splitter.addWidget(preview_container)
        
        self.results_splitter.setSizes([500, 500])
        main_layout.addWidget(self.results_splitter)

    def set_base_image(self, path):
        self.base_image_path = path
        self.base_img = cv2.imread(path)
        self.base_drop_zone.setText(f"Base Image: {os.path.basename(path)}")
        self.analyze_differences()
        self.update_preview()

    def append_edited_image(self, path):
        if path not in self.edited_images_paths:
            self.edited_images_paths.append(path)
            self.update_edited_list()
            self.analyze_differences()

    def reset_edited_images(self):
        self.edited_images_paths = []
        self.update_edited_list()
        self.clear_thumbnails()
        self.analyze_differences()
        self.update_preview()

    def update_edited_list(self):
        if not self.edited_images_paths:
            self.edited_list_label.setText("No images added")
        else:
            names = [os.path.basename(p) for p in self.edited_images_paths]
            self.edited_list_label.setText(f"Images ({len(names)}): " + ", ".join(names[:5]) + ("..." if len(names) > 5 else ""))

    def clear_thumbnails(self):
        while self.thumbnails_layout.count():
            item = self.thumbnails_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.found_regions = []
        self.min_size_slider.setValue(0)
        self.min_region_size = 0

    def get_quadtree_regions(self, mask, min_size=16):
        def split(x, y, w, h):
            if w <= min_size or h <= min_size:
                if np.any(mask[y:y+h, x:x+w]):
                    return [(x, y, w, h)]
                return []
            
            roi = mask[y:y+h, x:x+w]
            count = np.count_nonzero(roi)
            if count == 0:
                return []
            if count == w * h:
                return [(x, y, w, h)]
            
            # Mixed
            hw, hh = w // 2, h // 2
            return split(x, y, hw, hh) + \
                   split(x + hw, y, w - hw, hh) + \
                   split(x, y + hh, hw, h - hh) + \
                   split(x + hw, y + hh, w - hw, h - hh)

        rects = split(0, 0, mask.shape[1], mask.shape[0])
        if not rects:
            return []
            
        qt_mask = np.zeros_like(mask)
        for x, y, w, h in rects:
            qt_mask[y:y+h, x:x+w] = 255
            
        num_labels, labels = cv2.connectedComponents(qt_mask)
        regions = []
        for i in range(1, num_labels):
            r_mask = (labels == i).astype(np.uint8) * 255
            regions.append(r_mask)
        return regions

    def analyze_differences(self):
        if not self.base_image_path or not self.edited_images_paths:
            self.clear_thumbnails()
            return

        self.clear_thumbnails()
        if self.base_img is None:
            self.base_img = cv2.imread(self.base_image_path)
        
        if self.base_img is None: return
        base_img = self.base_img

        # First pass: find all differences and merge them into a heatmap
        all_diff_data = [] # List of (edit_img, thresh_mask)
        heatmap = np.zeros(base_img.shape[:2], dtype=np.int32)
        
        for edit_path in self.edited_images_paths:
            edit_img = cv2.imread(edit_path)
            if edit_img is None: continue
            
            if edit_img.shape != base_img.shape:
                edit_img = cv2.resize(edit_img, (base_img.shape[1], base_img.shape[0]))

            diff = cv2.absdiff(base_img, edit_img)
            gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
            
            # Use 25 as a more sensitive threshold. 
            ret, thresh = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
            
            kernel = np.ones((3,3), np.uint8)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)
            thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
            
            heatmap += (thresh > 0).astype(np.int32)
            all_diff_data.append((edit_img, thresh))

        self.all_diffs_mask = (heatmap > 0).astype(np.uint8) * 255

        # Second pass: find regions using Quadtree on the global mask
        regions = self.get_quadtree_regions(self.all_diffs_mask)

        # Third pass: create thumbnails grouped by (region, image)
        for r_mask in regions:
            # Find the master contour and bounding box of the region
            contours, _ = cv2.findContours(r_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours: continue
            
            # Use largest contour if multiple (should be only one per region)
            master_cnt = max(contours, key=cv2.contourArea)
            epsilon = 0.01 * cv2.arcLength(master_cnt, True)
            master_approx = cv2.approxPolyDP(master_cnt, epsilon, True)
            x, y, w, h = cv2.boundingRect(master_approx)
            area = cv2.contourArea(master_approx)
            
            for edit_img, thresh in all_diff_data:
                # Only show one thumbnail per edited image, per region
                # Check intersection of this image's difference with this region
                intersection = cv2.bitwise_and(thresh, r_mask)
                if cv2.countNonZero(intersection) > 0:
                    # Initial mask will be updated by update_region_mask
                    mask = np.zeros(base_img.shape[:2], dtype=np.uint8)
                    
                    region_crop = edit_img[y:y+h, x:x+w].copy()
                    thumb_img = cv2.cvtColor(region_crop, cv2.COLOR_BGR2RGB)
                    h_t, w_t, c_t = thumb_img.shape
                    q_img = QImage(thumb_img.data, w_t, h_t, 3 * w_t, QImage.Format.Format_RGB888)
                    pix = QPixmap.fromImage(q_img.copy())
                    
                    region_id = len(self.found_regions)
                    self.found_regions.append({
                        'master_contour': master_cnt,
                        'master_approx': master_approx,
                        'region_mask': r_mask,
                        'image_mask': thresh,
                        'mask': mask,
                        'edit_img': edit_img,
                        'rect': (x, y, w, h),
                        'area': area
                    })
                    
                    thumb_item = ThumbnailItem(pix, region_id, thumb_size=self.thumb_size)
                    thumb_item.clicked.connect(self.on_thumbnail_clicked)
                    thumb_item.hovered.connect(self.on_thumbnail_hovered)
                    thumb_item.unhovered.connect(self.on_thumbnail_unhovered)
                    thumb_item.settingsChanged.connect(self.on_thumbnail_settings_changed)
                    self.thumbnails_layout.addWidget(thumb_item)
                    
                    # Apply default "Overlap" shape
                    self.update_region_mask(region_id)
        
        if self.found_regions:
            max_area = max(r['area'] for r in self.found_regions)
            self.min_size_slider.setMaximum(int(max_area))
            self.max_size_slider.setMaximum(int(max_area))
            self.max_size_slider.setValue(int(max_area))
        else:
            self.min_size_slider.setMaximum(10000)
            self.max_size_slider.setMaximum(10000)
            self.max_size_slider.setValue(10000)
        self.update_thumbnail_visibility()

    def on_min_size_changed(self, value):
        self.min_region_size = value
        if value >= self.max_size_slider.value():
            self.max_size_slider.setValue(value + 1)
        self.update_thumbnail_visibility()
        self.update_preview()

    def on_max_size_changed(self, value):
        self.max_region_size = value
        if value <= self.min_size_slider.value():
            self.min_size_slider.setValue(max(0, value - 1))
        self.update_thumbnail_visibility()
        self.update_preview()

    def update_thumbnail_visibility(self):
        for i in range(self.thumbnails_layout.count()):
            widget = self.thumbnails_layout.itemAt(i).widget()
            if isinstance(widget, ThumbnailItem):
                region_id = widget.region_id
                area = self.found_regions[region_id]['area']
                if area < self.min_region_size or area > self.max_region_size:
                    widget.hide()
                else:
                    widget.show()
        self.thumbnails_layout.invalidate()

    def on_thumbnail_clicked(self, region_id):
        self.update_preview()

    def on_thumbnail_hovered(self, region_id):
        self.hovered_region_id = region_id
        self.update_preview()

    def on_thumbnail_unhovered(self):
        self.hovered_region_id = None
        self.update_preview()

    def on_thumbnail_settings_changed(self, region_id):
        self.update_region_mask(region_id)
        self.update_preview()

    def update_region_mask(self, region_id):
        region = self.found_regions[region_id]
        thumb_item = None
        for i in range(self.thumbnails_layout.count()):
            w = self.thumbnails_layout.itemAt(i).widget()
            if isinstance(w, ThumbnailItem) and w.region_id == region_id:
                thumb_item = w
                break
        
        if not thumb_item: return

        # Recalculate mask based on shape and edge margin
        cnt = region['master_contour']
        mask = np.zeros(region['mask'].shape, dtype=np.uint8)
        
        if thumb_item.shape_type == "Overlap":
            hull = cv2.convexHull(cnt)
            cv2.drawContours(mask, [hull], -1, 255, -1)
        elif thumb_item.shape_type == "Tight Fit":
            # For Tight Fit, we use the image-specific mask within this region
            mask = cv2.bitwise_and(region['image_mask'], region['region_mask'])
        elif thumb_item.shape_type == "Rectangle":
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(mask, (x, y), (x+w, y+h), 255, -1)
        elif thumb_item.shape_type == "Circle":
            (x, y), radius = cv2.minEnclosingCircle(cnt)
            cv2.circle(mask, (int(x), int(y)), int(radius), 255, -1)
            
        # Apply edge margin (dilate or erode)
        margin = thumb_item.edge_margin
        if margin != 0:
            kernel = np.ones((abs(margin)*2+1, abs(margin)*2+1), np.uint8)
            if margin > 0:
                mask = cv2.dilate(mask, kernel, iterations=1)
            else:
                mask = cv2.erode(mask, kernel, iterations=1)
        
        region['mask'] = mask
        # Update approx for preview/hover if needed
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            region['master_approx'] = max(contours, key=cv2.contourArea) # Update approx for overlay

    def update_pulse(self):
        self.pulse_fade = self.pulse_fade + 1
        self.pulse_angle = (self.pulse_angle + 10) % 360
        if self.hovered_region_id is not None:
            self.update_preview()

    def update_preview(self):
        if not self.base_image_path:
            self.preview_label.setText("No Base Image")
            return

        if self.base_img is None:
            self.base_img = cv2.imread(self.base_image_path)
            
        if self.base_img is None: return
        base_img = cv2.cvtColor(self.base_img, cv2.COLOR_BGR2RGB)
        
        composite = base_img.copy().astype(np.float32)
        
        for i in range(self.thumbnails_layout.count()):
            item = self.thumbnails_layout.itemAt(i).widget()
            if isinstance(item, ThumbnailItem) and item.selected and not item.isHidden():
                region = self.found_regions[item.region_id]
                mask = region['mask'].astype(np.float32) / 255.0
                edit_img = cv2.cvtColor(region['edit_img'], cv2.COLOR_BGR2RGB).astype(np.float32)
                
                mask_3d = cv2.merge([mask, mask, mask])
                composite = composite * (1 - mask_3d) + edit_img * mask_3d

        composite = composite.astype(np.uint8)
        
        # Draw hover polygon
        if self.hovered_region_id is not None:
            region = self.found_regions[self.hovered_region_id]
            overlay = composite.copy()
            
            # Rainbow pulse
            hue = (self.pulse_angle % 360) / 360.0
            r_val, g_val, b_val = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
            color = (int(r_val * 255), int(g_val * 255), int(b_val * 255))
            
            cv2.drawContours(overlay, [region['master_approx']], -1, color, 3)
            alpha = math.sin(self.pulse_fade / 10.0) * 0.5 + 0.5
            composite = cv2.addWeighted(overlay, alpha, composite, 1.0 - alpha, 0)

        h, w, c = composite.shape
        q_img = QImage(composite.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(q_img.copy())
        self.current_preview_pixmap = pix
        
        # Scaling relative to original image size
        target_size = pix.size() * self.preview_zoom
        scaled_pix = pix.scaled(target_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.preview_label.setPixmap(scaled_pix)
        self.preview_label.setFixedSize(scaled_pix.size())

        self.apply_fit_to_window()

    def copy_preview_to_clipboard(self, event):
        if self.current_preview_pixmap:
            QApplication.clipboard().setPixmap(self.current_preview_pixmap)
            print("Copied to clipboard")

    def start_drag_preview(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton) or not self.current_preview_pixmap:
            return
            
        # Ensure we only start drag after a certain distance
        if (event.pos() - QPoint(0, 0)).manhattanLength() < QApplication.startDragDistance():
            # Wait, event.pos() is relative to label. 
            # We don't have the initial press pos here easily, but we can just drag.
            pass

        drag = QDrag(self)
        mime_data = QMimeData()
        temp_path = os.path.abspath("final_preview.png")
        self.current_preview_pixmap.save(temp_path, "PNG")
        mime_data.setUrls([QUrl.fromLocalFile(temp_path)])
        
        # Also include image data for apps that support it
        mime_data.setImageData(self.current_preview_pixmap.toImage())
        
        drag.setMimeData(mime_data)
        drag.setPixmap(self.current_preview_pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        drag.exec(Qt.DropAction.CopyAction)

    def save_preview(self):
        if self.current_preview_pixmap:
            path, _ = QFileDialog.getSaveFileName(self, "Save Preview", "final_preview.png", "Images (*.png)")
            if path:
                self.current_preview_pixmap.save(path, "PNG")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
