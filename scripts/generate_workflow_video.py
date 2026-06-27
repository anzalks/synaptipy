import os
import sys
import time
from pathlib import Path

import imageio
import numpy as np
from PySide6.QtCore import QPoint, QPointF, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGraphicsRectItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QWidget,
)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_MAC_WANTS_LAYER"] = "1"

from synaptipy.application.gui.main_window import MainWindow

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ABF21 = _PROJECT_ROOT / "examples" / "data" / "2023_04_11_0021.abf"
_OUTPUT_DIR = _PROJECT_ROOT / "docs" / "tutorial"

global_vg = None


def _pump(n_frames=1):
    """Process UI events and capture one frame synchronously."""
    for _ in range(n_frames):
        QApplication.processEvents()
        if global_vg is not None:
            global_vg.capture_frame()
        time.sleep(0.01)


class VideoGenerator:
    def __init__(self, window):
        self.window = window
        self.frames = []

    def capture_frame(self):
        pixmap = self.window.grab()
        image = pixmap.toImage()
        width = image.width()
        height = image.height()
        ptr = image.bits()
        arr = np.array(ptr).reshape((height, width, 4))
        rgb_arr = arr[..., :3].copy()
        if image.format() in (QImage.Format.Format_ARGB32, QImage.Format.Format_RGB32):
            rgb_arr = rgb_arr[..., [2, 1, 0]]
        self.frames.append(rgb_arr)

    def save_video(self, stem="workflow_demo"):
        print(f"Captured {len(self.frames)} frames. Saving videos...")
        mp4_path = _OUTPUT_DIR / f"{stem}.mp4"
        gif_path = _OUTPUT_DIR / f"{stem}.gif"

        print(f"Writing {mp4_path} ...")
        writer = imageio.get_writer(str(mp4_path), fps=30)
        for f in self.frames:
            writer.append_data(f)
        writer.close()

        print(f"Writing {gif_path} ...")
        import subprocess

        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(mp4_path),
                "-vf",
                "fps=15,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                str(gif_path),
            ],
            check=True,
        )
        print("Done!")


class FakeCursor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.resize(parent.size() if parent else QSize(1280, 800))
        self.pos_x = self.width() // 2
        self.pos_y = self.height() // 2
        self.click_ripple_radius = 0
        self.click_ripple_opacity = 0.0

    def move_to(self, x, y):
        self.pos_x = x
        self.pos_y = y
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.click_ripple_opacity > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 0, int(150 * self.click_ripple_opacity)))
            painter.drawEllipse(
                QPoint(int(self.pos_x), int(self.pos_y)), self.click_ripple_radius, self.click_ripple_radius
            )

        painter.setPen(QPen(QColor(255, 255, 255), 2))
        painter.setBrush(QColor(0, 0, 0))
        pts = [
            QPoint(int(self.pos_x), int(self.pos_y)),
            QPoint(int(self.pos_x) + 12, int(self.pos_y) + 12),
            QPoint(int(self.pos_x) + 4, int(self.pos_y) + 12),
            QPoint(int(self.pos_x), int(self.pos_y) + 18),
        ]
        painter.drawPolygon(pts)


