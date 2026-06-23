import os
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from plot_utils import (
    add_figure_suptitle,
    add_panel_label,
    add_panel_title,
    create_paper_figure,
    save_paper_figure,
    set_paper_styles,
)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

# Mock message boxes
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

app = QApplication.instance() or QApplication(sys.argv)

repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))
from Synaptipy.application.gui.main_window import MainWindow
from Synaptipy.infrastructure.file_readers import NeoAdapter


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    abf_path = repo_root / "examples" / "data" / "2023_04_11_0021.abf"
    out_dir = repo_root / "paper" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)

    win = MainWindow()
    win._offer_session_restore = lambda: None
    win._show_demo_download_banner = lambda: None
    win._check_for_updates_manual = lambda: None

    win.resize(1200, 800)
    win.show()

    print(f"Loading data synchronously: {abf_path}")
    adapter = NeoAdapter()
    recording = adapter.read_recording(str(abf_path))
    win._load_in_explorer(abf_path, [abf_path], 0, False)
    app.processEvents()

    win.tab_widget.setCurrentIndex(0)
    app.processEvents()

    # Expand and select sweeps
    model = win.explorer_tab.sidebar.project_tree.model()
    idx = model.index(0, 0)
    win.explorer_tab.sidebar.project_tree.expand(idx)
    app.processEvents()

    pm_b = win.explorer_tab.grab()
    pm_b.save(str(out_dir / "temp_b.png"))

    win.tab_widget.setCurrentIndex(1)
    app.processEvents()
    for i in range(win.analyser_tab.sub_tab_widget.count()):
        if "Passive" in win.analyser_tab.sub_tab_widget.tabText(
            i
        ) or "Intrinsic" in win.analyser_tab.sub_tab_widget.tabText(i):
            win.analyser_tab.sub_tab_widget.setCurrentIndex(i)
            break
    app.processEvents()
    pm_c = win.analyser_tab.grab()
    pm_c.save(str(out_dir / "temp_c.png"))

    win.tab_widget.setCurrentIndex(2)
    app.processEvents()
    pm_d = win.exporter_tab.grab()
    pm_d.save(str(out_dir / "temp_d.png"))

    print("UI grabs successful. Stitching composite image using unified Matplotlib styling...")

    set_paper_styles()

    # Overview is used for Panel A!
    img_a_path = out_dir / "synaptipy_overview.png"
    if not img_a_path.exists():
        # Copy it from docs or create a dummy one
        overview_src = repo_root / "docs" / "_build" / "html" / "_images" / "synaptipy_overview.png"
        if overview_src.exists():
            import shutil

            shutil.copy(overview_src, img_a_path)
        else:
            import numpy as np

            dummy = np.ones((800, 1280, 3)) * 0.9  # Light gray
            plt.imsave(img_a_path, dummy)

    img_b_path = out_dir / "temp_b.png"
    img_c_path = out_dir / "temp_c.png"
    img_d_path = out_dir / "temp_d.png"

    img_a = mpimg.imread(str(img_a_path))
    img_b = mpimg.imread(str(img_b_path))
    img_c = mpimg.imread(str(img_c_path))
    img_d = mpimg.imread(str(img_d_path))

    # Create a figure with a 2x2 gridspec
    fig = create_paper_figure(0, 0)
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1])

    # Top-left: img_a
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.imshow(img_a)
    ax1.axis("off")
    add_panel_title(ax1, "Overview & Project Architecture")
    add_panel_label(ax1, "A")

    # Top-right: img_b
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_b)
    ax2.axis("off")
    add_panel_title(ax2, "Data Explorer & Metadata View")
    add_panel_label(ax2, "B")

    # Bottom-left: img_c
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.imshow(img_c)
    ax3.axis("off")
    add_panel_title(ax3, "Analysis Pipeline Builder")
    add_panel_label(ax3, "C")

    # Bottom-right: img_d
    ax4 = fig.add_subplot(gs[1, 1])
    ax4.imshow(img_d)
    ax4.axis("off")
    add_panel_title(ax4, "Data Exporter & Summary Results")
    add_panel_label(ax4, "D")

    # Removed suptitle to comply with eNeuro publishing guidelines

    final_path = out_dir / "figure_01.png"
    save_paper_figure(fig, final_path)
    print(f"Figure 1 saved to {final_path}")

    # Cleanup temporary screenshots
    for temp_img in [img_b_path, img_c_path, img_d_path]:
        if temp_img.exists():
            temp_img.unlink()
    print("Cleaned up temporary screenshot files.")

    # Safe exit to prevent Qt crash
    app.quit()


if __name__ == "__main__":
    main()
