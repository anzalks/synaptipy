# -*- coding: utf-8 -*-
"""
Regression suite for GUI theme, plot customization, Explorer zoom/downsampling,
Analyser overlays/popups, and publication export/batch/session workflows.
"""

from unittest.mock import MagicMock

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

import synaptipy.core.analysis  # noqa: F401 - register built-in analyses
from synaptipy.application.controllers.analysis_formatter import (
    AnalysisResultFormatter,
    generate_methods_text,
)
from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
from synaptipy.application.gui.batch_dialog import AddStepDialog, PipelineStepWidget
from synaptipy.application.gui.explorer.plot_canvas import ExplorerPlotCanvas
from synaptipy.application.gui.help_window import _build_help_css, _sanitize_sphinx_html
from synaptipy.application.gui.session_summary_dialog import SessionSummaryDialog
from synaptipy.core.data_model import Channel, Recording
from synaptipy.infrastructure.file_readers import NeoAdapter
from synaptipy.shared.plot_customization import (
    get_plot_customization_manager,
    get_scatter_pen_and_brush,
)
from synaptipy.shared.plot_exporter import PlotExporter
from synaptipy.shared.plot_factory import SynaptipyPlotFactory
from synaptipy.shared.theme_manager import (
    ThemeMode,
    apply_theme,
    clear_subdued_style,
    select_platform_style,
    status_html_colors,
    style_as_subdued,
    themed_plot_colors,
    warning_banner_stylesheet,
)


def test_white_plot_canvas_in_both_light_and_dark_themes(qapp):
    """Plot canvas stays white with black axes in both Light and Dark themes."""
    apply_theme(ThemeMode.DARK, preview=True)
    assert themed_plot_colors() == ("white", "black")
    pw_dark = SynaptipyPlotFactory.create_plot_widget(enable_grid=False)
    assert pw_dark.backgroundBrush().color().name().lower() == "#ffffff"
    pw_dark.close()

    apply_theme(ThemeMode.LIGHT, preview=True)
    assert themed_plot_colors() == ("white", "black")
    pw_light = SynaptipyPlotFactory.create_plot_widget(enable_grid=False)
    assert pw_light.backgroundBrush().color().name().lower() == "#ffffff"
    pw_light.close()


def test_subdued_dynamic_property_and_scoped_banner_qss(qapp):
    """style_as_subdued uses QSS property instead of palette-pinning; banner QSS is scoped."""
    lbl = QtWidgets.QLabel("Status")
    style_as_subdued(lbl, italic=True)
    assert lbl.property("subdued") is True
    assert lbl.font().italic() is True

    clear_subdued_style(lbl)
    assert lbl.property("subdued") is False
    assert lbl.font().italic() is False

    banner_qss = warning_banner_stylesheet()
    assert "QFrame#UpdateBanner" in banner_qss

    colors = status_html_colors()
    assert "warning" in colors and "error" in colors and "success" in colors


def test_help_html_sanitization_and_dark_light_css():
    """Sphinx RTD sidebar chrome and external stylesheets are stripped and themed cleanly."""
    raw_html = (
        "<html><head><link rel='stylesheet' href='_static/css/theme.css'></head>"
        "<body class='wy-body-for-nav'><nav class='wy-nav-side'>Sidebar</nav>"
        "<div class='wy-nav-content'><h1>User Guide</h1></div></body></html>"
    )
    cleaned = _sanitize_sphinx_html(raw_html)
    assert "wy-nav-side" not in cleaned
    assert "stylesheet" not in cleaned
    assert "User Guide" in cleaned
    assert "#232323" in _build_help_css(True)
    assert "#ffffff" in _build_help_css(False)


def test_scatter_default_visible_on_white_and_auto_border_for_light_fills(qapp):
    """Default scatter color is high-contrast on white; bright yellow gets a dark outline."""
    mgr = get_plot_customization_manager()
    assert mgr.defaults["scatter_points"]["color"].lower() != "#ffff00"

    orig = dict(mgr.defaults.get("scatter_points", {}))
    try:
        mgr.defaults["scatter_points"] = {"color": "#ffff00", "opacity": 100, "size": 10, "symbol": "o"}
        mgr._cache_dirty = True
        pen, _brush = get_scatter_pen_and_brush()
        assert pen.style() != QtCore.Qt.PenStyle.NoPen
        assert pen.color().name().lower() == "#222222"
    finally:
        mgr.defaults["scatter_points"] = orig
        mgr._cache_dirty = True


