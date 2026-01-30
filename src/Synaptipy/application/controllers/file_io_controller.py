# src/Synaptipy/application/controllers/file_io_controller.py
from pathlib import Path
from typing import Optional, List, Tuple
import logging

from PySide6 import QtWidgets, QtCore

from Synaptipy.infrastructure.file_readers import NeoAdapter

log = logging.getLogger(__name__)


class FileIOController:
    """
    Controller responsible for handling file input/output operations,
    including file dialogs, directory scanning, and preference management.
    """

    def __init__(self, parent_widget: QtWidgets.QWidget, settings: QtCore.QSettings, neo_adapter: NeoAdapter):
        """
        Initialize the FileIOController.

        Args:
            parent_widget: The validation widget (usually MainWindow) to parent dialogs to.
            settings: QSettings instance for persisting preferences.
            neo_adapter: NeoAdapter instance for file format logic.
        """
        self.parent = parent_widget
        self.settings = settings
        self.neo_adapter = neo_adapter

    def prompt_and_get_file_context(self) -> Optional[Tuple[Path, List[Path], int, bool]]:
        """
        Shows the file open dialog, handles user interaction, updates settings,
        and determines the file context (siblings).

        Returns:
            Tuple containing:
            - Initial file path (Path)
            - List of sibling files (List[Path])
            - Index of initial file in list (int)
            - Lazy load enabled (bool)
            Or None if cancelled.
        """
        log.debug("FileIOController: Open file dialog requested.")

        # 1. Get File Filter
        try:
            file_filter = self.neo_adapter.get_supported_file_filter()
        except Exception as e:
            log.error(f"Failed to get file filter from NeoAdapter: {e}", exc_info=True)
            QtWidgets.QMessageBox.critical(self.parent, "Adapter Error", f"Could not get file types from adapter:\n{e}")
            file_filter = "All Files (*)"

        # 2. Get Last Directory
        last_dir = self.settings.value("lastDirectory", "", type=str)

        # 3. Setup Dialog
        dialog = QtWidgets.QFileDialog(self.parent, "Open Recording File", filter=file_filter)
        dialog.setDirectory(last_dir)
        dialog.setFileMode(QtWidgets.QFileDialog.FileMode.ExistingFile)

        # Add Custom Checkbox
        lazy_load_checkbox = QtWidgets.QCheckBox("Lazy Load (recommended for large files)")
        lazy_load_checkbox.setChecked(False)  # Default

        layout = dialog.layout()
        if isinstance(layout, QtWidgets.QGridLayout):
            row = layout.rowCount()
            layout.addWidget(lazy_load_checkbox, row, 0, 1, layout.columnCount())

        # 4. Show Dialog
        if not dialog.exec():
            log.debug("FileIOController: Dialog cancelled.")
            return None

        # 5. Process Selection
        filepath_str = dialog.selectedFiles()[0] if dialog.selectedFiles() else None
        if not filepath_str:
            return None

        lazy_load_enabled = lazy_load_checkbox.isChecked()
        selected_filepath = Path(filepath_str)
        folder_path = selected_filepath.parent

        # Update Settings
        self.settings.setValue("lastDirectory", str(folder_path))

        selected_extension = selected_filepath.suffix.lower()
        log.debug(
            f"File selected: {selected_filepath.name}. "
            f"Scanning folder '{folder_path}' for files with extension '{selected_extension}'."
        )

        # 6. Scan Siblings
        sibling_files = []
        try:
            if folder_path.exists() and folder_path.is_dir():
                for p in folder_path.iterdir():
                    if p.is_file() and p.suffix.lower() == selected_extension:
                        sibling_files.append(p)
            sibling_files.sort()
        except Exception as e:
            log.error(f"Error scanning folder {folder_path} for sibling files: {e}", exc_info=True)
            QtWidgets.QMessageBox.warning(
                self.parent,
                "Folder Scan Error",
                f"Could not scan folder for similar files:\n{e}\nLoading selected file only."
            )
            # Fallback
            return selected_filepath, [selected_filepath], 0, lazy_load_enabled

        # 7. Determine Context
        file_list = sibling_files if sibling_files else [selected_filepath]

        if not sibling_files:
            log.warning(
                f"No files with extension '{selected_extension}' found (including selected). Defaulting to selected."
            )

        try:
            current_index = file_list.index(selected_filepath)
        except ValueError:
            log.warning(f"Selected file '{selected_filepath.name}' not found in scanned list. Appending it.")
            file_list.append(selected_filepath)
            file_list.sort()
            current_index = file_list.index(selected_filepath)

        return selected_filepath, file_list, current_index, lazy_load_enabled
