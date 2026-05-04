#!/usr/bin/env python3
"""
Headless screenshot capture for Synaptipy documentation.

Each run:
  1. Launches MainWindow using the offscreen Qt platform (no display required).
  2. Loads real example electrophysiology files and configures specific
     analysis scenarios so that every screenshot reflects genuine data.
  3. Captures the Explorer tab (multi-trial and multichannel views), the
     Analyser tab (all five core module tabs with relevant methods and
     parameters), popup plots produced by analyses (I-V curve, F-I curve,
     phase plane), and the Exporter tab.
  4. Removes any PNG in the output directory that was NOT produced this run.

Example data used
-----------------
- ``2023_04_11_0021.abf`` -- single-channel current-clamp, 20 trials, 500 ms,
  action potentials; used for spike analysis, excitability, phase plane.
- ``2023_04_11_0022.abf`` -- four channels (IN0, FrameTTL, Photodiode, Field),
  3 trials, 17.1 s; used for evoked-response (optogenetics) and synaptic-event
  screenshots.
- ``240326_003.wcp``      -- single-channel voltage-clamp (Im0, pA), 42 trials,
  981.7 ms; used for intrinsic-property screenshots (Rin, tau, capacitance,
  I-V curve, baseline RMP).

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
import time
import traceback
from pathlib import Path
from typing import Any, List, Optional, Tuple

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
_EXAMPLES_DATA = _PROJECT_ROOT / "examples" / "data"
_WINDOW_W = 1280
_WINDOW_H = 800

# Paths to example recordings bundled with the repository.
_ABF21 = _EXAMPLES_DATA / "2023_04_11_0021.abf"  # current-clamp, action potentials
_ABF22 = _EXAMPLES_DATA / "2023_04_11_0022.abf"  # multichannel, optogenetics
_WCP03 = _EXAMPLES_DATA / "240326_003.wcp"  # voltage-clamp, intrinsic properties

# Chan IDs as returned by NeoAdapter (numeric string keys, zero-indexed):
#   ABF21: '0' = IN0 (mV)
#   ABF22: '0' = IN0 (mV), '1' = FrameTTL (mV), '2' = Photodiode (mV), '3' = Field (mV)
#   WCP03: '0' = Im0 (pA)


# ---------------------------------------------------------------------------
# Theme detection (must happen before Qt palette is initialised)
# ---------------------------------------------------------------------------


def _os_is_dark() -> bool:
    """Return True when the host OS is configured for a dark colour scheme."""
    if sys.platform == "darwin":
        try:
            out = subprocess.check_output(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            return out.lower() == "dark"
        except subprocess.CalledProcessError:
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
            return value == 0
        except Exception:
            return False

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
# Low-level helpers
# ---------------------------------------------------------------------------


def _pump(n: int = 5) -> None:
    """Drain the Qt event queue *n* times so widgets repaint."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    for _ in range(n):
        QApplication.processEvents()


def _wait_explorer_load(explorer: Any, timeout_s: float = 15.0) -> None:
    """Poll until the Explorer tab finishes its background file load."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    # Brief initial pump to allow the load to start.
    _pump(3)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if not getattr(explorer, "_is_loading", False):
            break
        time.sleep(0.05)
    # Extra draining to allow deferred paint events to execute.
    _pump(20)


def _wait_data_load(tab: Any, timeout_s: float = 15.0) -> None:
    """Poll until an analysis tab re-enables itself after async data loading."""
    from PySide6.QtWidgets import QApplication  # noqa: PLC0415

    # Brief initial pump so that any disable() call from _on_analysis_item_selected
    # has already propagated before we start polling.
    _pump(3)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if tab.isEnabled():
            break
        time.sleep(0.05)
    _pump(5)


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


def _grab(widget: Any, dest: Path) -> None:
    """Capture *widget* to *dest* as a PNG file, creating parent dirs as needed."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    pixmap = widget.grab()
    pixmap.save(str(dest), "PNG")
    print(f"  [ok] {dest.name}")


# ---------------------------------------------------------------------------
# Data-loading helpers
# ---------------------------------------------------------------------------


def _load_explorer(window: Any, path: Path, file_list: List[Path], index: int) -> None:
    """Load *path* into the Explorer tab and wait for the background thread."""
    window.tab_widget.setCurrentIndex(0)
    _pump(3)
    window.explorer_tab.load_recording_data(path, file_list, index)
    _wait_explorer_load(window.explorer_tab)


