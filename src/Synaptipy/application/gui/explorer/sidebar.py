# src/Synaptipy/application/gui/explorer/sidebar.py
# -*- coding: utf-8 -*-
"""
Explorer Sidebar widget.
Handles file system navigation (tree view) and file list management.
"""
import logging
from pathlib import Path
from PySide6 import QtCore, QtWidgets, QtGui
from typing import Dict, Optional  # Added Dict
from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class ExplorerSidebar(QtWidgets.QGroupBox):
    """
    Sidebar containing the file explorer tree.
    Emits signals when a file is selected for loading.
    """

    file_selected = QtCore.Signal(Path, list, int)  # path, file_list, index

    def __init__(self, neo_adapter: NeoAdapter, file_io_controller=None, parent=None):
        super().__init__("File Explorer", parent)
        self.neo_adapter = neo_adapter
        self.file_io = file_io_controller
        self.file_model: Optional[QtWidgets.QFileSystemModel] = None
        self.file_tree: Optional[QtWidgets.QTreeView] = None

        self.setAcceptDrops(True)  # Screen-level drop support
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        self.file_model = QtWidgets.QFileSystemModel()
        self.file_model.setRootPath(QtCore.QDir.rootPath())

        # Filter for supported files using NeoAdapter
        supported_exts = self.neo_adapter.get_supported_extensions()
        self.file_model.setNameFilters([f"*.{ext}" for ext in supported_exts])
        self.file_model.setNameFilterDisables(False)

        self.file_tree = QtWidgets.QTreeView()
        self.file_tree.setModel(self.file_model)

        # Set initial directory from settings or default
        last_dir = QtCore.QSettings(APP_NAME, SETTINGS_SECTION).value("lastDirectory", str(Path.home()), type=str)
        self.file_tree.setRootIndex(self.file_model.index(last_dir))

        self.file_tree.setDragEnabled(True)  # Enable Drag
        self.file_tree.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragOnly)
        self.file_tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.file_tree.setHeaderHidden(True)

        # Hide columns other than Name (Size, Type, Date) to save space
        for i in range(1, 4):
            self.file_tree.setColumnHidden(i, True)

        # Set Custom Delegate
        self.delegate = QualityDelegate(self.file_tree)
        self.file_tree.setItemDelegate(self.delegate)

        self.file_tree.doubleClicked.connect(self._on_tree_double_clicked)

        # Async Sync Handling
        self.file_model.directoryLoaded.connect(self._on_directory_loaded)
        self._pending_sync_path: Optional[Path] = None

        layout.addWidget(self.file_tree)

    def _on_tree_double_clicked(self, index: QtCore.QModelIndex):
        """Handle double click on file tree to load file."""
        file_path = Path(self.file_model.filePath(index))
        if file_path.is_file():
            log.debug(f"Tree double-click: Loading {file_path}")

            # --- Build file_list for navigation ---
            # Get the parent directory index
            parent_index = index.parent()
            # Get number of rows (files) in the directory
            num_rows = self.file_model.rowCount(parent_index)

            file_list = []
            selected_index = 0

            # Iterate through siblings to build file list
            for i in range(num_rows):
                child_index = self.file_model.index(i, 0, parent_index)
                child_path = Path(self.file_model.filePath(child_index))

                if child_path.is_file():
                    file_list.append(child_path)
                    if child_path == file_path:
                        selected_index = len(file_list) - 1

            log.debug(f"Context loaded: {len(file_list)} files in directory. Selected index: {selected_index}")

            # Update settings
            QtCore.QSettings(APP_NAME, SETTINGS_SECTION).setValue("lastDirectory", str(file_path.parent))

            # Emit signal
            self.file_selected.emit(file_path, file_list, selected_index)

    def sync_to_file(self, file_path: Path):
        """Ensure the file explorer shows and selects the given file."""
        if not file_path or not self.file_model:
            return

        self._pending_sync_path = file_path

        # 1. Ask model to watch this path (triggers loading)
        self.file_model.setRootPath(str(file_path.parent))

        # 2. Try to sync immediately if already loaded
        self._attempt_sync(file_path)

    def _attempt_sync(self, file_path: Path):
        """Try to set root index and select file if model is ready."""
        parent_dir = file_path.parent
        parent_index = self.file_model.index(str(parent_dir))

        if parent_index.isValid():
            # Set View Root (Visual)
            self.file_tree.setRootIndex(parent_index)
            QtCore.QSettings(APP_NAME, SETTINGS_SECTION).setValue("lastDirectory", str(parent_dir))

            # Select File
            file_index = self.file_model.index(str(file_path))
            if file_index.isValid():
                self.file_tree.scrollTo(file_index, QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
                self.file_tree.setCurrentIndex(file_index)
                self.file_tree.selectionModel().select(
                    file_index, QtCore.QItemSelectionModel.SelectionFlag.ClearAndSelect
                )
                # Success, clear pending
                if self._pending_sync_path == file_path:
                    self._pending_sync_path = None
            else:
                log.debug(f"File index not valid yet: {file_path}")
        else:
            log.debug(f"Parent index not valid yet: {parent_dir}")

    def _on_directory_loaded(self, path: str):
        """Handle directory load completion."""
        if self._pending_sync_path and str(self._pending_sync_path.parent) == path:
            self._attempt_sync(self._pending_sync_path)

    def update_file_quality(self, file_path: Path, metrics: dict):
        """
        Update the quality status for a specific file and trigger repaint.
        """
        if self.file_tree.itemDelegate():
            delegate = self.file_tree.itemDelegate()
            if isinstance(delegate, QualityDelegate):
                delegate.update_status(file_path, metrics)

                # Retrieve index for the file path
                idx = self.file_model.index(str(file_path))

                # Trigget viewport update for the specific index if visible
                if idx.isValid():
                    self.file_tree.update(idx)

    # --- Drag & Drop Support ---
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QtGui.QDropEvent):
        if not self.file_io:
            log.warning("Drop ignored: No FileIOController connected.")
            return

        urls = event.mimeData().urls()
        if not urls:
            return

        file_paths = []
        for url in urls:
            if url.isLocalFile():
                file_paths.append(Path(url.toLocalFile()))

        if not file_paths:
            return

        # Pass rigid paths to FileIOController
        context = self.file_io.load_files(file_paths)

        if context:
            # Unpack context: (primary, list, index, lazy)
            primary_file, file_list, index, lazy = context
            log.debug(f"Drop accepted. Loading {primary_file}")

            # Emit signal to trigger loading in ExplorerTab
            self.file_selected.emit(primary_file, file_list, index)

            # Also sync sidebar to show this file
            self.sync_to_file(primary_file)

        event.acceptProposedAction()


