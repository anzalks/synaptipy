# src/Synaptipy/application/gui/about_dialog.py
# -*- coding: utf-8 -*-
"""
About dialog for Synaptipy.

Accessible via Help -> About in the main window menu bar.
Displays version information and a discrete academic citation with a
copy-to-clipboard button.
"""

import logging

from PySide6 import QtCore, QtWidgets

log = logging.getLogger(__name__)

_APA_CITATION = (
    "Shahul, A. K., & Valera, A. (2026). Synaptipy: A High-Performance Suite for "
    "Experimental Electrophysiology. [Journal Name]. DOI: [Placeholder]"
)

_BIBTEX_CITATION = """\
@article{shahul2026synaptipy,
  author  = {Shahul, Anzal K. and Valera, A.},
  title   = {Synaptipy: A High-Performance Suite for Experimental Electrophysiology},
  journal = {[Journal Name]},
  year    = {2026},
  doi     = {[Placeholder]},
}"""


class AboutDialog(QtWidgets.QDialog):
    """
    Modal dialog displaying version information and academic citation for Synaptipy.

    Opened exclusively via Help -> About in the main menu bar.
    """

    def __init__(self, version: str, parent: QtWidgets.QWidget = None):
        """
        Initialise the About dialog.

        Args:
            version: The current Synaptipy version string (e.g. "0.1.0").
            parent:  Optional parent widget.
        """
        super().__init__(parent)
        self.setWindowTitle("About Synaptipy")
        self.setModal(True)
        self.setMinimumWidth(520)
        self._version = version
        self._build_ui()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Construct and lay out all widgets."""
        root = QtWidgets.QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(20, 20, 20, 20)

        # Title
        title_label = QtWidgets.QLabel("<b>Synaptipy</b>")
        title_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        font = title_label.font()
        font.setPointSize(font.pointSize() + 4)
        title_label.setFont(font)
        root.addWidget(title_label)

        # Subtitle
        subtitle = QtWidgets.QLabel("A High-Performance Suite for Experimental Electrophysiology")
        subtitle.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(subtitle)

        # Version
        version_label = QtWidgets.QLabel(f"Version: {self._version}")
        version_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        root.addWidget(version_label)

        root.addSpacing(8)

        # Citation section header
        cite_header = QtWidgets.QLabel("<b>Academic Citation</b>")
        root.addWidget(cite_header)

        # APA citation text (read-only, selectable)
        apa_box = QtWidgets.QPlainTextEdit()
        apa_box.setPlainText(_APA_CITATION)
        apa_box.setReadOnly(True)
        apa_box.setFixedHeight(70)
        root.addWidget(apa_box)

        # BibTeX citation text (read-only, selectable)
        bibtex_label = QtWidgets.QLabel("BibTeX:")
        root.addWidget(bibtex_label)

        bibtex_box = QtWidgets.QPlainTextEdit()
        bibtex_box.setPlainText(_BIBTEX_CITATION)
        bibtex_box.setReadOnly(True)
        bibtex_box.setFixedHeight(120)
        root.addWidget(bibtex_box)

        # Copy citation button
        copy_btn = QtWidgets.QPushButton("Copy Citation")
        copy_btn.setToolTip("Copy APA citation and BibTeX snippet to clipboard")
        copy_btn.clicked.connect(self._copy_citation)
        root.addWidget(copy_btn, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)

        root.addSpacing(4)

        # Close button
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)
        root.addWidget(button_box)

    def _copy_citation(self) -> None:
        """Copy both the APA citation and BibTeX snippet to the system clipboard."""
        combined = f"{_APA_CITATION}\n\n{_BIBTEX_CITATION}"
        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(combined)
        log.debug("Citation copied to clipboard.")