def _set_analysis_source(sm: Any, path: Path) -> None:
    """Set a single-file analysis source in SessionManager.

    This populates each sub-tab's internal analysis-items list via the
    ``selected_analysis_items_changed`` signal chain.  The data load itself is
    deferred and must be awaited via ``_wait_data_load`` after switching to the
    target sub-tab.
    """
    sm.selected_analysis_items = [{"path": path, "target_type": "Recording", "trial_index": None}]
    _pump(5)


# ---------------------------------------------------------------------------
# Analyser-tab helpers
# ---------------------------------------------------------------------------


def _find_sub_tab(analyser: Any, label: str) -> Tuple[int, Optional[Any]]:
    """Return the (index, widget) of the sub-tab whose display label matches *label*."""
    tw = analyser.sub_tab_widget
    for i in range(tw.count()):
        if tw.tabText(i) == label:
            return i, tw.widget(i)
    return -1, None


def _activate_sub_tab(window: Any, analyser: Any, label: str) -> Optional[Any]:
    """Switch to the Analyser top tab, then to the named sub-tab.

    Switching the sub-tab index triggers ``_on_tab_changed`` which starts an
    asynchronous data load for the newly visible tab.  This function waits for
    that load to complete before returning.
    """
    window.tab_widget.setCurrentIndex(1)
    _pump(3)
    idx, tab = _find_sub_tab(analyser, label)
    if idx < 0 or tab is None:
        print(f"  [warn] sub-tab '{label}' not found", file=sys.stderr)
        return None
    analyser.sub_tab_widget.setCurrentIndex(idx)
    _wait_data_load(tab)
    return tab


def _set_method(tab: Any, method_label: str) -> None:
    """Switch the method-selector combobox to *method_label* and drain the event queue."""
    cb = getattr(tab, "method_combobox", None)
    if cb is None:
        return
    cb.setCurrentText(method_label)
    _pump(5)


def _set_channel(tab: Any, chan_id: str) -> None:
    """Select the channel whose userData equals *chan_id* in the signal-channel combobox."""
    cb = getattr(tab, "signal_channel_combobox", None)
    if cb is None:
        return
    for i in range(cb.count()):
        if cb.itemData(i) == chan_id:
            cb.setCurrentIndex(i)
            _pump(3)
            return


def _set_param(tab: Any, name: str, value: Any) -> None:
    """Set a scalar parameter widget by name via the tab's param_generator."""
    pg = getattr(tab, "param_generator", None)
    if pg is None:
        return
    widget = pg.widgets.get(name)
    if widget is None:
        return
    if hasattr(widget, "setValue"):
        widget.setValue(value)
    elif hasattr(widget, "setCurrentText"):
        widget.setCurrentText(str(value))
    _pump(2)


def _set_trial(tab: Any, trial_index: int) -> None:
    """Select a single trial by 0-based index in the data-source combobox.

    Has no effect when the combobox is absent or does not contain a matching
    entry (e.g. when the tab is configured for multi-trial analysis).
    """
    cb = getattr(tab, "data_source_combobox", None)
    if cb is None:
        return
    for i in range(cb.count()):
        if cb.itemData(i) == trial_index:
            cb.setCurrentIndex(i)
            _pump(3)
            return


def _run_analysis(tab: Any) -> None:
    """Call _trigger_analysis directly (bypassing the debounce timer)."""
    if hasattr(tab, "_trigger_analysis"):
        try:
            tab._trigger_analysis()
        except Exception as exc:
            print(f"  [warn] analysis raised: {exc}", file=sys.stderr)
    _pump(10)


def _grab_popups(tab: Any, dest_stem: str, output_dir: Path) -> List[str]:
    """Capture any popup windows created by the last analysis run."""
    captured: List[str] = []
    popups: List[Any] = getattr(tab, "_popup_windows", [])
    for i, popup in enumerate(popups):
        if popup is None:
            continue
        suffix = "" if i == 0 else f"_{i}"
        fname = f"{dest_stem}_popup{suffix}.png"
        _grab(popup, output_dir / fname)
        captured.append(fname)
    return captured


# ---------------------------------------------------------------------------
# Explorer screenshots
# ---------------------------------------------------------------------------