class QualityDelegate(QtWidgets.QStyledItemDelegate):
    """
    Delegate to draw a small colored circle indicating signal quality next to the filename.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.quality_cache: Dict[Path, Dict] = {}
        # Colors
        self.color_good = QtGui.QColor("#2ecc71")   # Green
        self.color_warn = QtGui.QColor("#f1c40f")   # Yellow
        self.color_bad = QtGui.QColor("#e74c3c")    # Red
        self.color_unknown = QtGui.QColor("transparent")  # Default

    def update_status(self, path: Path, metrics: dict):
        self.quality_cache[path] = metrics

    def paint(self, painter: QtGui.QPainter, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex):
        # 1. Draw Default Text/Icon behavior
        super().paint(painter, option, index)

        # 2. Check if we have quality info for this file
        model = index.model()
        if isinstance(model, QtWidgets.QFileSystemModel):
            file_path = Path(model.filePath(index))

            if file_path in self.quality_cache:
                info = self.quality_cache[file_path]

                # Determine Color
                if not info.get("is_good", False):
                    color = self.color_bad
                elif info.get("warnings"):
                    color = self.color_warn
                else:
                    color = self.color_good

                # Draw Circle
                painter.save()
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)

                # Position: Right side of the item rect, or left of text?
                # FileSystemModel usually has Icon then Text.
                # Let's draw it on the far right of the column (Name column 0)
                # Or just to the left of the text if possible?
                # Calculating text rect is hard without more info.
                # Let's put it at fixed offset from left, assuming standard icon size.
                # Or better: Draw it on top of the icon? No.
                # Let's draw it in the right padding of the text?

                # Simple approach: Draw a small circle at (rect.right() - 15, center_y)
                radius = 4
                cx = option.rect.right() - 15
                cy = option.rect.center().y()

                if cx > option.rect.left():  # Only if visible
                    painter.drawEllipse(QtCore.QPointF(cx, cy), radius, radius)

                painter.restore()

    def helpEvent(self, event, view, option, index):
        """Show Tooltip with specific warnings."""
        if event.type() == QtCore.QEvent.Type.ToolTip:
            model = index.model()
            if isinstance(model, QtWidgets.QFileSystemModel):
                file_path = Path(model.filePath(index))
                if file_path in self.quality_cache:
                    info = self.quality_cache[file_path]

                    tooltip = "<b>Signal Quality analysis:</b><br>"
                    if not info.get("is_good"):
                        tooltip += f"<font color='red'>ERROR: {info.get('error', 'Unknown')}</font><br>"

                    if info.get("warnings"):
                        tooltip += "<b>Warnings:</b><ul>"
                        for w in info['warnings']:
                            tooltip += f"<li>{w}</li>"
                        tooltip += "</ul>"

                    # Add drift info if available
                    if 'metrics' in info:
                        m = info['metrics']
                        if 'total_drift' in m:
                            tooltip += f"<br>Drift: {m['total_drift']:.2f}"
                        if 'rms_noise' in m:
                            tooltip += f"<br>RMS Noise: {m['rms_noise']:.2f}"

                    QtWidgets.QToolTip.showText(event.globalPos(), tooltip, view)
                    return True

        return super().helpEvent(event, view, option, index)
