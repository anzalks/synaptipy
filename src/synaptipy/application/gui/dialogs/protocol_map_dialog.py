# -*- coding: utf-8 -*-
"""Compact editor for trial/time protocol assignments.

The dialog deliberately edits the recording's :class:`ProtocolMap` rather than
analysis parameters.  This makes the choice reusable across all built-in
analyses and visible before a batch is submitted.
"""

from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from synaptipy.core.protocols import ProtocolAssignment, ProtocolSource


class ProtocolMapDialog(QtWidgets.QDialog):
    """Review and manually assign protocol segments for the open recording."""

    FAMILIES = (
        "signal_only",
        "current_step",
        "single_stim",
        "paired_pulse",
        "stimulus_train",
        "optogenetic",
        "custom",
    )

    def __init__(self, recording, current_trial: int = 0, parent=None):
        super().__init__(parent)
        self.recording = recording
        self.current_trial = max(0, int(current_trial))
        self.setWindowTitle("Protocol Map")
        self.resize(760, 430)
        self._build()
        self._refresh()

    def _build(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        description = QtWidgets.QLabel(
            "Assign a protocol to individual trials or a time range. Analysis segments cannot overlap; "
            "annotations may overlap and are retained as context. Select detected evidence to copy its "
            "recorded command or timing details into a reviewed assignment."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QtWidgets.QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ("Trials", "Protocol", "Label", "Window (s)", "Source", "Verified", "Kind")
        )
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        form = QtWidgets.QFormLayout()
        self.trials = QtWidgets.QLineEdit(str(self.current_trial + 1))
        self.trials.setToolTip("One-based trial numbers; use commas/ranges, e.g. 1, 3-5.")
        self.family = QtWidgets.QComboBox()
        self.family.addItems(self.FAMILIES)
        self.detected_evidence = QtWidgets.QComboBox()
        self.detected_evidence.addItem("No detected evidence selected", None)
        self.detected_evidence.currentIndexChanged.connect(self._select_detected_evidence)
        self._selected_evidence_id = None
        self.label = QtWidgets.QLineEdit()
        self.start = QtWidgets.QDoubleSpinBox()
        self.end = QtWidgets.QDoubleSpinBox()
        for widget in (self.start, self.end):
            widget.setRange(0.0, 1e9)
            widget.setDecimals(5)
            widget.setSpecialValueText("full trial")
        self.source = QtWidgets.QComboBox()
        # ``recorded`` is reserved for importer-created assignments backed by
        # an actual command/TTL trace; a manual UI choice must not claim that
        # evidence exists.
        self.source.addItems(
            [
                ProtocolSource.MANUAL.value,
                ProtocolSource.DRAWN.value,
                ProtocolSource.IMPORTED.value,
                ProtocolSource.SIGNAL_ONLY.value,
            ]
        )
        self.source.addItem(ProtocolSource.RECORDED.value)
        recorded_index = self.source.findText(ProtocolSource.RECORDED.value)
        self.source.model().item(recorded_index).setEnabled(False)
        self.verified = QtWidgets.QCheckBox("Reviewed")
        self.annotation = QtWidgets.QCheckBox("Annotation (may overlap)")
        self.manual_steps = QtWidgets.QCheckBox("Verified manual current-step table supplied")
        self.manual_timings = QtWidgets.QCheckBox("Verified manual stimulus timings supplied")
        form.addRow("Trials:", self.trials)
        form.addRow("Protocol family:", self.family)
        form.addRow("Detected evidence:", self.detected_evidence)
        form.addRow("Label:", self.label)
        form.addRow("Start / end:", self._pair(self.start, self.end))
        form.addRow("Source:", self.source)
        form.addRow("", self.verified)
        form.addRow("", self.manual_steps)
        form.addRow("", self.manual_timings)
        form.addRow("", self.annotation)
        layout.addLayout(form)

        buttons = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton("Add Assignment")
        add.clicked.connect(self._add)
        remove = QtWidgets.QPushButton("Remove Selected")
        remove.clicked.connect(self._remove)
        close = QtWidgets.QPushButton("Done")
        close.clicked.connect(self.accept)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @staticmethod
    def _pair(first: QtWidgets.QWidget, second: QtWidgets.QWidget) -> QtWidgets.QWidget:
        holder = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(first)
        layout.addWidget(QtWidgets.QLabel("to"))
        layout.addWidget(second)
        return holder

    def _trial_indices(self):
        text = self.trials.text().strip()
        count = max(1, getattr(self.recording, "max_trials", 0) or self.current_trial + 1)
        one_based = set()
        for part in text.split(","):
            token = part.strip()
            if not token:
                continue
            bounds = [int(value.strip()) for value in token.split("-", 1)]
            if len(bounds) == 1:
                one_based.add(bounds[0])
            else:
                start, end = bounds
                if end < start:
                    raise ValueError("Trial ranges must increase from left to right.")
                one_based.update(range(start, end + 1))
        if not one_based or min(one_based) < 1 or max(one_based) > count:
            raise ValueError(f"Trials must be between 1 and {count}.")
        return tuple(index - 1 for index in sorted(one_based))

    def _add(self) -> None:
        try:
            indices = self._trial_indices()
            if not indices:
                raise ValueError("Choose at least one trial.")
            start = self.start.value() if self.start.value() > 0 else None
            end = self.end.value() if self.end.value() > 0 else None
            if (start is None) != (end is None):
                raise ValueError("Enter both start and end, or leave both at full trial.")
            evidence = self._selected_evidence()
            parameters = dict(evidence.parameters) if evidence is not None else {}
            parameters.update(
                {
                    **({"current_steps": "manual"} if self.manual_steps.isChecked() else {}),
                    **({"stimulus_times": "manual"} if self.manual_timings.isChecked() else {}),
                }
            )
            source = ProtocolSource.RECORDED if evidence is not None else ProtocolSource(self.source.currentText())
            assignment = ProtocolAssignment(
                protocol_family=self.family.currentText(),
                trial_indices=indices,
                start_time=start,
                end_time=end,
                label=self.label.text().strip(),
                source=source,
                parameters=parameters,
                verified=self.verified.isChecked(),
                is_analysis_segment=not self.annotation.isChecked(),
            )
            self.recording.protocol_map.add(assignment)
        except ValueError as exc:
            QtWidgets.QMessageBox.warning(self, "Cannot Add Protocol Assignment", str(exc))
            return
        self._refresh()

    def _selected_evidence(self):
        """Return the selected importer-created annotation, if it remains present."""
        if not self._selected_evidence_id:
            return None
        return next(
            (
                assignment
                for assignment in self.recording.protocol_map.assignments
                if assignment.assignment_id == self._selected_evidence_id
                and not assignment.is_analysis_segment
                and assignment.source == ProtocolSource.RECORDED
                and assignment.parameters.get("auto_detected") is True
            ),
            None,
        )

    def _select_detected_evidence(self, index: int) -> None:
        assignment_id = self.detected_evidence.itemData(index)
        self._selected_evidence_id = assignment_id or None
        evidence = self._selected_evidence()
        if evidence is None:
            return
        self.trials.setText(", ".join(str(trial_index + 1) for trial_index in evidence.trial_indices))
        self.label.setText(evidence.label)
        self.source.setCurrentText(ProtocolSource.RECORDED.value)

    def _refresh_detected_evidence(self) -> None:
        selected = self._selected_evidence_id
        self.detected_evidence.blockSignals(True)
        self.detected_evidence.clear()
        self.detected_evidence.addItem("No detected evidence selected", None)
        for assignment in self.recording.protocol_map.assignments:
            if (
                not assignment.is_analysis_segment
                and assignment.source == ProtocolSource.RECORDED
                and assignment.parameters.get("auto_detected") is True
            ):
                trial_label = ", ".join(str(index + 1) for index in assignment.trial_indices)
                self.detected_evidence.addItem(f"{assignment.label} (trials {trial_label})", assignment.assignment_id)
        index = self.detected_evidence.findData(selected)
        self.detected_evidence.setCurrentIndex(index if index >= 0 else 0)
        self.detected_evidence.blockSignals(False)
        self._selected_evidence_id = self.detected_evidence.currentData() or None

    def _remove(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        assignment_id = self.table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)
        self.recording.protocol_map.remove(assignment_id)
        self._refresh()

    def _refresh(self) -> None:
        self._refresh_detected_evidence()
        assignments = self.recording.protocol_map.assignments
        self.table.setRowCount(len(assignments))
        for row, assignment in enumerate(assignments):
            trial_label = ", ".join(str(index + 1) for index in assignment.trial_indices)
            window = (
                "full trial"
                if assignment.start_time is None
                else f"{assignment.start_time:g} – {assignment.end_time:g}"
            )
            values = (
                trial_label,
                assignment.protocol_family,
                assignment.label or "—",
                window,
                assignment.source.value,
                "yes" if assignment.verified else "needs review",
                "segment" if assignment.is_analysis_segment else "annotation",
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, assignment.assignment_id)
                self.table.setItem(row, column, item)
