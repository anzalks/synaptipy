#!/usr/bin/env python3
"""
Advanced headless workflow video generator with simulated interactions.
Draws a virtual mouse cursor, simulates zooms, and triggers Qt dialogs.
"""

import os
import sys
import time
from pathlib import Path

# Must be set before PySide6 import
os.environ["QT_QPA_PLATFORM"] = "offscreen"

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

import imageio
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt, QTimer, QPointF, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QPen
from PySide6.QtWidgets import QApplication, QWidget, QFileDialog, QLineEdit, QPushButton

from Synaptipy.application.gui.main_window import MainWindow

_OUTPUT_DIR = _PROJECT_ROOT / "docs" / "tutorial"
_EXAMPLES_DATA = _PROJECT_ROOT / "examples" / "data"
_ABF21 = _EXAMPLES_DATA / "2023_04_11_0021.abf"

class MouseCursorOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.resize(parent.size())
        self.pos_x = parent.width() / 2
        self.pos_y = parent.height() / 2
        self.click_ripple_radius = 0
        self.click_ripple_opacity = 0.0
        self.raise_()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw ripple
        if self.click_ripple_opacity > 0:
            color = QColor(255, 0, 0, int(self.click_ripple_opacity * 255))
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(self.pos_x, self.pos_y), self.click_ripple_radius, self.click_ripple_radius)
            
        # Draw cursor (filled circle with white border)
        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QColor(255, 0, 0, 200))
        painter.drawEllipse(QPointF(self.pos_x, self.pos_y), 8, 8)
        
    def move_to(self, x, y):
        self.pos_x = x
        self.pos_y = y
        self.update()

class VideoGenerator:
    def __init__(self, window):
        self.window = window
        self.frames = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.capture_frame)
        self.timer.start(33)  # ~30 FPS

    def capture_frame(self):
        pixmap = self.window.grab()
        image = pixmap.toImage()
        width = image.width()
        height = image.height()
        ptr = image.bits()
        arr = np.array(ptr).reshape((height, width, 4))  # RGBA
        rgb_arr = arr[..., :3].copy()
        if image.format() == QImage.Format.Format_ARGB32 or image.format() == QImage.Format.Format_RGB32:
            rgb_arr = rgb_arr[..., [2, 1, 0]]
        self.frames.append(rgb_arr)

    def save_video(self, stem="workflow_demo"):
        self.timer.stop()
        print(f"Captured {len(self.frames)} frames. Saving videos...")
        
        mp4_path = _OUTPUT_DIR / f"{stem}.mp4"
        gif_path = _OUTPUT_DIR / f"{stem}.gif"
        
        # Save MP4
        print(f"Writing {mp4_path} ...")
        writer = imageio.get_writer(str(mp4_path), fps=30)
        for f in self.frames:
            writer.append_data(f)
        writer.close()
        
        # Save GIF using ffmpeg for perfect colors
        print(f"Writing {gif_path} ...")
        import subprocess
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp4_path),
            "-vf", "fps=15,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            str(gif_path)
        ], check=True)
        print("Done!")

def _pump(n=1):
    for _ in range(n):
        QApplication.processEvents()
        time.sleep(0.01)

class Choreographer:
    def __init__(self, window):
        self.window = window
        self.cursor = MouseCursorOverlay(window)
        self.cursor.show()
        
    def _get_widget_center(self, widget):
        try:
            if hasattr(widget, "getViewWidget"):
                widget = widget.getViewWidget()
            rect = widget.rect()
            pos = widget.mapTo(self.window, rect.center())
            return pos.x(), pos.y()
        except AttributeError:
            return self.window.width() // 2, self.window.height() // 2

    def move_mouse_to_pos(self, end_x, end_y, duration_frames=15):
        self.cursor.raise_()
        start_x, start_y = self.cursor.pos_x, self.cursor.pos_y
        for i in range(duration_frames):
            t = (i + 1) / duration_frames
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            self.cursor.move_to(x, y)
            _pump(1)

    def move_mouse_to(self, target_widget, duration_frames=15):
        end_x, end_y = self._get_widget_center(target_widget)
        self.move_mouse_to_pos(end_x, end_y, duration_frames)

    def click(self):
        self.cursor.raise_()
        self.cursor.click_ripple_radius = 5
        self.cursor.click_ripple_opacity = 1.0
        for i in range(10):
            self.cursor.click_ripple_radius += 2
            self.cursor.click_ripple_opacity -= 0.1
            self.cursor.update()
            _pump(1)

    def scroll_to_widget(self, target_widget):
        print(f"    - scroll_to_widget({target_widget})")
        from PySide6.QtWidgets import QScrollArea
        from PySide6.QtCore import QPoint
        parent = target_widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                content_widget = parent.widget()
                if content_widget:
                    print(f"      - scrolling parent {parent}")
                    pos = target_widget.mapTo(content_widget, QPoint(0, 0))
                    sb = parent.verticalScrollBar()
                    start_val = sb.value()
                    end_val = pos.y() - parent.viewport().height() // 2 + target_widget.height() // 2
                    end_val = max(sb.minimum(), min(sb.maximum(), end_val))
                    for i in range(15):
                        t = (i + 1) / 15.0
                        sb.setValue(int(start_val + (end_val - start_val) * t))
                        _pump(1)
                break
            parent = parent.parentWidget()
        print(f"    - finished scroll_to_widget")