def _capture_explorer_screenshots(window: Any, output_dir: Path) -> List[str]:
    """Load each example recording into the Explorer and capture the result."""
    captured: List[str] = []

    abf21_files = [_ABF21]
    abf22_files = [_ABF22]
    wcp_files = [_WCP03]

    # Single-channel current-clamp with action potentials - primary tutorial screenshot.
    if _ABF21.exists():
        _load_explorer(window, _ABF21, abf21_files, 0)
        _pump(5)
        _grab(window, output_dir / "explorer_tab.png")
        captured.append("explorer_tab.png")

    # Multichannel recording (four channels) - demonstrates channel stacking.
    if _ABF22.exists():
        _load_explorer(window, _ABF22, abf22_files, 0)
        _pump(5)
        _grab(window, output_dir / "explorer_tab_multichannel.png")
        captured.append("explorer_tab_multichannel.png")

    # Voltage-clamp single-channel recording.
    if _WCP03.exists():
        _load_explorer(window, _WCP03, wcp_files, 0)
        _pump(5)
        _grab(window, output_dir / "explorer_tab_voltageclamp.png")
        captured.append("explorer_tab_voltageclamp.png")

    return captured


# ---------------------------------------------------------------------------
# Intrinsic Properties screenshots (WCP voltage-clamp file)
# ---------------------------------------------------------------------------


def _capture_intrinsic_properties(window: Any, analyser: Any, sm: Any, output_dir: Path) -> List[str]:
    """Capture the Intrinsic Properties tab with the voltage-clamp example file."""
    captured: List[str] = []
    if not _WCP03.exists():
        return captured

    _set_analysis_source(sm, _WCP03)

    tab = _activate_sub_tab(window, analyser, "Intrinsic Properties")
    if tab is None:
        return captured

    # Module-level overview with default method.
    _grab(window, output_dir / "analyser_intrinsic_properties.png")
    captured.append("analyser_intrinsic_properties.png")

    # ---- Baseline (RMP) ----
    _set_method(tab, "Baseline (RMP)")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_baseline_rmp.png")
    captured.append("analyser_intrinsic_properties_baseline_rmp.png")
    captured.extend(_grab_popups(tab, "analyser_intrinsic_properties_baseline_rmp", output_dir))

    # ---- Input Resistance ----
    _set_method(tab, "Input Resistance")
    # Baseline: 0-40 ms; response window: 50-80 ms (matching the -10 pA current step).
    _set_param(tab, "baseline_end", 0.04)
    _set_param(tab, "response_start", 0.05)
    _set_param(tab, "response_end", 0.08)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_input_resistance.png")
    captured.append("analyser_intrinsic_properties_input_resistance.png")

    # ---- Tau (Time Constant) ----
    _set_method(tab, "Tau (Time Constant)")
    _set_param(tab, "stim_start_time", 0.05)
    _set_param(tab, "fit_duration", 0.03)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_tau_time_constant.png")
    captured.append("analyser_intrinsic_properties_tau_time_constant.png")

    # ---- Capacitance ----
    _set_method(tab, "Capacitance")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_capacitance.png")
    captured.append("analyser_intrinsic_properties_capacitance.png")

    # ---- I-V Curve (produces a popup scatter plot) ----
    _set_method(tab, "I-V Curve")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_i-v_curve.png")
    captured.append("analyser_intrinsic_properties_i-v_curve.png")
    captured.extend(_grab_popups(tab, "analyser_intrinsic_properties_i-v_curve", output_dir))

    # ---- Sag Ratio (Ih) ----
    _set_method(tab, "Sag Ratio (Ih)")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_intrinsic_properties_sag_ratio_ih.png")
    captured.append("analyser_intrinsic_properties_sag_ratio_ih.png")

    return captured


# ---------------------------------------------------------------------------
# Spike Analysis screenshots (ABF21 current-clamp with action potentials)
# ---------------------------------------------------------------------------


def _capture_spike_analysis(window: Any, analyser: Any, sm: Any, output_dir: Path) -> List[str]:
    """Capture the Spike Analysis tab with the single-channel action-potential file."""
    captured: List[str] = []
    if not _ABF21.exists():
        return captured

    _set_analysis_source(sm, _ABF21)

    tab = _activate_sub_tab(window, analyser, "Spike Analysis")
    if tab is None:
        return captured

    _grab(window, output_dir / "analyser_spike_analysis.png")
    captured.append("analyser_spike_analysis.png")

    # ---- Spike Detection (Trial 18 = index 17 shows clear APs) ----
    _set_method(tab, "Spike Detection")
    _set_param(tab, "threshold", -20.0)
    _set_trial(tab, 17)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_spike_analysis_spike_detection.png")
    captured.append("analyser_spike_analysis_spike_detection.png")

    # ---- Phase Plane (produces a popup dV/dt vs V plot) ----
    _set_method(tab, "Phase Plane")
    _set_trial(tab, 17)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_spike_analysis_phase_plane.png")
    captured.append("analyser_spike_analysis_phase_plane.png")
    captured.extend(_grab_popups(tab, "analyser_spike_analysis_phase_plane", output_dir))

    return captured