def test_explorer_manual_y_lock_preserves_box_zoom_across_x_changes(qapp):
    """Once _synaptipy_manual_y is set (e.g. 2D box zoom), X pans do not reset Y to autoRange."""
    canvas = ExplorerPlotCanvas()
    rec = MagicMock(spec=Recording)
    ch = MagicMock(spec=Channel)
    ch.name = "Vm"
    ch.units = "mV"
    rec.channels = {"ch0": ch}
    canvas.rebuild_plots(rec)
    canvas.widget.resize(640, 480)
    canvas.widget.show()
    try:
        plot = canvas.channel_plots["ch0"]
        vb = plot.getViewBox()
        assert vb.autoRangeEnabled() == [False, True]
        plot.plot(np.linspace(0, 1.0, 1000), np.linspace(-70.0, 40.0, 1000))

        # Simulate 2D box zoom locking Y to [-68, -62]
        vb._synaptipy_manual_y = True
        vb.enableAutoRange(x=False, y=False)
        plot.setXRange(0.2, 0.4, padding=0)
        plot.setYRange(-68.0, -62.0, padding=0)

        # Panning X must NOT snap Y back to full trace auto-range
        plot.setXRange(0.4, 0.6, padding=0)
        yr = plot.viewRange()[1]
        assert abs(yr[0] - (-68.0)) < 0.5
        assert abs(yr[1] - (-62.0)) < 0.5
    finally:
        canvas.widget.hide()
        canvas.clear_plots()


def test_plot_exporter_supports_bare_plot_item_and_skips_hidden_sweeps(qapp, tmp_path):
    """PlotExporter exports bare PlotItem (Analysis tabs) to PDF and skips hidden pooled sweeps."""
    glw = pg.GraphicsLayoutWidget()
    glw.resize(640, 480)
    pi = glw.addPlot(row=0, col=0)
    pi.setLabel("bottom", "Current (pA)")
    pi.setLabel("left", "Voltage Response (mV)")
    visible_line = pi.plot(np.array([-50.0, 0.0, 50.0]), np.array([-5.0, 0.0, 5.0]), name="Average")
    hidden_line = pi.plot(np.array([-50.0, 50.0]), np.array([-100.0, 100.0]))
    hidden_line.hide()
    assert visible_line.isVisible()

    scatter = pg.ScatterPlotItem(x=[-50.0, 0.0, 50.0], y=[-5.0, 0.0, 5.0], size=9, brush=pg.mkBrush("#e41a1c"))
    pi.addItem(scatter)
    hline = pg.InfiniteLine(pos=0.0, angle=0, pen=pg.mkPen("r"))
    pi.addItem(hline)

    pdf_out = tmp_path / "analysis_plot_item.pdf"
    ok = PlotExporter(recording=None, plot_canvas_widget=pi).export(str(pdf_out), "pdf", 300)
    assert ok is True
    assert pdf_out.is_file() and pdf_out.stat().st_size > 0
    glw.close()


def test_metadata_driven_derivative_unit_and_per_method_param_cache(qapp, qtbot):
    """Phase plane derivative unit maps mV -> V/s, and method switching preserves user parameter edits."""
    assert MetadataDrivenAnalysisTab._derivative_unit_str("mV") == "V/s"
    assert MetadataDrivenAnalysisTab._derivative_unit_str("pA") == "nA/s"

    tab = MetadataDrivenAnalysisTab("passive_properties", neo_adapter=MagicMock(spec=NeoAdapter))
    qtbot.addWidget(tab)
    try:
        # Initial method is Baseline (RMP)
        assert tab.analysis_name == "rmp_analysis"
        assert tab._region_mode_combo is not None
        tab.param_generator.widgets["baseline_end"].setValue(0.25)

        # Switch to Input Resistance then back to Baseline (RMP)
        rin_idx = tab.method_combobox.findText("Input Resistance")
        tab.method_combobox.setCurrentIndex(rin_idx)
        assert tab.analysis_name == "rin_analysis"

        rmp_idx = tab.method_combobox.findText("Baseline (RMP)")
        tab.method_combobox.setCurrentIndex(rmp_idx)
        assert tab.analysis_name == "rmp_analysis"
        assert abs(tab.param_generator.widgets["baseline_end"].value() - 0.25) < 1e-6
    finally:
        tab.cleanup()


