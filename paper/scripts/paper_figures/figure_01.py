import os
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt

# Add parent scripts directory to path to import plot_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from figure_01_panel_a import draw_panel_a, save_panel_a_svg
from plot_utils import (
    add_panel_label,
    add_panel_title,
    create_paper_figure,
    set_paper_styles,
)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QMessageBox

# Mock message boxes
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

app = QApplication.instance() or QApplication(sys.argv)

repo_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(repo_root / "src"))
from synaptipy.application.gui.main_window import MainWindow


def main():
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    abf_path = repo_root / "examples" / "data" / "2023_04_11_0021.abf"
    out_dir = repo_root / "paper" / "figures"
    out_dir.mkdir(parents=True, exist_ok=True)
    save_panel_a_svg(out_dir / "figure_01_panel_a.svg")

    win = MainWindow()
    win._offer_session_restore = lambda: None
    win._show_demo_download_banner = lambda: None
    win._check_for_updates_manual = lambda: None

    win.resize(1200, 800)
    win.show()

    print(f"Loading data: {abf_path}")
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

    print(
        "UI grabs successful. Stitching composite image using unified Matplotlib styling..."
    )

    set_paper_styles()
    plt.rcParams["svg.fonttype"] = "none"

    img_b_path = out_dir / "temp_b.png"
    img_c_path = out_dir / "temp_c.png"
    img_d_path = out_dir / "temp_d.png"

    img_b = mpimg.imread(str(img_b_path))
    img_c = mpimg.imread(str(img_c_path))
    img_d = mpimg.imread(str(img_d_path))

    # Create a figure with a 2x2 gridspec
    fig = create_paper_figure(0, 0)
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1], width_ratios=[1, 1])

    # Top-left: draw the architecture as vectors in the composite figure.
    ax1 = fig.add_subplot(gs[0, 0])
    draw_panel_a(ax1, font_scale=0.78)
    add_panel_title(ax1, "Overview & Project Architecture")
    add_panel_label(ax1, "A")

    # Top-right: img_b
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.imshow(img_b)
    ax2.set_anchor("N")
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
    vector_path = out_dir / "figure_01.svg"
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(final_path, dpi=300, bbox_inches="tight")
    fig.savefig(vector_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Figure 1 saved to {final_path} and {vector_path}")

    # Cleanup temporary screenshots
    for temp_img in [img_b_path, img_c_path, img_d_path]:
        if temp_img.exists():
            temp_img.unlink()
    print("Cleaned up temporary screenshot files.")

    # MainWindow.closeEvent stops its worker thread and cleans up the tabs.
    win.close()
    app.processEvents()
    app.quit()


if __name__ == "__main__":
    main()