class Choreographer:
    def __init__(self, window):
        self.window = window
        self.cursor = FakeCursor(window)
        self.cursor.show()
        self.cursor.raise_()

    def move_mouse_to_pos(self, end_x, end_y, duration_frames=15):
        self.cursor.raise_()
        start_x, start_y = self.cursor.pos_x, self.cursor.pos_y
        for i in range(duration_frames):
            t = (i + 1) / duration_frames
            x = start_x + (end_x - start_x) * t
            y = start_y + (end_y - start_y) * t
            self.cursor.move_to(x, y)
            _pump(1)

    def _get_widget_center(self, widget):
        try:
            if hasattr(widget, "getViewWidget"):
                widget = widget.getViewWidget()
            rect = widget.rect()
            pos = widget.mapTo(self.window, rect.center())
            return pos.x(), pos.y()
        except AttributeError:
            return self.window.width() // 2, self.window.height() // 2

    def move_mouse_to(self, target_widget, duration_frames=15):
        end_x, end_y = self._get_widget_center(target_widget)
        self.move_mouse_to_pos(end_x, end_y, duration_frames)

    def click(self):
        for i in range(5):
            self.cursor.click_ripple_radius = 5 + i * 2
            self.cursor.click_ripple_opacity = 1.0 - (i / 5.0)
            self.cursor.update()
            _pump(1)
        self.cursor.click_ripple_opacity = 0.0
        self.cursor.update()
        _pump(1)

    def scroll_to_widget(self, target_widget):
        parent = target_widget.parentWidget()
        while parent is not None:
            if isinstance(parent, QScrollArea):
                content_widget = parent.widget()
                if content_widget:
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


def _os_is_dark() -> bool:
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
            pass
    return False