def test_batch_add_step_dialog_renders_int_and_options_params(qapp, qtbot):
    """AddStepDialog renders int (n_pulses) and options-keyed choice (tau_model) parameters."""
    dlg = AddStepDialog()
    qtbot.addWidget(dlg)

    dlg._on_analysis_changed("paired_pulse_ratio")
    assert "n_pulses" in dlg.param_widgets
    assert isinstance(dlg.param_widgets["n_pulses"], QtWidgets.QSpinBox)

    dlg._on_analysis_changed("tau_analysis")
    assert "tau_model" in dlg.param_widgets
    combo = dlg.param_widgets["tau_model"]
    assert isinstance(combo, QtWidgets.QComboBox)
    assert combo.count() >= 2

    step_w = PipelineStepWidget({"analysis": "tau_analysis", "scope": "average", "params": {}}, 0)
    qtbot.addWidget(step_w)
    step_w.update_index(3)
    assert step_w.step_label.text() == "#4"


def test_session_summary_and_formatter_unpack_schema_v1_and_nan_safe(qapp, qtbot):
    """SessionSummaryDialog, AnalysisResultFormatter, and generate_methods_text handle Schema v1 dicts."""
    entries = [
        {
            "schema_version": 1,
            "analysis_name": "rmp_analysis",
            "analysis_type": "Baseline (RMP)",
            "source_label": "Trial 1",
            "metrics": {"rmp_mv": -65.0, "rmp_std": 0.4, "_plot_rmp_mv": -65.0},
            "provenance": {"parameters": {"baseline_start": 0.0, "baseline_end": 0.1}},
        },
        {
            "schema_version": 1,
            "analysis_name": "rmp_analysis",
            "analysis_type": "Baseline (RMP)",
            "source_label": "Trial 2",
            "metrics": {"rmp_mv": float("nan"), "rmp_std": 0.6},
            "provenance": {"parameters": {"baseline_start": 0.0, "baseline_end": 0.1}},
        },
        {
            "schema_version": 1,
            "analysis_name": "rmp_analysis",
            "analysis_type": "Baseline (RMP)",
            "source_label": "Trial 3",
            "metrics": {"rmp_mv": -67.0, "rmp_std": 0.5},
            "provenance": {"parameters": {"baseline_start": 0.0, "baseline_end": 0.1}},
        },
    ]

    dlg = SessionSummaryDialog(entries)
    qtbot.addWidget(dlg)
    assert dlg.table.rowCount() == 3
    headers = [dlg.table.horizontalHeaderItem(c).text() for c in range(dlg.table.columnCount())]
    assert "Schema Version" not in headers
    assert "Rmp Mv" in headers

    methods_txt = dlg.methods_text.toPlainText()
    assert "matched filter" not in methods_txt.lower()
    assert "Resting membrane potential" in methods_txt

    val_str, _details = AnalysisResultFormatter.format_result(entries[0])
    assert "-65.000" in val_str
    assert "1.00" not in val_str

    tau_methods = generate_methods_text(
        {
            "schema_version": 1,
            "analysis_name": "tau_analysis",
            "parameters": {"tau_model": "mono", "fit_duration": 0.05},
        }
    )
    assert "mono-exponential" in tau_methods


