# src/Synaptipy/application/gui/explorer/sidebar.py
# -*- coding: utf-8 -*-
"""
Explorer Sidebar widget.
Handles file system navigation (tree view) and file list management.
"""
import logging
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtWidgets
from Synaptipy.shared.constants import APP_NAME, SETTINGS_SECTION
from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class ExplorerSidebar(QtWidgets.QGroupBox):
    """
    Sidebar containing the file explorer tree.
    Emits signals when a file is selected for loading.
    """

    file_selected = QtCore.Signal(Path, list, int)  # path, file_list, index

    def __init__(self, neo_adapter: NeoAdapter, parent=None):
        super().__init__("File Explorer", parent)
        self.neo_adapter = neo_adapter
        self.file_model: Optional[QtWidgets.QFileSystemModel] = None
        self.file_tree: Optional[QtWidgets.QTreeView] = None
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
