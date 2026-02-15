# src/Synaptipy/application/gui/nwb_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog for collecting NWB session metadata before export.
Supports comprehensive metadata including Subject, Device, and Electrode details.
"""
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from PySide6 import QtWidgets, QtCore

try:
    import tzlocal
except ImportError:
    tzlocal = None

# Use a specific logger if desired, or fallback to root
log = logging.getLogger(__name__)


class NwbMetadataDialog(QtWidgets.QDialog):
    """
    A tabbed dialog for configuring NWB file metadata.
    Tabs: Session, Subject, Device, Electrode.
    """

    def __init__(self, recording=None, parent: Optional[QtWidgets.QWidget] = None):
        """
        Args:
            recording: Optional Recording object to pre-fill metadata from.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("NWB Export Metadata")
        self.resize(600, 500)
        self.setModal(True)

        self.recording = recording
        self._setup_ui()
        self._prefill_data()

    def _setup_ui(self):
        """Builds the tabbed UI structure."""
        main_layout = QtWidgets.QVBoxLayout(self)

        self.tab_widget = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tab_widget)

        # --- Create Tabs ---
        self.session_tab = self._create_session_tab()
        self.subject_tab = self._create_subject_tab()
        self.device_tab = self._create_device_tab()
        self.electrode_tab = self._create_electrode_tab()

        self.tab_widget.addTab(self.session_tab, "Session")
        self.tab_widget.addTab(self.subject_tab, "Subject")
        self.tab_widget.addTab(self.device_tab, "Device")
        self.tab_widget.addTab(self.electrode_tab, "Electrodes")

        # --- Button Box ---
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def _create_session_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.session_description = QtWidgets.QLineEdit()
        self.session_description.setPlaceholderText("Description of the experimental session...")

        self.identifier = QtWidgets.QLineEdit()
        self.identifier.setPlaceholderText("Unique session ID (UUID)")
        # Add a refresh button for UUID
        uuid_layout = QtWidgets.QHBoxLayout()
        uuid_layout.addWidget(self.identifier)
        self.refresh_uuid_btn = QtWidgets.QPushButton("Gen UUID")
        self.refresh_uuid_btn.setFixedWidth(70)
        self.refresh_uuid_btn.clicked.connect(lambda: self.identifier.setText(str(uuid.uuid4())))
        uuid_layout.addWidget(self.refresh_uuid_btn)

        self.session_start_time = QtWidgets.QDateTimeEdit(datetime.now())
        self.session_start_time.setCalendarPopup(True)
        self.session_start_time.setDisplayFormat("yyyy-MM-dd HH:mm:ss t")
        self.session_start_time.setTimeSpec(QtCore.Qt.TimeSpec.TimeZone)  # Use timezone

        self.session_id = QtWidgets.QLineEdit()  # Optional short ID
        self.experimenter = QtWidgets.QLineEdit()
        self.lab = QtWidgets.QLineEdit()
        self.institution = QtWidgets.QLineEdit()
        self.notes = QtWidgets.QTextEdit()
        self.notes.setPlaceholderText("Additional experimental notes...")
        self.notes.setMaximumHeight(80)

        layout.addRow("Description*:", self.session_description)
        layout.addRow("Identifier*:", uuid_layout)
        layout.addRow("Start Time*:", self.session_start_time)
        layout.addRow("Session ID:", self.session_id)
        layout.addRow("Experimenter:", self.experimenter)
        layout.addRow("Lab:", self.lab)
        layout.addRow("Institution:", self.institution)
        layout.addRow("Notes:", self.notes)
        layout.addRow(QtWidgets.QLabel("<i>* Required fields</i>"))

        return widget

    def _create_subject_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.subject_id = QtWidgets.QLineEdit()
        self.subject_id.setPlaceholderText("Unique subject identifier")

        self.species = QtWidgets.QComboBox()
        self.species.setEditable(True)
        self.species.addItems(
            [
                "",
                "Mus musculus",
                "Rattus norvegicus",
                "Homo sapiens",
                "Drosophila melanogaster",
                "Danio rerio",
                "Caenorhabditis elegans",
            ]
        )
        self.species.setPlaceholderText("Select or type species name")

        self.subject_age = QtWidgets.QLineEdit()
        self.subject_age.setPlaceholderText("ISO 8601 duration (e.g., P90D, P1Y2M)")

        self.subject_sex = QtWidgets.QComboBox()
        self.subject_sex.addItems(["U", "M", "F", "O"])  # NWB: Unknown, Male, Female, Other
        self.subject_sex.setCurrentText("U")
        self.subject_sex.setToolTip("M=Male, F=Female, O=Other, U=Unknown")

        self.subject_description = QtWidgets.QLineEdit()
        self.genotype = QtWidgets.QLineEdit()
        self.weight = QtWidgets.QLineEdit()

        layout.addRow("Subject ID (DANDI)*:", self.subject_id)
        layout.addRow("Species:", self.species)
        layout.addRow("Age:", self.subject_age)
        layout.addRow("Sex:", self.subject_sex)
        layout.addRow("Description:", self.subject_description)
        layout.addRow("Genotype:", self.genotype)
        layout.addRow("Weight:", self.weight)

        return widget

    def _create_device_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        self.device_name = QtWidgets.QLineEdit()
        self.device_description = QtWidgets.QLineEdit()
        self.device_manufacturer = QtWidgets.QLineEdit()

        layout.addRow("Device Name:", self.device_name)
        layout.addRow("Description:", self.device_description)
        layout.addRow("Manufacturer:", self.device_manufacturer)

        return widget

    def _create_electrode_tab(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(widget)

        layout.addRow(QtWidgets.QLabel("<b>Default Settings for Intracellular Electrodes:</b>"))

        self.elec_description = QtWidgets.QLineEdit("Intracellular Electrode")
        self.elec_location = QtWidgets.QLineEdit("Soma")
        self.elec_filtering = QtWidgets.QLineEdit("Unknown")

        layout.addRow("Description:", self.elec_description)
        layout.addRow("Location:", self.elec_location)
        layout.addRow("Filtering:", self.elec_filtering)

        return widget

    def _prefill_data(self):  # noqa: C901
        """Fills fields based on the Recording object if provided."""
        # Defaults
        self.identifier.setText(str(uuid.uuid4()))

        if not self.recording:
            return

        # Session Tab
        rec = self.recording

        # Protocol name as description
        desc = getattr(rec, "protocol_name", "")
        if not desc:
            desc = f"Recording from {rec.source_file.name}"
        self.session_description.setText(desc)

        # Session ID from filename
        self.session_id.setText(rec.source_file.stem)

        # Start Time
        start_dt = getattr(rec, "session_start_time_dt", None)
        if start_dt:
            # Check for timezone info
            if start_dt.tzinfo is None:
                # Attempt to localize if naive
                if tzlocal:
                    try:
                        start_dt = start_dt.replace(tzinfo=tzlocal.get_localzone())
                    except Exception:
                        start_dt = start_dt.replace(tzinfo=timezone.utc)
                else:
                    start_dt = start_dt.replace(tzinfo=timezone.utc)
            self.session_start_time.setDateTime(start_dt)

        # Notes
        meta_notes = rec.metadata.get("notes", "")
        if meta_notes:
            self.notes.setText(str(meta_notes))

        # Device info if available in metadata
        self.device_name.setText(rec.metadata.get("device_name", "Amplifier"))
        self.device_description.setText(rec.metadata.get("device_description", "Electrophysiology Recording System"))
        self.device_manufacturer.setText(rec.metadata.get("device_manufacturer", ""))

        # Check for user metadata if stored
        self.experimenter.setText(rec.metadata.get("experimenter", ""))
        self.lab.setText(rec.metadata.get("lab", ""))
        self.institution.setText(rec.metadata.get("institution", ""))

        # Subject info usually not in raw ABF, but check custom metadata keys
        self.subject_id.setText(rec.metadata.get("subject_id", ""))
        spec = rec.metadata.get("species", "")
        if spec:
            self.species.setCurrentText(spec)
        self.subject_age.setText(rec.metadata.get("age", ""))

        sex_val = rec.metadata.get("sex", "")
        if sex_val in ["M", "F", "O", "U"]:
            self.subject_sex.setCurrentText(sex_val)

        self.genotype.setText(rec.metadata.get("genotype", ""))

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """Validate and return all metadata as a nested dictionary."""

        # --- Validation ---
        desc = self.session_description.text().strip()
        ident = self.identifier.text().strip()

        if not desc:
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Session Description is required.")
            self.tab_widget.setCurrentWidget(self.session_tab)
            return None
        if not ident:
            QtWidgets.QMessageBox.warning(self, "Validation Error", "Session Identifier is required.")
            self.tab_widget.setCurrentWidget(self.session_tab)
            return None

        # Optional validation for Subject ID if strictly enforcing DANDI
        subj_id = self.subject_id.text().strip()
        # For now, let's keep it optional but warn? Or make it required if user entered ANY subject info?
        # Let's enforce it only if other subject fields are filled to avoid "half-empty" subject objects
        has_subject_info = any(
            [
                self.species.currentText().strip(),
                self.subject_age.text().strip(),
                self.subject_description.text().strip(),
                self.genotype.text().strip(),
                self.weight.text().strip(),
            ]
        )

        if has_subject_info and not subj_id:
            QtWidgets.QMessageBox.warning(
                self, "Validation Error", "Subject ID is required if Subject information is provided."
            )
            self.tab_widget.setCurrentWidget(self.subject_tab)
            return None

        # --- Construct Data ---

        # Session
        start_time_dt = self.session_start_time.dateTime().toPython()
        if start_time_dt.tzinfo is None:
            start_time_dt = start_time_dt.replace(tzinfo=timezone.utc)

        metadata = {
            # Core NWBFile fields
            "session_description": desc,
            "identifier": ident,
            "session_start_time": start_time_dt,
            "session_id": self.session_id.text().strip() or None,
            "experimenter": self.experimenter.text().strip() or None,
            "lab": self.lab.text().strip() or None,
            "institution": self.institution.text().strip() or None,
            "notes": self.notes.toPlainText().strip() or None,
            # Subject fields (nested dict or passed flat? Let's check exporter)
            # We will pass flattened logic or specific subject keys for the exporter to parse
            "subject_id": subj_id or None,
            "species": self.species.currentText().strip() or None,
            "sex": self.subject_sex.currentText(),
            "age": self.subject_age.text().strip() or None,
            "subject_description": self.subject_description.text().strip() or None,
            "genotype": self.genotype.text().strip() or None,
            "weight": self.weight.text().strip() or None,
            # Device fields
            "device_name": self.device_name.text().strip() or "Amplifier",
            "device_description": self.device_description.text().strip() or None,
            "device_manufacturer": self.device_manufacturer.text().strip() or None,
            # Electrode defaults (to be applied to channels if they don't have specifics)
            "electrode_description_default": self.elec_description.text().strip(),
            "electrode_location_default": self.elec_location.text().strip(),
            "electrode_filtering_default": self.elec_filtering.text().strip(),
        }

        return metadata


if __name__ == "__main__":
    # Test harness
    app = QtWidgets.QApplication([])

    # Mock recording
    class MockRec:
        def __init__(self):
            self.protocol_name = "Test Protocol"
            self.source_file = type("Path", (object,), {"name": "test_file.abf", "stem": "test_file"})()
            self.metadata = {}

    dlg = NwbMetadataDialog(recording=MockRec())
    if dlg.exec():
        print("Metadata:", dlg.get_metadata())
    else:
        print("Cancelled")
