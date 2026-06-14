import sys
import os
import time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QTimer

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
    for _ in range(10): app.processEvents()
    pm_a = win.explorer_tab.grab()
    pm_a.save(str(out_dir / "temp_a.png"))
    
    # Panel B: Analyser View
    win.tab_widget.setCurrentWidget(win.analyser_tab)
    for _ in range(10): app.processEvents()
    pm_b = win.analyser_tab.grab()
    pm_b.save(str(out_dir / "temp_b.png"))
    
    # Panel C: Batch Engine View
    win.tab_widget.setCurrentWidget(win.exporter_tab)
    for _ in range(10): app.processEvents()
    pm_c = win.exporter_tab.grab()
    pm_c.save(str(out_dir / "temp_c.png"))
    
    print("UI grabs successful. Stitching composite image...")
    
    img_a = Image.open(out_dir / "temp_a.png")
    img_b = Image.open(out_dir / "temp_b.png")
    img_c = Image.open(out_dir / "temp_c.png")
    
    target_width = 1600
    a_ratio = target_width / img_a.width
    a_height = int(img_a.height * a_ratio)
    img_a = img_a.resize((target_width, a_height), Image.Resampling.LANCZOS)

    padding = 20
    bottom_width = (target_width - padding) // 2
    
    b_ratio = bottom_width / img_b.width
    b_height = int(img_b.height * b_ratio)
    img_b = img_b.resize((bottom_width, b_height), Image.Resampling.LANCZOS)

    c_ratio = bottom_width / img_c.width
    c_height = int(img_c.height * c_ratio)
    img_c = img_c.resize((bottom_width, c_height), Image.Resampling.LANCZOS)

    canvas_height = a_height + padding + max(b_height, c_height)
    canvas = Image.new("RGB", (target_width, canvas_height), "white")

    canvas.paste(img_a, (0, 0))
    canvas.paste(img_b, (0, a_height + padding))
    canvas.paste(img_c, (bottom_width + padding, a_height + padding))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 60)
    except IOError:
        font = ImageFont.load_default()

    labels = [
        ("A", (20, 20)),
        ("B", (20, a_height + padding + 20)),
        ("C", (bottom_width + padding + 20, a_height + padding + 20)),
    ]

    for text, (x, y) in labels:
        draw.text((x-2, y-2), text, fill="white", font=font)
        draw.text((x+2, y+2), text, fill="white", font=font)
        draw.text((x, y), text, fill="black", font=font)

    final_path = out_dir / "gui_workflow.png"
    canvas.save(final_path)
    print(f"Final real-data composite saved to {final_path}")
    
    (out_dir / "temp_a.png").unlink()
    (out_dir / "temp_b.png").unlink()
    (out_dir / "temp_c.png").unlink()

if __name__ == "__main__":
    main()
    print("Done")
