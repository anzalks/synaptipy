# src/Synaptipy/application/gui/nwb_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog for collecting NWB session metadata before export.
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from PySide6 import QtWidgets, QtCore # Make sure PySide6 is imported
try:
    import tzlocal # Optional, for local timezone handling
except ImportError:
    tzlocal = None

# Use a specific logger if desired, or fallback to root
log = logging.getLogger('Synaptipy.application.gui.nwb_dialog')

# --- NWB Metadata Dialog ---
# V V V CHECK THIS CLASS NAME CAREFULLY V V V
class NwbMetadataDialog(QtWidgets.QDialog):
    def __init__(self, default_identifier: str, default_start_time: datetime, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("NWB Session Metadata")
        self.setModal(True)
        self.layout = QtWidgets.QFormLayout(self)

        self.session_description = QtWidgets.QLineEdit("Session description...")
        self.identifier = QtWidgets.QLineEdit(default_identifier)

        # Ensure the default time passed is timezone-aware before setting
        if default_start_time.tzinfo is None:
            log.warning("NwbMetadataDialog received naive datetime, assuming UTC.")
            default_start_time = default_start_time.replace(tzinfo=timezone.utc)
        self.session_start_time_edit = QtWidgets.QDateTimeEdit(default_start_time)
        self.session_start_time_edit.setCalendarPopup(True)
        self.session_start_time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss t") # Show timezone offset
        self.session_start_time_edit.setTimeSpec(QtCore.Qt.TimeSpec.TimeZone) # Use timezone

        self.experimenter = QtWidgets.QLineEdit("")
        self.lab = QtWidgets.QLineEdit("")
        self.institution = QtWidgets.QLineEdit("")
        self.session_id = QtWidgets.QLineEdit("") # Optional NWB session_id

        self.layout.addRow("Description*:", self.session_description)
        self.layout.addRow("Identifier*:", self.identifier)
        self.layout.addRow("Start Time*:", self.session_start_time_edit)
        self.layout.addRow("Experimenter:", self.experimenter)
        self.layout.addRow("Lab:", self.lab)
        self.layout.addRow("Institution:", self.institution)
        self.layout.addRow("Session ID:", self.session_id)
        self.layout.addRow(QtWidgets.QLabel("* Required fields"))

        self.button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """Validates input and returns metadata dictionary or None if invalid."""
        desc = self.session_description.text().strip()
        ident = self.identifier.text().strip()
        # QDateTimeEdit with TimeZone spec should return aware datetime
        start_time_dt = self.session_start_time_edit.dateTime().toPython()

        if not desc or not ident:
            QtWidgets.QMessageBox.warning(self, "Input Error", "Session Description and Identifier are required fields.")
            return None

        # Double check timezone awareness (should be handled by QDateTimeEdit config now)
        if start_time_dt.tzinfo is None:
             log.error("QDateTimeEdit unexpectedly returned naive datetime despite TimeZone spec! Forcing UTC.")
             start_time_dt = start_time_dt.replace(tzinfo=timezone.utc)

        metadata = {
            "session_description": desc,
            "identifier": ident,
            "session_start_time": start_time_dt,
            "experimenter": self.experimenter.text().strip() or None,
            "lab": self.lab.text().strip() or None,
            "institution": self.institution.text().strip() or None,
            "session_id": self.session_id.text().strip() or None,
        }
        return metadata
# --- End NwbMetadataDialog Class ---