def _os_is_dark() -> bool:
    """Return True when the host OS is configured for a dark colour scheme."""
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return out.lower() == "dark"
        except subprocess.CalledProcessError:
            return False
    return False

def run_choreography():
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
    app = QApplication.instance() or QApplication(sys.argv)
    from Synaptipy.shared.theme_manager import ThemeMode, apply_theme
    mode = ThemeMode.DARK if _os_is_dark() else ThemeMode.LIGHT
    apply_theme(mode)
    print(f"Applying theme: {mode.value}")
    MainWindow._offer_session_restore = lambda self: None
    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    
    vg = VideoGenerator(window)
    choreo = Choreographer(window)
    
    # 1. Idle empty state
    _pump(30)
    
    # 2. Load File
    print("Loading file...")
    window.explorer_tab.load_recording_data(_ABF21, [_ABF21], 0)
    # Turn off downsampling for high-fidelity video
    if hasattr(window.explorer_tab, "config_panel"):
        window.explorer_tab.config_panel.downsample_cb.setChecked(False)
        
    deadline = time.monotonic() + 10.0
    while getattr(window.explorer_tab, "_is_loading", False) and time.monotonic() < deadline:
        _pump(1)
    _pump(30)
    
    # 3. Zooming animation
    print("Zooming in...")
    try:
        print("  - getting plot widget")
        pw = list(window.explorer_tab.plot_canvas.channel_plots.values())[0]
        from PySide6.QtWidgets import QGraphicsRectItem
        from PySide6.QtCore import QPointF
        import pyqtgraph as pg
        
        view = pw.getViewWidget()
        view_box = pw.getViewBox()
        
        print("  - calculating coordinates")
        # Calculate screen coordinates for the zoom bounds
        start_scene = view_box.mapViewToScene(QPointF(0.150, 60.0))
        start_view = view.mapFromScene(start_scene)
        start_global = view.mapTo(window, start_view)
        
        end_scene = view_box.mapViewToScene(QPointF(0.200, -40.0))
        end_view = view.mapFromScene(end_scene)
        end_global = view.mapTo(window, end_view)
        
        print("  - moving mouse")
        # Move mouse to start of the box
        choreo.move_mouse_to_pos(start_global.x(), start_global.y(), 15)
        
        # Simulate click press
        choreo.cursor.click_ripple_radius = 5
        choreo.cursor.click_ripple_opacity = 1.0
        
        roi = QGraphicsRectItem(0.150, -40.0, 0.0, 100.0)
        roi.setPen(pg.mkPen(color=(255, 255, 0), width=2))
        roi.setBrush(QColor(255, 255, 0, 128))
        pw.addItem(roi)
        
        print("  - animating rect")
        # animate width of ROI and drag mouse
        for i in range(20):
            t = (i+1)/20.0
            roi.setRect(0.150, -40.0, 0.050 * t, 100.0)
            
            cur_x = start_global.x() + (end_global.x() - start_global.x()) * t
            cur_y = start_global.y() + (end_global.y() - start_global.y()) * t
            choreo.cursor.move_to(cur_x, cur_y)
            _pump(1)
            
        print("  - finishing zoom")
        # Simulate click release
        choreo.cursor.click_ripple_opacity = 0.0
        choreo.cursor.update()
        _pump(10)
        
        # Apply zoom and remove ROI
        pw.setXRange(0.150, 0.200, padding=0)
        pw.setYRange(-40.0, 60.0, padding=0)
        pw.removeItem(roi)
        _pump(30)
        print("  - zoom completed")
    except Exception as e:
        print("Zoom failed:", e)
        
    window.session_manager.selected_analysis_items = [{"path": _ABF21, "target_type": "Recording", "trial_index": None}]
    
    # 4. Switch to Analyser Tab
    print("Switching to Analyser...")
    tab_bar = window.tab_widget.tabBar()
    choreo.move_mouse_to(tab_bar)
    choreo.click()
    window.tab_widget.setCurrentIndex(1)
    _pump(30)
    
    analyser = window.analyser_tab
    for i in range(analyser.sub_tab_widget.count()):
        if analyser.sub_tab_widget.tabText(i) == "Spike Analysis":
            analyser.sub_tab_widget.setCurrentIndex(i)
            break
            
    tab = analyser.sub_tab_widget.currentWidget()
    deadline = time.monotonic() + 10.0
    while not tab.isEnabled() and time.monotonic() < deadline:
        _pump(1)
    _pump(30)
    
    def get_widget(name):
        pg = getattr(tab, "param_generator", None)
        if pg: return pg.widgets.get(name)
        return None
        
    # Set Trial to 17
    print("Setting data source to Trial 17...")
    cb = getattr(tab, "data_source_combobox", None)
    if cb:
        choreo.move_mouse_to(cb)
        choreo.click()
        cb.showPopup()
        _pump(15)
        for i in range(cb.count()):
            if cb.itemData(i) == 17:
                cb.setCurrentIndex(i)
                break
        cb.hidePopup()
        _pump(15)
        
    # Tinkering with Refractory Period
    print("Adjusting refractory period...")
    ref_widget = get_widget("refractory_period")
    for val in [0.020, 0.002]:
        if ref_widget:
            print(f"Scrolling to refractory period ({val})...")
            choreo.scroll_to_widget(ref_widget)
            choreo.move_mouse_to(ref_widget)
            choreo.click()
            ref_widget.setValue(val)
            _pump(10)
        
        # Click Run
        run_btn = getattr(tab, "run_button", None)
        if run_btn is None:
            for btn in tab.findChildren(QPushButton):
                if "Run" in btn.text():
                    run_btn = btn
                    break
                    
        if run_btn:
            choreo.scroll_to_widget(run_btn)
            choreo.move_mouse_to(run_btn)
            choreo.click()
            if hasattr(tab, "_trigger_analysis"):
                tab._trigger_analysis()
            
        # Wait for spikes to appear (wait 2 seconds for worker thread to finish plotting)
        _pump(60) 
        
    # Click Reset View to show all scatters
    reset_btn = None
    for btn in tab.findChildren(QPushButton):
        if btn.text() and "Reset View" in btn.text():
            reset_btn = btn
            break
            
    if reset_btn:
        choreo.scroll_to_widget(reset_btn)
        choreo.move_mouse_to(reset_btn)
        choreo.click()
        reset_btn.click()
        _pump(40)
        
    # Click Save Result
    save_btn = getattr(tab, "save_button", None)
    if not save_btn:
        for btn in tab.findChildren(QPushButton):
            if btn.text() and "Save" in btn.text() and "Result" in btn.text():
                save_btn = btn
                break
                
    if save_btn:
        choreo.scroll_to_widget(save_btn)
        choreo.move_mouse_to(save_btn)
        choreo.click()
        save_btn.click()
        _pump(30)
        
    # 5. Switch to Exporter Tab
    print("Switching to Exporter...")
    
    # We first click the main tab bar for Exporter
    rect = window.tab_widget.tabBar().tabRect(2)
    pos = window.tab_widget.tabBar().mapTo(window, rect.center())
    choreo.move_mouse_to_pos(pos.x(), pos.y(), 15)
    choreo.click()
    window.tab_widget.setCurrentIndex(2)
    _pump(30)
    
    exporter = window.exporter_tab
    
    # Switch to Analysis Results sub-tab visually by clicking the tab
    sub_rect = exporter.sub_tab_widget.tabBar().tabRect(1)
    sub_pos = exporter.sub_tab_widget.tabBar().mapTo(window, sub_rect.center())
    choreo.move_mouse_to_pos(sub_pos.x(), sub_pos.y(), 15)
    choreo.click()
    exporter.sub_tab_widget.setCurrentIndex(1)
    _pump(30)
    
    # Click Refresh
    refresh_btn = exporter.analysis_results_refresh_button
    choreo.move_mouse_to(refresh_btn)
    choreo.click()
    refresh_btn.click()
    _pump(30)
    
    # Click Select All
    sel_all_btn = exporter.analysis_results_select_all_button
    choreo.move_mouse_to(sel_all_btn)
    choreo.click()
    sel_all_btn.click()
    _pump(15)
    
    # Click Export
    export_btn = exporter.analysis_results_export_button
    choreo.move_mouse_to(export_btn)
    choreo.click()
        
    def handle_dialog():
        print("Handling dialog...")
        from PySide6.QtWidgets import QFileDialog, QLineEdit, QPushButton
        active = QApplication.activeModalWidget()
        print(f"Active modal: {active}")
        if active and isinstance(active, QFileDialog):
            print("Is file dialog!")
            # We need to simulate typing
            line_edits = active.findChildren(QLineEdit)
            if line_edits:
                print("Found line edits, typing...")
                # Animate typing
                text = "detected_spikes.csv"
                for i in range(len(text)):
                    line_edits[0].setText(text[:i+1])
                    _pump(2)
            _pump(10)
            # Find Save/Open/Choose button
            for b in active.findChildren(QPushButton):
                if b.text() and ("Save" in b.text() or "Open" in b.text() or "Choose" in b.text()):
                    print(f"Clicking save button: {b.text()}")
                    choreo.move_mouse_to(b)
                    choreo.click()
                    b.click()
                    break
            print("Accepting dialog...")
            active.accept()
        else:
            print("No active QFileDialog found!")
            
    print("Clicking export button...")
    
    from PySide6.QtCore import QTimer
    QTimer.singleShot(1000, handle_dialog)
    export_btn.click() # triggers modal dialog
    
    _pump(60)
    vg.save_video()

if __name__ == "__main__":
    run_choreography()
