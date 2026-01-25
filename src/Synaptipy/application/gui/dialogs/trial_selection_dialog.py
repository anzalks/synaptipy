# src/Synaptipy/application/gui/dialogs/trial_selection_dialog.py
# -*- coding: utf-8 -*-
"""
Dialog for selecting multiple trials.
"""
from typing import Optional, Set, Tuple
from PySide6 import QtWidgets, QtCore


class TrialSelectionDialog(QtWidgets.QDialog):
    """
    Dialog to select multiple trials from a list.
    """

    def __init__(self, num_trials: int, pre_selected_indices: Optional[Set[int]] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Trials to Plot")
        self.resize(300, 400)

        self.num_trials = num_trials
        self.selected_indices: Set[int] = pre_selected_indices or set()

        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # List Widget
        self.list_widget = QtWidgets.QListWidget()
        layout.addWidget(self.list_widget)

        # Populate List
        for i in range(self.num_trials):
            item = QtWidgets.QListWidgetItem(f"Trial {i + 1}")
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)

            if i in self.selected_indices:
                item.setCheckState(QtCore.Qt.CheckState.Checked)
            else:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked)

            # Store index in user data
            item.setData(QtCore.Qt.ItemDataRole.UserRole, i)
            self.list_widget.addItem(item)

        # Selection Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.select_all_btn = QtWidgets.QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        btn_layout.addWidget(self.select_all_btn)

        self.select_none_btn = QtWidgets.QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._select_none)
        btn_layout.addWidget(self.select_none_btn)
        layout.addLayout(btn_layout)

        # Standard Dialog Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _select_all(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Checked)

    def _select_none(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setCheckState(QtCore.Qt.CheckState.Unchecked)

    def get_selected_indices(self) -> Set[int]:
        """Return a set of selected trial indices."""
        selected = set()
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == QtCore.Qt.CheckState.Checked:
                idx = item.data(QtCore.Qt.ItemDataRole.UserRole)
                selected.add(idx)
        return selected

    @staticmethod
    def get_selection(num_trials: int, pre_selected: Optional[Set[int]] = None, parent=None) -> Tuple[bool, Set[int]]:
        """
        Static convenience method to show the dialog.
        Returns (accepted, selected_indices).
        """
        dialog = TrialSelectionDialog(num_trials, pre_selected, parent)
        result = dialog.exec()
        return result == QtWidgets.QDialog.Accepted, dialog.get_selected_indices()