# ---------------------------------------------------------------------------
# Excitability screenshots (ABF21 - firing-rate-current relationship)
# ---------------------------------------------------------------------------


def _capture_excitability(window: Any, analyser: Any, sm: Any, output_dir: Path) -> List[str]:
    """Capture the Excitability tab with the multi-trial action-potential file."""
    captured: List[str] = []
    if not _ABF21.exists():
        return captured

    _set_analysis_source(sm, _ABF21)

    tab = _activate_sub_tab(window, analyser, "Excitability")
    if tab is None:
        return captured

    _grab(window, output_dir / "analyser_excitability.png")
    captured.append("analyser_excitability.png")

    # ---- Excitability (F-I curve popup) ----
    _set_method(tab, "Excitability")
    _set_param(tab, "threshold", -20.0)
    # Current step is injected from 75 ms to 325 ms in the ABF21 recording.
    _set_param(tab, "analysis_start_s", 0.075)
    _set_param(tab, "analysis_end_s", 0.325)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_excitability_excitability.png")
    captured.append("analyser_excitability_excitability.png")
    captured.extend(_grab_popups(tab, "analyser_excitability_excitability", output_dir))

    # ---- Burst Analysis (Trial 18 shows a clear burst) ----
    _set_method(tab, "Burst Analysis")
    _set_param(tab, "threshold", -20.0)
    _set_param(tab, "analysis_start_s", 0.075)
    _set_param(tab, "analysis_end_s", 0.325)
    _set_trial(tab, 17)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_excitability_burst_analysis.png")
    captured.append("analyser_excitability_burst_analysis.png")

    # ---- Spike Train Dynamics (ISI popup; Trial 18) ----
    _set_method(tab, "Spike Train Dynamics")
    _set_param(tab, "spike_threshold", -20.0)
    _set_param(tab, "analysis_start_s", 0.075)
    _set_param(tab, "analysis_end_s", 0.325)
    _set_trial(tab, 17)
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_excitability_spike_train_dynamics.png")
    captured.append("analyser_excitability_spike_train_dynamics.png")
    captured.extend(_grab_popups(tab, "analyser_excitability_spike_train_dynamics", output_dir))

    return captured


# ---------------------------------------------------------------------------
# Synaptic Events screenshots (ABF22 - four-channel recording)
# ---------------------------------------------------------------------------


def _capture_synaptic_events(window: Any, analyser: Any, sm: Any, output_dir: Path) -> List[str]:
    """Capture the Synaptic Events tab using the multichannel recording."""
    captured: List[str] = []
    if not _ABF22.exists():
        return captured

    _set_analysis_source(sm, _ABF22)

    tab = _activate_sub_tab(window, analyser, "Synaptic Events")
    if tab is None:
        return captured

    # Use IN0 (chan_id '0') as the primary signal channel.
    _set_channel(tab, "0")

    _grab(window, output_dir / "analyser_synaptic_events.png")
    captured.append("analyser_synaptic_events.png")

    # ---- Threshold Based ----
    _set_method(tab, "Threshold Based")
    _set_param(tab, "polarity", "positive")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_synaptic_events_threshold_based.png")
    captured.append("analyser_synaptic_events_threshold_based.png")

    # ---- Deconvolution ----
    _set_method(tab, "Deconvolution (Custom)")
    _set_param(tab, "polarity", "positive")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_synaptic_events_deconvolution_custom.png")
    captured.append("analyser_synaptic_events_deconvolution_custom.png")

    # ---- Baseline + Peak + Kinetics ----
    _set_method(tab, "Baseline + Peak + Kinetics")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_synaptic_events_baseline_peak_kinetics.png")
    captured.append("analyser_synaptic_events_baseline_peak_kinetics.png")

    return captured


