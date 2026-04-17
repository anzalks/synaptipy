#!/usr/bin/env python3
"""
Headless screenshot capture for Synaptipy documentation.

Each run:
  1. Launches MainWindow using the offscreen Qt platform (no display required).
  2. Captures the Explorer, Analyser overview, every analysis module tab,
     every per-method view inside each module tab, and the Exporter tab.
  3. Removes any PNG in the output directory that was NOT produced this run
     (stale files from old tab layouts are deleted automatically).

Usage::

    python scripts/capture_screenshots.py
    python scripts/capture_screenshots.py --output-dir /custom/path

Exit codes:
  0 - all screenshots written successfully
  1 - one or more screenshots failed
"""

import argparse
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import List, Optional

# ---------------------------------------------------------------------------
# Must be set before the first PySide6 import.
# ---------------------------------------------------------------------------
if "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent

# Put src/ on the path so the editable install is not required.
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

_DEFAULT_OUTPUT_DIR = _PROJECT_ROOT / "docs" / "tutorial" / "screenshots"
_WINDOW_W = 1280
_WINDOW_H = 800


# ---------------------------------------------------------------------------
# Theme detection (must happen before Qt palette is initialised)
# ---------------------------------------------------------------------------


def _os_is_dark() -> bool:
    """
    Return *True* when the host OS is in dark mode.

    Uses native system queries so the result is correct even when Qt runs
    on the *offscreen* platform (which always initialises a light palette and
    therefore makes Qt's own palette-luminance heuristic unreliable).
    """
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return out.lower() == "dark"
        except subprocess.CalledProcessError:
            # Key absent == Light mode
            return False
        except Exception:
            return False

    if sys.platform == "win32":
        try:
            import winreg  # noqa: PLC0415

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return value == 0  # 0 = dark
        except Exception:
            return False

    # Linux: check GTK / colour-scheme hints
    try:
        out = subprocess.check_output(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return "dark" in out.lower()
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pump(n: int = 3) -> None:
    """Pump the Qt event queue *n* times to let widgets paint."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    for _ in range(n):
        QApplication.processEvents()


def _safe_name(text: str) -> str:
    """Convert a display label to a filesystem-safe lowercase stem."""
    return (
        text.lower()
        .replace(" ", "_")
        .replace("/", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace("+", "")
    )


def _grab(widget, dest: Path) -> None:
    """Capture *widget* to *dest* as a PNG file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    pixmap.save(str(dest), "PNG")
    print(f"  [ok] {dest.name}")


# ---------------------------------------------------------------------------
# Capture logic (split into small functions to keep complexity low)
# ---------------------------------------------------------------------------


def _capture_top_level(window, output_dir: Path) -> List[str]:
    """Capture Explorer, Analyser overview, and Exporter tabs."""
    captured: List[str] = []

    # Explorer
    window.tab_widget.setCurrentIndex(0)
    _pump()
    _grab(window, output_dir / "explorer_tab.png")
    captured.append("explorer_tab.png")

    # Analyser overview
    window.tab_widget.setCurrentIndex(1)
    _pump()
    _grab(window, output_dir / "analyser_tab.png")
    captured.append("analyser_tab.png")

    # Exporter
    window.tab_widget.setCurrentIndex(2)
    _pump()
    _grab(window, output_dir / "exporter_tab.png")
    captured.append("exporter_tab.png")

    return captured


def _capture_method_views(
    sub_tab,
    module_safe: str,
    window,
    output_dir: Path,
) -> List[str]:
    """Cycle through each method in *sub_tab*'s combobox and capture."""
    captured: List[str] = []
    cb: Optional[object] = getattr(sub_tab, "method_combobox", None)
    if cb is None:
        return captured

    original_index = cb.currentIndex()  # type: ignore[attr-defined]
    for j in range(cb.count()):  # type: ignore[attr-defined]
        cb.setCurrentIndex(j)  # type: ignore[attr-defined]
        _pump()
        method_label: str = cb.currentText()  # type: ignore[attr-defined]
        method_safe = _safe_name(method_label)
        fname = f"analyser_{module_safe}_{method_safe}.png"
        _grab(window, output_dir / fname)
        captured.append(fname)

    cb.setCurrentIndex(original_index)  # type: ignore[attr-defined]
    _pump()
    return captured


def _capture_analyser_sub_tabs(window, output_dir: Path) -> List[str]:
    """Capture all analysis module tabs and their per-method views."""
    captured: List[str] = []
    analyser = window.analyser_tab
    if not (hasattr(analyser, "sub_tab_widget") and analyser.sub_tab_widget):
        return captured

    tab_widget = analyser.sub_tab_widget
    window.tab_widget.setCurrentIndex(1)  # keep Analyser tab active
    _pump()

    for i in range(tab_widget.count()):
        tab_widget.setCurrentIndex(i)
        _pump()

        module_label: str = tab_widget.tabText(i)
        module_safe = _safe_name(module_label)

        # Module-level overview screenshot
        fname = f"analyser_{module_safe}.png"
        _grab(window, output_dir / fname)
        captured.append(fname)

        # Per-method screenshots
        sub_tab = tab_widget.widget(i)
        captured.extend(_capture_method_views(sub_tab, module_safe, window, output_dir))

    return captured


def _remove_stale(output_dir: Path, captured: List[str]) -> None:
    """Delete PNGs in *output_dir* that are not in the captured set."""
    captured_set = set(captured)
    removed: List[str] = []
    for png in output_dir.glob("*.png"):
        if png.name not in captured_set:
            png.unlink()
            removed.append(png.name)

    if removed:
        print(f"\n[cleanup] Removed {len(removed)} stale screenshot(s):")
        for name in removed:
            print(f"  - {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run(output_dir: Path) -> bool:  # noqa: C901
    """Execute the full capture pipeline. Return *True* on success."""
    from PySide6.QtCore import QTimer  # noqa: PLC0415
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    from Synaptipy.application.gui.main_window import MainWindow  # noqa: PLC0415

    captured: List[str] = []
    success = False

    app = QApplication.instance() or QApplication(sys.argv)

    # Apply the Synaptipy theme that matches the host OS appearance so that
    # screenshots look identical to what users see on their own machine.
    # ThemeMode.SYSTEM cannot be used here because the offscreen Qt platform
    # always starts with a light system palette, causing dark-mode systems to
    # render light screenshots incorrectly.
    from Synaptipy.shared.theme_manager import ThemeMode, apply_theme  # noqa: PLC0415

    target_theme = ThemeMode.DARK if _os_is_dark() else ThemeMode.LIGHT
    apply_theme(target_theme)
    print(f"[theme] {target_theme.value}")

    try:
        # Load built-in analyses then example/user plugins so that plugin
        # tabs (e.g. Synaptic Charge AUC) appear in the Analyser before the
        # MainWindow UI is constructed.
        import Synaptipy.core.analysis  # noqa: F401 — registers built-ins
        from Synaptipy.application.plugin_manager import PluginManager  # noqa: PLC0415

        PluginManager.load_plugins()

        window = MainWindow()
        window.resize(_WINDOW_W, _WINDOW_H)
        window.show()
        _pump(5)

        captured.extend(_capture_top_level(window, output_dir))
        captured.extend(_capture_analyser_sub_tabs(window, output_dir))

        window.close()
        _pump(2)
        success = True

    except Exception:
        print("[ERROR] Screenshot capture raised an exception:", file=sys.stderr)
        traceback.print_exc()
        success = False

    if success and captured:
        _remove_stale(output_dir, captured)
        print(f"\n[done] {len(captured)} screenshot(s) written to: {output_dir}")
    elif not captured:
        print("[WARN] No screenshots were captured.", file=sys.stderr)
        success = False

    QTimer.singleShot(0, app.quit)
    app.exec()
    return success


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Capture Synaptipy docs screenshots headlessly.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        metavar="PATH",
        help="Destination directory for PNG files " "(default: docs/tutorial/screenshots/).",
    )
    args = parser.parse_args()
    return 0 if run(args.output_dir) else 1


if __name__ == "__main__":
    sys.exit(main())