def test_per_os_native_style_and_menubar_conventions(main_window):
    """Each OS gets its native Qt style (macOS, Windows 11/10, Linux Breeze/Fusion) and menu conventions."""
    assert select_platform_style(False, "darwin", "cocoa", ["macOS", "Windows", "Fusion"]) == ("macOS", True)
    assert select_platform_style(True, "darwin", "cocoa", ["macOS", "Windows", "Fusion"]) == ("macOS", True)
    assert select_platform_style(False, "win32", "windows", ["windows11", "windowsvista", "Fusion"]) == (
        "windows11",
        False,
    )
    assert select_platform_style(True, "win32", "windows", ["windows11", "windowsvista", "Fusion"]) == (
        "windows11",
        False,
    )
    assert select_platform_style(False, "win32", "windows", ["windowsvista", "Fusion"]) == ("windowsvista", True)
    assert select_platform_style(True, "win32", "windows", ["windowsvista", "Fusion"]) == ("Fusion", False)
    assert select_platform_style(True, "linux", "xcb", ["Fusion"]) == ("Fusion", False)
    assert select_platform_style(False, "darwin", "offscreen", ["Windows", "Fusion"]) == ("Fusion", False)

    mb = main_window.menuBar()
    top_titles = [act.text().replace("&", "") for act in mb.actions()]
    assert top_titles == ["File", "Edit", "View", "Help"]
    assert main_window.preferences_action.menuRole() == QtGui.QAction.MenuRole.NoRole
    assert main_window.plot_customization_action.menuRole() == QtGui.QAction.MenuRole.NoRole
    assert hasattr(main_window, "theme_menu")
    assert main_window.theme_dark_action.isCheckable()

    main_window._set_theme_from_menu(ThemeMode.DARK)
    assert main_window.theme_dark_action.isChecked() is True
    main_window._set_theme_from_menu(ThemeMode.LIGHT)
    assert main_window.theme_light_action.isChecked() is True


def test_legacy_capital_synaptipy_plugins_migrate_and_bundled_wins_over_stale_copy(tmp_path):
    """Stale pre-rename 'Synaptipy' copies do not fail startup or shadow updated bundled examples."""
    from unittest.mock import patch

    from synaptipy.application.plugin_manager import PluginManager
    from synaptipy.core.analysis.registry import AnalysisRegistry

    bundled_dir = tmp_path / "bundled"
    user_dir = tmp_path / "user"
    bundled_dir.mkdir()
    user_dir.mkdir()

    # 1. Bundled updated plugin vs stale pre-rename user copy with same stem
    (bundled_dir / "demo_ex.py").write_text(
        "from synaptipy.core.analysis.registry import AnalysisRegistry\n"
        "@AnalysisRegistry.register('demo_ex_updated')\n"
        "def fn(data, time, sampling_rate, **kwargs):\n"
        "    return {'metrics': {'ok': 1}}\n",
        encoding="utf-8",
    )
    (user_dir / "demo_ex.py").write_text(
        "from Synaptipy.core.analysis.registry import AnalysisRegistry\n"
        "@AnalysisRegistry.register('demo_ex_stale')\n"
        "def fn(data, time, sampling_rate, **kwargs):\n"
        "    return {'metrics': {'ok': 0}}\n",
        encoding="utf-8",
    )

    # 2. Standalone custom user plugin still importing legacy 'Synaptipy'
    (user_dir / "custom_legacy.py").write_text(
        "from Synaptipy.core.analysis.registry import AnalysisRegistry\n"
        "@AnalysisRegistry.register('custom_legacy_ok')\n"
        "def fn2(data, time, sampling_rate, **kwargs):\n"
        "    return {'metrics': {'ok': 2}}\n",
        encoding="utf-8",
    )

    saved_reg = dict(AnalysisRegistry._registry)
    saved_meta = dict(AnalysisRegistry._metadata)
    saved_orig = dict(AnalysisRegistry._original_metadata)
    try:
        with (
            patch("synaptipy.application.plugin_manager._get_bundled_plugin_dir", return_value=bundled_dir),
            patch("synaptipy.application.plugin_manager.PLUGIN_DIR", user_dir),
        ):
            files = PluginManager.get_plugin_files()
            assert (bundled_dir / "demo_ex.py") in files
            assert (user_dir / "demo_ex.py") not in files
            assert (user_dir / "custom_legacy.py") in files

            failures = PluginManager.load_plugins()
            assert failures == []
            assert AnalysisRegistry.get_function("demo_ex_updated") is not None
            assert AnalysisRegistry.get_function("demo_ex_stale") is None
            assert AnalysisRegistry.get_function("custom_legacy_ok") is not None
    finally:
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._registry.update(saved_reg)
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._metadata.update(saved_meta)
        AnalysisRegistry._original_metadata.clear()
        AnalysisRegistry._original_metadata.update(saved_orig)
