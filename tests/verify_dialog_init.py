import sys
from pathlib import Path
from PySide6 import QtWidgets
from Synaptipy.application.gui.batch_dialog import BatchAnalysisDialog

# Minimal app
app = QtWidgets.QApplication.instance()
if not app:
    app = QtWidgets.QApplication(sys.argv)


def test_dialog():
    files = [Path("file1.abf"), Path("file2.abf")]
    pipeline_config = [{"analysis": "spike_detection", "scope": "all_trials", "params": {"threshold": -20}}]

    try:
        dialog = BatchAnalysisDialog(files, pipeline_config=pipeline_config)
        print("Dialog instantiated successfully")
        # dialog.show()  # Can't show in headless
        # Check if internal state is correct
        assert len(dialog.files) == 2
        assert len(dialog.pipeline_steps) == 1
        print("Dialog state verification passed")
    except Exception as e:
        print(f"Dialog instantiation failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_dialog()
