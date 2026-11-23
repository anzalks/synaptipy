# src/synaptipy/shared/plot_exporter.py
# -*- coding: utf-8 -*-
"""
Plot Exporter Utility.
Handles export of plots to various formats (SVG, PDF, PNG, JPG) using
Matplotlib (for vector quality) or PyQtGraph (for raster WYSIWYG).
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pyqtgraph as pg
import pyqtgraph.exporters

from synaptipy.core.data_model import Recording
from synaptipy.shared.plot_customization import get_average_pen, get_force_opaque_trials, get_single_trial_pen

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hybrid-rendering DPI for PDF/SVG exports.
# Rasterized layers (dense traces, filled regions) are embedded at this DPI
# so they remain sharp in print while keeping axes/text as true vectors.
# ---------------------------------------------------------------------------
_RASTER_DPI = 300


class PlotExporter:
    """
    Handles logic for exporting plots from the ExplorerTab (or similar).
    """

    def __init__(
        self,
        recording: Recording,
        plot_canvas_widget: Any,
        plot_canvas_wrapper: Any = None,
        config: Dict[str, Any] = None,
    ):
        """
        Args:
            recording: Current Recording object.
            plot_canvas_widget: The actual pg.GraphicsLayoutWidget (raster) or pg.PlotWidget.
            plot_canvas_wrapper: The wrapper (ExplorerPlotCanvas) for get_plot(). Optional.
            config: Configuration dict.
        """
        self.recording = recording
        self.widget = plot_canvas_widget
        self.wrapper = plot_canvas_wrapper
        self.config = config or {}

    def export(self, filename: str, fmt: str, dpi: int) -> bool:
        """
        Export the plot to the specified file.
        Returns True if successful, False otherwise.
        """
        try:
            if fmt in ["pdf"]:
                exported = self._save_via_matplotlib(filename, fmt, dpi)
            else:
                exported = self._save_via_pyqtgraph(filename, fmt, dpi)
            if exported:
                self._write_provenance_sidecar(filename, fmt, dpi)
            return exported
        except Exception as e:
            log.error(f"Export failed: {e}")
            raise e

    def _write_provenance_sidecar(self, filename: str, fmt: str, dpi: int) -> None:
        """Write machine-readable context beside every exported figure."""
        output = Path(filename)
        source_file = getattr(self.recording, "source_file", None) if self.recording is not None else None
        recording_metadata = getattr(self.recording, "metadata", {}) if self.recording is not None else {}
        provenance = {
            "schema_version": 1,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "figure_file": output.name,
            "format": fmt.lower(),
            "dpi": int(dpi),
            "source_file": str(source_file) if source_file is not None else None,
            "recording_metadata": recording_metadata,
            "analysis_context": self.config,
        }
        sidecar = output.with_suffix(output.suffix + ".provenance.json")
        sidecar.write_text(json.dumps(provenance, indent=2, default=str), encoding="utf-8")

    def _save_via_pyqtgraph(self, filename: str, fmt: str, dpi: int) -> bool:
        """Save raster images using pyqtgraph (WYSIWYG).

        Explicitly sets an opaque white background before grabbing the widget so
        that macOS Dark Mode or transparent Qt themes do not bleed a dark canvas
        colour through semi-transparent shaded regions in the exported PNG.
        The original background is restored immediately after the capture.
        """
        # Use the central layout item (.ci) if avail, else the widget itself
        if isinstance(self.widget, pg.PlotItem):
            target_item = self.widget
        elif hasattr(self.widget, "getPlotItem"):
            target_item = self.widget.getPlotItem()
        else:
            target_item = getattr(self.widget, "ci", self.widget)

        # --- Force opaque white background for PNG export ---
        # Issue 2 fix: prevents OS dark-mode from compositing a dark canvas
        # through transparent Qt backgrounds, which makes alpha shading appear
        # muddy / over-dark in image viewers (Preview, Finder Quick Look, etc.)
        original_bg = None
        try:
            if hasattr(self.widget, "backgroundBrush"):
                original_bg = self.widget.backgroundBrush()
            if hasattr(self.widget, "setBackground"):
                self.widget.setBackground("w")  # solid white
        except Exception:
            pass  # non-fatal — proceed with whatever background exists

        try:
            if fmt == "svg":
                exporter = pg.exporters.SVGExporter(target_item)
                exporter.export(filename)
                log.info(f"Exported SVG plot to {filename}")
                return True
            else:
                exporter = pg.exporters.ImageExporter(target_item)

                # Scale for DPI (Screen DPI is usually ~96)
                scale_factor = max(0.5, float(dpi or 300) / 96.0)
                exporter.parameters()["width"] = max(64, int(float(target_item.width()) * scale_factor))

                exporter.export(filename)
                log.info(f"Exported raster plot to {filename}")
                return True
        finally:
            # Restore original background
            try:
                if original_bg is not None and hasattr(self.widget, "setBackground"):
                    self.widget.setBackground(original_bg)
            except Exception:
                pass

    def _save_via_matplotlib(self, filename: str, fmt: str, dpi: int) -> bool:  # noqa: C901
        """
        Save vector plots using Matplotlib for publication quality.

        Hybrid rendering strategy (Issue 1b + Issue 2):
        - Axes, tick labels, and text are rendered as **true vectors** (crisp at any zoom).
        - Dense raw-data lines and filled/shaded regions use ``rasterized=True`` so they
          are embedded as a single high-DPI bitmap layer inside the PDF/SVG.  This prevents:
            * PDF file bloat (one vector path per sample point),
            * Alpha-compositing stitching artefacts in Acrobat / Preview,
            * Viewer crashes on high-density recordings (>100 k points per line).
        - The raster DPI used for embedded bitmaps is ``_RASTER_DPI`` (300 dpi) regardless
          of the ``dpi`` argument so that the embedded layer is always print-quality.

        PNG alpha-stacking / Dark Mode fix (Issue 2):
        - Each call creates a *fresh* Figure + Axes (no state bleed between exports).
        - ``fig.savefig`` always uses ``facecolor='white', transparent=False`` so that
          macOS Dark Mode or any OS-level theme cannot composite a dark canvas colour
          through the transparent PNG background.
        - Every Axes face is also explicitly set to white (``ax.set_facecolor('white')``).

        Extracts data directly from pyqtgraph PlotDataItems to match screen appearance.
        """
        import matplotlib
        import matplotlib.pyplot as plt

        # Use the non-interactive Agg backend for off-screen rendering.
        # This avoids "matplotlib not found" errors that occur when the Qt backend
        # tries to create a display window in a headless / embedded context.
        matplotlib.use("Agg")

        # Embed TrueType fonts, rather than Type 3 glyph outlines, so labels
        # remain editable text in Illustrator, Affinity Designer, and Inkscape.
        # This applies only to the vector PDF route; SVG uses PyQtGraph's native
        # SVG exporter, which emits ``<text>`` elements directly.
        if fmt == "pdf":
            matplotlib.rcParams["pdf.fonttype"] = 42
            matplotlib.rcParams["ps.fonttype"] = 42

        # 1. Setup Figure - accept ExplorerPlotCanvas wrapper, PlotWidget, PlotItem, or GraphicsLayoutWidget
        plots_to_export = []

        if self.wrapper and self.recording and hasattr(self.recording, "channels"):
            for cid in self.recording.channels.keys():
                plot_item = self.wrapper.get_plot(cid)
                if plot_item and plot_item.isVisible():
                    plots_to_export.append((cid, plot_item))
        elif isinstance(self.widget, pg.PlotItem):
            plots_to_export.append(("Analysis", self.widget))
        elif hasattr(self.widget, "getPlotItem"):
            plot_item = self.widget.getPlotItem()
            if plot_item is not None:
                plots_to_export.append(("Analysis", plot_item))
        elif hasattr(self.widget, "ci") and hasattr(self.widget.ci, "items"):
            for item in self.widget.ci.items.keys():
                if isinstance(item, pg.PlotItem) and item.isVisible():
                    plots_to_export.append(("Plot", item))
        else:
            log.warning("Widget cannot be resolved to PlotItem(s). Cannot export vector.")
            return False

        if not plots_to_export:
            log.warning("No visible plots to export.")
            return False

        n_plots = len(plots_to_export)
        try:
            screen_width = float(self.widget.width())
            screen_height = float(self.widget.height())
        except Exception:
            screen_width, screen_height = 0.0, 0.0

        if screen_width > 0 and screen_height > 0:
            aspect_ratio = screen_width / screen_height
            fig_width = 12.0
            fig_height = max(2.5, min(36.0, fig_width / aspect_ratio))
        else:
            fig_width = 10.0
            fig_height = 3.0 * n_plots

        export_dpi = max(72, int(dpi or _RASTER_DPI))
        share_x = n_plots > 1 and bool(self.wrapper)

        fig, axes = plt.subplots(
            n_plots,
            1,
            sharex=share_x,
            figsize=(fig_width, fig_height),
            dpi=export_dpi,
            facecolor="white",
        )
        if n_plots == 1:
            axes = [axes]

        import numpy as np
        import PySide6.QtCore as QtCore
        import PySide6.QtGui as QtGui

        from synaptipy.shared.plot_customization import get_grid_pen, is_grid_enabled

        avg_pen = get_average_pen()
        trial_pen = get_single_trial_pen()
        grid_on = is_grid_enabled()
        grid_pen = get_grid_pen()
        grid_alpha = (
            (grid_pen.color().alpha() / 255.0) if (grid_pen is not None and hasattr(grid_pen, "color")) else 0.3
        )

        def pen_to_mpl(pen):
            c = pen.color()
            w = max(0.5, float(pen.widthF() or pen.width() or 1.0))
            st = pen.style()
            ls = "--" if st == QtCore.Qt.PenStyle.DashLine else (":" if st == QtCore.Qt.PenStyle.DotLine else "-")
            return (c.redF(), c.greenF(), c.blueF()), c.alphaF(), w, ls

        def brush_to_mpl(brush):
            if brush is None:
                return (0.2, 0.4, 0.8), 0.3
            c = pg.mkBrush(brush).color()
            return (c.redF(), c.greenF(), c.blueF()), c.alphaF()

        pg_sym_map = {"o": "o", "s": "s", "t": "^", "t1": "v", "d": "D", "+": "+", "x": "x", "star": "*"}

        avg_color, avg_alpha, avg_w, _ = pen_to_mpl(avg_pen)
        trial_color, trial_alpha, trial_w, _ = pen_to_mpl(trial_pen)

        if get_force_opaque_trials():
            trial_alpha = 1.0

        use_rasterized = fmt in ("pdf", "svg")

        def _axis_label_text(pi: pg.PlotItem, side: str) -> str:
            try:
                ax_item = pi.getAxis(side)
                if ax_item is None:
                    return ""
                txt = (getattr(ax_item, "labelText", "") or "").strip()
                units = (getattr(ax_item, "labelUnits", "") or "").strip()
                if txt and units and f"({units})" not in txt and f"[{units}]" not in txt:
                    return f"{txt} ({units})"
                return txt
            except Exception:
                return ""

        for i, (label, plot_item) in enumerate(plots_to_export):
            ax = axes[i]
            ax.set_facecolor("white")

            vb = plot_item.getViewBox()
            x_range = vb.viewRange()[0]
            y_range = vb.viewRange()[1]

            # 2a. PlotDataItems (skip hidden pooled sweeps, prefer full-resolution raw data)
            plotted_items = (
                plot_item.listDataItems()
                if hasattr(plot_item, "listDataItems")
                else [it for it in plot_item.items if isinstance(it, pg.PlotDataItem)]
            )

            for item in plotted_items:
                try:
                    if hasattr(item, "isVisible") and not item.isVisible():
                        continue
                    raw_xy = getattr(item, "_synaptipy_raw_xy", None)
                    if (
                        isinstance(raw_xy, tuple)
                        and len(raw_xy) == 2
                        and raw_xy[0] is not None
                        and raw_xy[1] is not None
                    ):
                        x_data, y_data = raw_xy
                    elif getattr(item, "xData", None) is not None and getattr(item, "yData", None) is not None:
                        x_data, y_data = item.xData, item.yData
                    else:
                        x_data, y_data = item.getData()

                    if x_data is None or y_data is None or len(x_data) == 0 or len(y_data) == 0:
                        continue

                    min_len = min(len(x_data), len(y_data))
                    x_data = np.asarray(x_data[:min_len], dtype=float)
                    y_data = np.asarray(y_data[:min_len], dtype=float)

                    opts = getattr(item, "opts", {}) or {}
                    item_name = str(opts.get("name") or (item.name() if hasattr(item, "name") else "") or "")
                    is_average = "average" in item_name.lower() or "avg" in item_name.lower()

                    item_pen = opts.get("pen")
                    symbol = opts.get("symbol")

                    # Symbol-only PlotDataItem (e.g. popup scatter points / Phase Plane markers)
                    if item_pen is None and symbol is not None:
                        sym_brush = opts.get("symbolBrush")
                        mc, ma = brush_to_mpl(sym_brush)
                        ms = float(opts.get("symbolSize", 8))
                        ax.scatter(
                            x_data,
                            y_data,
                            s=ms * ms * 0.6,
                            color=[(*mc, max(0.2, ma))],
                            marker=pg_sym_map.get(str(symbol), "o"),
                            edgecolors="#222222",
                            linewidths=0.6,
                            zorder=15,
                        )
                        continue

                    ls = "-"
                    lw = avg_w if is_average else trial_w
                    if item_pen is not None:
                        qpen = item_pen if isinstance(item_pen, QtGui.QPen) else pg.mkPen(item_pen)
                        if qpen.style() == QtCore.Qt.PenStyle.NoPen:
                            mp_color, mp_alpha = None, 0.0
                        else:
                            mp_color, mp_alpha, lw, ls = pen_to_mpl(qpen)
                    else:
                        mp_color, mp_alpha = (avg_color, avg_alpha) if is_average else (trial_color, trial_alpha)

                    if mp_color is not None and mp_alpha > 0:
                        ax.plot(
                            x_data,
                            y_data,
                            color=mp_color,
                            alpha=1.0 if (not is_average and get_force_opaque_trials()) else mp_alpha,
                            linewidth=max(0.6, lw * 0.85),
                            linestyle=ls,
                            zorder=10 if is_average else 2,
                            rasterized=(False if (is_average or len(x_data) < 2000) else use_rasterized),
                        )

                    if symbol is not None:
                        sym_brush = opts.get("symbolBrush")
                        mc, ma = brush_to_mpl(sym_brush) if sym_brush is not None else (mp_color or (0, 0, 0), 1.0)
                        ms = float(opts.get("symbolSize", 7))
                        ax.scatter(
                            x_data,
                            y_data,
                            s=ms * ms * 0.55,
                            color=[(*mc, max(0.25, ma))],
                            marker=pg_sym_map.get(str(symbol), "o"),
                            edgecolors="#222222",
                            linewidths=0.5,
                            zorder=14,
                        )
                except Exception as e:
                    log.warning(f"Failed to extract data from PlotDataItem: {e}")

            # 2b. Analysis overlays: curves, scatters, lines, regions, fills, text
            for item in getattr(plot_item, "items", []):
                try:
                    if isinstance(item, pg.PlotDataItem):
                        continue
                    if hasattr(item, "isVisible") and not item.isVisible():
                        continue

                    if isinstance(item, pg.FillBetweenItem):
                        curves = getattr(item, "curves", None)
                        if curves and len(curves) >= 2:
                            x1, y1 = curves[0].getData()
                            x2, y2 = curves[1].getData()
                            if x1 is not None and y1 is not None and y2 is not None and len(x1) == len(y1) == len(y2):
                                fc, fa = brush_to_mpl(getattr(item, "brush", None))
                                ax.fill_between(x1, y1, y2, color=fc, alpha=fa, zorder=3, rasterized=use_rasterized)

                    elif isinstance(item, pg.PlotCurveItem):
                        xc, yc = item.getData()
                        if xc is not None and yc is not None and len(xc) >= 2:
                            qpen = pg.mkPen(item.opts.get("pen"))
                            if qpen.style() != QtCore.Qt.PenStyle.NoPen:
                                cc, ca, cw, cls = pen_to_mpl(qpen)
                                ax.plot(
                                    xc,
                                    yc,
                                    color=cc,
                                    alpha=ca,
                                    linewidth=max(0.8, cw * 0.85),
                                    linestyle=cls,
                                    zorder=12,
                                )

                    elif isinstance(item, pg.ScatterPlotItem):
                        xs, ys = item.getData()
                        if xs is not None and ys is not None and len(xs) > 0:
                            fc, fa = brush_to_mpl(item.opts.get("brush"))
                            sz = float(item.opts.get("size", 9))
                            sym = pg_sym_map.get(str(item.opts.get("symbol", "o")), "o")
                            ax.scatter(
                                xs,
                                ys,
                                s=sz * sz * 0.6,
                                color=[(*fc, max(0.3, fa))],
                                marker=sym,
                                edgecolors="#222222",
                                linewidths=0.6,
                                zorder=16,
                            )

                    elif isinstance(item, pg.InfiniteLine):
                        pos_val = float(item.value())
                        qpen = pg.mkPen(item.pen)
                        lc, la, lw, lls = pen_to_mpl(qpen)
                        if abs(float(item.angle) - 90.0) < 1e-3:
                            ax.axvline(pos_val, color=lc, alpha=la, linewidth=lw, linestyle=lls, zorder=11)
                        elif abs(float(item.angle)) < 1e-3:
                            ax.axhline(pos_val, color=lc, alpha=la, linewidth=lw, linestyle=lls, zorder=11)

                    elif isinstance(item, pg.LinearRegionItem):
                        r0, r1 = item.getRegion()
                        rc, ra = brush_to_mpl(getattr(item, "brush", None))
                        ax.axvspan(r0, r1, color=rc, alpha=ra, zorder=1)

                    elif isinstance(item, pg.TextItem):
                        txt = item.toPlainText().strip()
                        if txt:
                            pos = item.pos()
                            ax.text(
                                float(pos.x()),
                                float(pos.y()),
                                txt,
                                fontsize=8.5,
                                color="#111111",
                                bbox={
                                    "boxstyle": "round,pad=0.25",
                                    "facecolor": "white",
                                    "edgecolor": "#666666",
                                    "alpha": 0.88,
                                },
                                zorder=20,
                            )
                except Exception as exc:
                    log.debug("Skipped overlay item during Matplotlib export: %s", exc)

            ax.set_xlim(x_range)
            ax.set_ylim(y_range)

            # Axis labels & title: preserve PlotItem labels first, fall back to Recording channel metadata
            y_lbl = _axis_label_text(plot_item, "left")
            has_rec_chan = (
                self.wrapper
                and self.recording
                and hasattr(self.recording, "channels")
                and label in self.recording.channels
            )
            if not y_lbl and has_rec_chan:
                chan = self.recording.channels[label]
                y_lbl = f"{chan.get_primary_data_label()} ({chan.units})"
            ax.set_ylabel(y_lbl or label)

            x_lbl = _axis_label_text(plot_item, "bottom")
            if x_lbl and (not share_x or i == n_plots - 1):
                ax.set_xlabel(x_lbl)

            try:
                title_txt = (plot_item.titleLabel.text or "").strip() if getattr(plot_item, "titleLabel", None) else ""
                if title_txt:
                    ax.set_title(title_txt, fontsize=10)
            except Exception:
                pass

            ax.spines["right"].set_visible(False)
            ax.spines["top"].set_visible(False)
            if grid_on and grid_pen is not None:
                ax.grid(True, alpha=grid_alpha)
            else:
                ax.grid(False)

        if not axes[-1].get_xlabel():
            bot_lbl = _axis_label_text(plots_to_export[-1][1], "bottom")
            axes[-1].set_xlabel(bot_lbl or "Time (s)")

        plt.tight_layout()

        fig.savefig(
            filename,
            format=fmt,
            dpi=export_dpi,
            facecolor="white",
            transparent=False,
        )
        plt.close(fig)
        log.info(f"Exported vector plot to {filename} (hybrid rendering, dpi={export_dpi})")
        return True