# ---------------------------------------------------------------------------
# Evoked Responses screenshots (ABF22 - FrameTTL optogenetics channel)
# ---------------------------------------------------------------------------


def _capture_evoked_responses(window: Any, analyser: Any, sm: Any, output_dir: Path) -> List[str]:
    """Capture the Evoked Responses tab using the optogenetics recording."""
    captured: List[str] = []
    if not _ABF22.exists():
        return captured

    _set_analysis_source(sm, _ABF22)

    tab = _activate_sub_tab(window, analyser, "Evoked Responses")
    if tab is None:
        return captured

    _grab(window, output_dir / "analyser_evoked_responses.png")
    captured.append("analyser_evoked_responses.png")

    # ---- Evoked Sync (optogenetics; TTL trigger = FrameTTL, chan_id '1') ----
    _set_method(tab, "Evoked Sync")
    # Select IN0 (chan_id '0') as primary signal, FrameTTL ('1') as the TTL source
    # via the secondary channel combobox when available.
    _set_channel(tab, "0")
    sec_cb = getattr(tab, "_secondary_channel_combobox", None)
    if sec_cb is not None:
        for i in range(sec_cb.count()):
            if sec_cb.itemData(i) == "1":
                sec_cb.setCurrentIndex(i)
                _pump(2)
                break
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_evoked_responses_evoked_sync.png")
    captured.append("analyser_evoked_responses_evoked_sync.png")

    # ---- Paired-Pulse Ratio ----
    _set_method(tab, "Paired-Pulse Ratio")
    _run_analysis(tab)
    _grab(window, output_dir / "analyser_evoked_responses_paired-pulse_ratio.png")
    captured.append("analyser_evoked_responses_paired-pulse_ratio.png")

    return captured


# ---------------------------------------------------------------------------
# Stale-file cleanup
# ---------------------------------------------------------------------------


def _remove_stale(output_dir: Path, captured: List[str]) -> None:
    """Delete PNGs in *output_dir* that were not produced in this run."""
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
    from Synaptipy.application.session_manager import SessionManager  # noqa: PLC0415
    from Synaptipy.shared.theme_manager import ThemeMode, apply_theme  # noqa: PLC0415

    captured: List[str] = []
    success = False

    app = QApplication.instance() or QApplication(sys.argv)

    # Apply the theme matching the host OS so screenshots look identical to
    # what users see on their own system.  ThemeMode.SYSTEM cannot be used
    # because the offscreen platform always initialises a light palette.
    target_theme = ThemeMode.DARK if _os_is_dark() else ThemeMode.LIGHT
    apply_theme(target_theme)
    print(f"[theme] {target_theme.value}")

    try:
        # Register all built-in analyses and load example plugins before the
        # MainWindow is constructed so every analysis tab is present.
        import Synaptipy.core.analysis  # noqa: F401 — registers built-in analyses
        from Synaptipy.application.plugin_manager import PluginManager  # noqa: PLC0415

        PluginManager.load_plugins()

        window = MainWindow()
        window.resize(_WINDOW_W, _WINDOW_H)
        window.show()
        _pump(10)

        sm = SessionManager()
        analyser = window.analyser_tab

        # --- Explorer screenshots ---
        print("[explorer]")
        captured.extend(_capture_explorer_screenshots(window, output_dir))

        # Return focus to Analyser tab before starting analysis captures.
        window.tab_widget.setCurrentIndex(1)
        _pump(5)

        # --- Analyser overview (no data) ---
        _grab(window, output_dir / "analyser_tab.png")
        captured.append("analyser_tab.png")

        # --- Per-module analysis screenshots ---
        print("[intrinsic properties]")
        captured.extend(_capture_intrinsic_properties(window, analyser, sm, output_dir))

        print("[spike analysis]")
        captured.extend(_capture_spike_analysis(window, analyser, sm, output_dir))

        print("[excitability]")
        captured.extend(_capture_excitability(window, analyser, sm, output_dir))

        print("[synaptic events]")
        captured.extend(_capture_synaptic_events(window, analyser, sm, output_dir))

        print("[evoked responses]")
        captured.extend(_capture_evoked_responses(window, analyser, sm, output_dir))

        # --- Exporter tab ---
        window.tab_widget.setCurrentIndex(2)
        _pump(5)
        _grab(window, output_dir / "exporter_tab.png")
        captured.append("exporter_tab.png")

        window.close()
        _pump(3)
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