def run_choreography():
    global global_vg

    QApplication.setAttribute(Qt.ApplicationAttribute.AA_UseHighDpiPixmaps)
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)

    app = QApplication.instance() or QApplication(sys.argv)

    from synaptipy.shared.theme_manager import ThemeMode, apply_theme

    mode = ThemeMode.DARK if _os_is_dark() else ThemeMode.LIGHT
    apply_theme(mode)
    print(f"Theme selected: {mode.value}")

    MainWindow._offer_session_restore = lambda self: None
    window = MainWindow()
    window.resize(1280, 800)
    window.show()

    global_vg = VideoGenerator(window)
    choreo = Choreographer(window)

    _pump(15)

    # --- 1. EXPLORER TAB ---
    print("Loading file...")
    window.explorer_tab.load_recording_data(_ABF21, [_ABF21], 0)
    if hasattr(window.explorer_tab, "config_panel"):
        window.explorer_tab.config_panel.downsample_cb.setChecked(False)

    deadline = time.monotonic() + 10.0
    while getattr(window.explorer_tab, "_is_loading", False) and time.monotonic() < deadline:
        _pump(1)
    _pump(30)

    print("Simulating zoom...")
    try:
        pw = list(window.explorer_tab.plot_canvas.channel_plots.values())[0]
        import pyqtgraph as pg

        view = pw.getViewWidget()
        view_box = pw.getViewBox()

        start_scene = view_box.mapViewToScene(QPointF(0.150, 60.0))
        start_view = view.mapFromScene(start_scene)
        start_global = view.mapTo(window, start_view)

        end_scene = view_box.mapViewToScene(QPointF(0.200, -40.0))
        end_view = view.mapFromScene(end_scene)
        end_global = view.mapTo(window, end_view)

        choreo.move_mouse_to_pos(start_global.x(), start_global.y(), 15)

        choreo.cursor.click_ripple_radius = 5
        choreo.cursor.click_ripple_opacity = 1.0

        roi = QGraphicsRectItem(0.150, -40.0, 0.0, 100.0)
        roi.setPen(pg.mkPen(color=(255, 255, 0), width=2))
        roi.setBrush(QColor(255, 255, 0, 128))
        pw.addItem(roi)

        for i in range(20):
            t = (i + 1) / 20.0
            roi.setRect(0.150, -40.0, 0.050 * t, 100.0)
            cur_x = start_global.x() + (end_global.x() - start_global.x()) * t
            cur_y = start_global.y() + (end_global.y() - start_global.y()) * t
            choreo.cursor.move_to(cur_x, cur_y)
            _pump(1)

        choreo.cursor.click_ripple_opacity = 0.0
        choreo.cursor.update()
        _pump(10)

        pw.setXRange(0.150, 0.200, padding=0)
        pw.setYRange(-40.0, 60.0, padding=0)
        pw.removeItem(roi)
        _pump(30)
    except Exception as e:
        print("Zoom animation failed:", e)

    # Inject recording into session
    window.session_manager.selected_analysis_items = [{"path": _ABF21, "target_type": "Recording", "trial_index": None}]

    # --- 2. ANALYSER TAB ---
    print("Switching to Analyser...")
    rect = window.tab_widget.tabBar().tabRect(1)
    pos = window.tab_widget.tabBar().mapTo(window, rect.center())
    choreo.move_mouse_to_pos(pos.x(), pos.y(), 15)
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

    # Change Trial to 17
    print("Setting Data Source to Trial 17")
    cb = getattr(tab, "data_source_combobox", None)
    if cb:
        choreo.move_mouse_to(cb)
        choreo.click()
        for i in range(cb.count()):
            if cb.itemData(i) == 17:
                cb.setCurrentIndex(i)
                break
        _pump(15)

    # Adjust Refractory Period
    print("Adjusting Refractory Period")
    ref_widget = None
    pg_obj = getattr(tab, "param_generator", None)
    if pg_obj:
        ref_widget = pg_obj.widgets.get("refractory_period")

    for val in [0.020, 0.002]:
        if ref_widget:
            choreo.scroll_to_widget(ref_widget)
            choreo.move_mouse_to(ref_widget)
            choreo.click()
            ref_widget.setValue(val)
            _pump(15)

    # Click Save Result
    print("Clicking Save Result")
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

    # --- 3. EXPORTER TAB ---
    print("Switching to Exporter...")
    rect = window.tab_widget.tabBar().tabRect(2)
    pos = window.tab_widget.tabBar().mapTo(window, rect.center())
    choreo.move_mouse_to_pos(pos.x(), pos.y(), 15)
    choreo.click()
    window.tab_widget.setCurrentIndex(2)
    _pump(30)

    exporter = window.exporter_tab
    sub_rect = exporter.sub_tab_widget.tabBar().tabRect(1)
    sub_pos = exporter.sub_tab_widget.tabBar().mapTo(window, sub_rect.center())
    choreo.move_mouse_to_pos(sub_pos.x(), sub_pos.y(), 15)
    choreo.click()
    exporter.sub_tab_widget.setCurrentIndex(1)
    _pump(30)

    print("Refreshing results")
    refresh_btn = getattr(exporter, "analysis_results_refresh_button", None)
    if refresh_btn:
        choreo.move_mouse_to(refresh_btn)
        choreo.click()
        refresh_btn.click()
        _pump(30)

    print("Selecting all")
    sel_all_btn = getattr(exporter, "analysis_results_select_all_button", None)
    if sel_all_btn:
        choreo.move_mouse_to(sel_all_btn)
        choreo.click()
        sel_all_btn.click()
        _pump(15)

    print("Exporting...")
    export_btn = getattr(exporter, "analysis_results_export_button", None)
    if export_btn:
        choreo.move_mouse_to(export_btn)
        choreo.click()

        def handle_modals():
            active = QApplication.activeModalWidget()
            if active and isinstance(active, QFileDialog):
                print("Intercepted QFileDialog!")
                line_edits = active.findChildren(QLineEdit)
                if line_edits:
                    text = "detected_spikes.csv"
                    for i in range(len(text)):
                        line_edits[0].setText(text[: i + 1])
                        _pump(2)
                _pump(10)

                for b in active.findChildren(QPushButton):
                    if b.text() and ("Save" in b.text() or "Open" in b.text() or "Choose" in b.text()):
                        choreo.move_mouse_to(b)
                        choreo.click()
                        b.click()
                        break
                active.accept()
                QTimer.singleShot(200, handle_msgbox)

        def handle_msgbox():
            msg_active = QApplication.activeModalWidget()
            if msg_active and isinstance(msg_active, QMessageBox):
                print("Intercepted QMessageBox!")
                msg_active.accept()

        QTimer.singleShot(500, handle_modals)
        export_btn.click()

    _pump(60)
    global_vg.save_video()


if __name__ == "__main__":
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    run_choreography()
