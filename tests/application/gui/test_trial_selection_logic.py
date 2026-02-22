import sys
import unittest
import numpy as np
from unittest.mock import MagicMock
from PySide6 import QtWidgets

# Mock imports if needed, but we can import directly
from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.application.gui.explorer.explorer_tab import ExplorerTab


class TestTrialSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not QtWidgets.QApplication.instance():
            cls.app = QtWidgets.QApplication(sys.argv)
        else:
            cls.app = QtWidgets.QApplication.instance()

    def setUp(self):
        # Create Dummy Recording
        self.recording = Recording(source_file=MagicMock())
        self.recording.sampling_rate = 1000.0

        # 10 Trials of random data
        trials = [np.ones(100) * i for i in range(10)]  # Trial i has value i
        self.channel = Channel("0", "Ch0", "mV", 1000.0, trials)
        self.recording.channels["0"] = self.channel

        # Mocks
        self.neo_adapter = MagicMock()
        self.nwb_exporter = MagicMock()
        self.status_bar = QtWidgets.QStatusBar()

        self.explorer = ExplorerTab(
            self.neo_adapter, self.nwb_exporter, self.status_bar
        )
        self.explorer._display_recording(self.recording)

    def tearDown(self):
        self.explorer.deleteLater()

    def test_trial_selection_logic(self):
        """Test that requesting 'Every Nth trial' (gap-based) updates selection.

        The implementation uses gap-based logic: step = n + 1.
        So n=1 means every 2nd trial (step 2), n=2 means every 3rd (step 3).
        """
        # Initial: Empty selection (implies all)
        self.assertEqual(len(self.explorer.selected_trial_indices), 0)

        # Request gap=1 -> step=2 (Every 2nd: 0, 2, 4, 6, 8)
        self.explorer._on_trial_selection_requested(1)
        expected = {0, 2, 4, 6, 8}
        self.assertEqual(self.explorer.selected_trial_indices, expected)

        # Request gap=2 -> step=3 (Every 3rd: 0, 3, 6, 9)
        self.explorer._on_trial_selection_requested(2)
        expected = {0, 3, 6, 9}
        self.assertEqual(self.explorer.selected_trial_indices, expected)

    def test_selective_averaging(self):
        """Test that get_averaged_data respects indices."""
        # Average of all (0..9) = 4.5
        avg_all = self.channel.get_averaged_data()
        self.assertAlmostEqual(avg_all[0], 4.5)

        # Average of even trials (0, 2, 4, 6, 8) = 20/5 = 4.0
        indices = [0, 2, 4, 6, 8]
        avg_sel = self.channel.get_averaged_data(trial_indices=indices)
        self.assertAlmostEqual(avg_sel[0], 4.0)

    def test_reset_selection(self):
        self.explorer._on_trial_selection_requested(2)
        self.assertNotEqual(len(self.explorer.selected_trial_indices), 0)

        self.explorer._on_trial_selection_reset_requested()
        self.assertEqual(len(self.explorer.selected_trial_indices), 0)


if __name__ == '__main__':
    unittest.main()
