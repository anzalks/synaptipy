import os
import sys
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# Add scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent))
from plot_utils import add_panel_label, set_paper_styles

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

# Mock message boxes
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

app = QApplication.instance() or QApplication(sys.argv)

from Synaptipy.application.gui.main_window import MainWindow
from Synaptipy.infrastructure.file_readers import NeoAdapter


def main():
    repo_root = Path(__file__).resolve().parent.parent
    abf_path = repo_root / "examples" / "data" / "2023_04_11_0021.abf"

    win = MainWindow()
    win._offer_session_restore = lambda: None
    win._show_demo_download_banner = lambda: None
    win._check_for_updates_manual = lambda: None

    win.resize(1200, 800)
    win.show()

    print(f"Loading data synchronously: {abf_path}")
    adapter = NeoAdapter()
    recording = adapter.read_recording(str(abf_path))
    win._pending_file_list = [abf_path]
    win._pending_current_index = 0
    win._on_data_ready(recording)

    # Process all pending events
    for _ in range(100):
        app.processEvents()
        time.sleep(0.01)

    out_dir = repo_root / "paper" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Panel A: Explorer View
    win.tab_widget.setCurrentWidget(win.explorer_tab)
    for _ in range(10):
        app.processEvents()
    pm_a = win.explorer_tab.grab()
    pm_a.save(str(out_dir / "temp_a.png"))

    # Panel B: Analyser View
    win.tab_widget.setCurrentWidget(win.analyser_tab)
    for _ in range(10):
        app.processEvents()
    pm_b = win.analyser_tab.grab()
    pm_b.save(str(out_dir / "temp_b.png"))

    # Panel C: Batch Engine View
    win.tab_widget.setCurrentWidget(win.exporter_tab)
    for _ in range(10):
        app.processEvents()
    pm_c = win.exporter_tab.grab()
    pm_c.save(str(out_dir / "temp_c.png"))

    print("UI grabs successful. Stitching composite image using unified Matplotlib styling...")

    set_paper_styles()

    img_a_path = out_dir / "temp_a.png"
    img_b_path = out_dir / "temp_b.png"
    img_c_path = out_dir / "temp_c.png"

    img_a = mpimg.imread(str(img_a_path))
    img_b = mpimg.imread(str(img_b_path))
    img_c = mpimg.imread(str(img_c_path))

    # Create a figure with a customized gridspec
    fig = plt.figure(figsize=(14, 10))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1])

    # Top row: full width (img_a)
    ax1 = fig.add_subplot(gs[0, :])
    ax1.imshow(img_a)
    ax1.axis("off")
    add_panel_label(ax1, "A", x=-0.02, y=1.05)

    # Bottom row: two columns (img_b and img_c)
    ax2 = fig.add_subplot(gs[1, 0])
    ax2.imshow(img_b)
    ax2.axis("off")
    add_panel_label(ax2, "B", x=-0.05, y=1.05)

    ax3 = fig.add_subplot(gs[1, 1])
    ax3.imshow(img_c)
    ax3.axis("off")
    add_panel_label(ax3, "C", x=-0.05, y=1.05)

    plt.tight_layout()

    final_path = out_dir / "gui_workflow.png"
    plt.savefig(final_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"Final real-data composite saved to {final_path}")

    img_a_path.unlink()
    img_b_path.unlink()
    img_c_path.unlink()


if __name__ == "__main__":
    main()
    print("Done")
