"""Scientific vector schematic for Figure 1A.

Run this file to regenerate ``paper/figures/figure_01_panel_a.svg``. The
same vector artists are also drawn in the full Figure 1 SVG. Waveforms and
table entries are schematic illustrations, not measured results.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, Rectangle

INK = "#19324A"
MUTED = "#526675"
GRID = "#CFD9DF"
BLUE = "#246B9A"
TEAL = "#16847D"
PURPLE = "#695491"
AMBER = "#9C631E"


def _text(ax, x, y, value, size, scale, color=INK, weight="normal", **kwargs):
    ax.text(
        x,
        y,
        value,
        fontsize=size * scale,
        color=color,
        weight=weight,
        va="center",
        zorder=5,
        **kwargs,
    )


def _stage(ax, x, width, color):
    # A light rule groups each step without enclosing the scientific plots.
    ax.add_patch(
        Rectangle((x, 49.5), width, 0.5, facecolor=color, edgecolor="none", zorder=3)
    )


def _arrow(ax, start, end, color=INK):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=10,
            linewidth=1.4,
            color=color,
            shrinkA=0,
            shrinkB=0,
            zorder=4,
        )
    )


def _plot_axes(ax, left, bottom, width, height):
    ax.plot(
        [left, left, left + width],
        [bottom + height, bottom, bottom],
        color=GRID,
        linewidth=0.7,
        zorder=3,
    )


def _input_panel(ax, scale):
    _text(ax, 4, 46.7, "01  RECORDINGS", 8.5, scale, weight="bold")
    for x, width, label in (
        (4, 4.1, "ABF"),
        (8.6, 5.0, "HEKA"),
        (14.1, 4.1, "WCP"),
        (18.7, 3.5, "NWB"),
    ):
        ax.add_patch(
            Rectangle(
                (x, 40.8),
                width,
                3.3,
                facecolor="#EFF5F9",
                edgecolor="#C7DAE6",
                linewidth=0.6,
                zorder=3,
            )
        )
        _text(
            ax,
            x + width / 2,
            42.45,
            label,
            6.0,
            scale,
            color=BLUE,
            weight="bold",
            ha="center",
        )

    _plot_axes(ax, 5, 27, 16, 12)
    t = np.linspace(0, 1, 320)
    for offset, alpha in ((-1.4, 0.32), (0.0, 0.58), (1.4, 0.95)):
        voltage = np.full_like(t, 31.1 + offset)
        for center in (0.27, 0.53, 0.79):
            voltage += 5.5 * np.exp(-(((t - center) / 0.012) ** 2))
            voltage -= 1.5 * np.exp(-(((t - center - 0.026) / 0.022) ** 2))
        ax.plot(5 + 16 * t, voltage, color=BLUE, linewidth=1.05, alpha=alpha, zorder=4)
    _text(ax, 5.3, 38.6, "Vm", 5.7, scale, color=MUTED)
    _text(ax, 18.4, 25.5, "time", 5.7, scale, color=MUTED)
    _text(ax, 4, 21.1, "Neo file readers", 7.4, scale, weight="bold")
    _text(ax, 4, 18.3, "traces + metadata", 7.0, scale, color=MUTED)


def _configuration_panel(ax, scale):
    _text(ax, 29.5, 46.7, "02  CONFIGURE", 8.5, scale, weight="bold")
    ax.add_patch(
        Rectangle(
            (35.1, 27.6), 6.4, 12.4, facecolor="#E9F5F1", edgecolor="none", zorder=2.5
        )
    )
    _plot_axes(ax, 31, 27.6, 14.5, 12.4)
    ax.plot(
        [31, 45.5],
        [31.8, 31.8],
        color=TEAL,
        linewidth=0.8,
        linestyle=(0, (2, 2)),
        alpha=0.7,
        zorder=3,
    )
    t = np.linspace(0, 1, 300)
    # One action potential: rapid upstroke, slower repolarization, then AHP.
    sigmoid = lambda x: 1.0 / (1.0 + np.exp(-x))
    spike = 7.2 * (sigmoid((t - 0.474) / 0.003) - sigmoid((t - 0.501) / 0.009))
    threshold_rise = 0.4 * np.exp(-(((t - 0.459) / 0.023) ** 2))
    ahp = 1.4 * np.exp(-(((t - 0.545) / 0.045) ** 2))
    response = 31.8 + threshold_rise + spike - ahp
    ax.plot(31 + 14.5 * t, response, color=TEAL, linewidth=1.25, zorder=4)
    _text(ax, 35.3, 39.0, "analysis epoch", 5.6, scale, color=TEAL)
    _text(ax, 29.5, 21.1, "Sweeps + epochs", 7.0, scale, weight="bold")
    _text(ax, 29.5, 18.3, "baseline + filters", 6.9, scale, color=MUTED)


def _analysis_panel(ax, scale):
    _text(ax, 54.5, 46.7, "03  ANALYSIS CORE", 8.5, scale, weight="bold")
    panels = (
        (55.1, 32.0, "Passive", PURPLE),
        (67.0, 32.0, "Spikes", BLUE),
        (55.1, 22.1, "Synaptic", TEAL),
        (67.0, 22.1, "Evoked", AMBER),
    )
    for left, bottom, label, color in panels:
        _text(ax, left, bottom + 8.1, label, 6.8, scale, color=color, weight="bold")
        _plot_axes(ax, left, bottom, 9.5, 6.8)

    t = np.linspace(0, 1, 150)
    passive = np.full_like(t, 36.7)
    active = (t >= 0.27) & (t <= 0.78)
    passive[active] = 34.1 + 0.7 * (1 - np.exp(-(t[active] - 0.27) / 0.22))
    ax.plot(55.1 + 9.5 * t, passive, color=PURPLE, linewidth=1.1, zorder=4)
    spike = 34.0 + 4.2 * np.exp(-(((t - 0.49) / 0.045) ** 2))
    spike -= 0.9 * np.exp(-(((t - 0.59) / 0.075) ** 2))
    ax.plot(67.0 + 9.5 * t, spike, color=BLUE, linewidth=1.1, zorder=4)
    synaptic = np.full_like(t, 27.0)
    for center in (0.27, 0.64):
        dt = t - center
        synaptic -= np.where(dt >= 0, 2.1 * np.exp(-np.maximum(dt, 0) / 0.12), 0)
    ax.plot(55.1 + 9.5 * t, synaptic, color=TEAL, linewidth=1.1, zorder=4)
    evoked = 23.0 + 2.4 * np.exp(-(((t - 0.31) / 0.09) ** 2))
    evoked += 1.6 * np.exp(-(((t - 0.68) / 0.11) ** 2))
    ax.plot(67.0 + 9.5 * t, evoked, color=AMBER, linewidth=1.1, zorder=4)
    _text(
        ax,
        54.5,
        18.3,
        "registry + user plugins",
        7.1,
        scale,
        color=PURPLE,
        weight="bold",
    )


def _output_panel(ax, scale):
    _text(ax, 84.2, 46.7, "04  OUTPUT", 8.5, scale, weight="bold")
    _text(ax, 84.5, 42.1, "feature table", 6.8, scale, weight="bold")
    ax.add_patch(
        Rectangle(
            (84.5, 29.2),
            11.7,
            10.6,
            facecolor="white",
            edgecolor=GRID,
            linewidth=0.7,
            zorder=3,
        )
    )
    ax.add_patch(
        Rectangle(
            (84.5, 36.8), 11.7, 3, facecolor="#F2F5F7", edgecolor="none", zorder=3
        )
    )
    for y in (36.8, 33.0):
        ax.plot([84.5, 96.2], [y, y], color=GRID, linewidth=0.65, zorder=4)
    for x in (88.3, 93.0):
        ax.plot([x, x], [29.2, 39.8], color=GRID, linewidth=0.65, zorder=4)
    for x, label in ((85.0, "file"), (88.7, "RMP"), (93.4, "AP")):
        _text(ax, x, 38.2, label, 5.4, scale, weight="bold")
    for y, values in ((34.8, ("01", "−64", "3")), (31.1, ("02", "−67", "5"))):
        for x, value in zip((85.0, 88.7, 93.4), values):
            _text(ax, x, y, value, 5.4, scale, color=MUTED)
    _text(ax, 84.5, 26.5, "illustrative values", 5.7, scale, color=MUTED)
    _text(ax, 84.5, 22.1, "CSV metrics", 6.9, scale, weight="bold")
    _text(ax, 84.5, 18.7, "NWB archive", 6.9, scale, weight="bold")


def _workflow_band(ax, scale):
    ax.add_patch(
        Rectangle(
            (2.5, 3.4),
            95,
            9.6,
            facecolor="#F5F8FA",
            edgecolor="none",
            zorder=2,
        )
    )
    ax.plot([2.5, 97.5], [13, 13], color=GRID, linewidth=0.8, zorder=3)
    for x in (33.5, 66.5):
        ax.plot([x, x], [4.7, 11.7], color=GRID, linewidth=0.7, zorder=3)
    _text(ax, 5, 9.7, "INTERACTIVE GUI", 7.8, scale, color=TEAL, weight="bold")
    _text(ax, 5, 6.3, "inspect + tune", 6.9, scale, color=MUTED)
    _text(ax, 36, 9.7, "SHARED PARAMETERS", 7.8, scale, color=BLUE, weight="bold")
    _text(ax, 36, 6.3, "saved configuration", 6.9, scale, color=MUTED)
    _text(ax, 69, 9.7, "HEADLESS BATCH", 7.8, scale, color=PURPLE, weight="bold")
    _text(ax, 69, 6.3, "same functions, many files", 6.9, scale, color=MUTED)
    _arrow(ax, (30.8, 8.2), (35.1, 8.2), BLUE)
    _arrow(ax, (63.8, 8.2), (68.1, 8.2), PURPLE)


def draw_panel_a(ax, font_scale=1.0):
    """Draw Figure 1A using vector lines, patches, and editable text."""
    ax.set_xlim(0, 100)
    ax.set_ylim(2, 52)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    ax.set_facecolor("white")
    ax.set_box_aspect(0.60)
    ax.set_anchor("N")

    for x, width, color in (
        (2.5, 21, BLUE),
        (28, 20, TEAL),
        (53, 25, PURPLE),
        (83, 14.5, AMBER),
    ):
        _stage(ax, x, width, color)
    _arrow(ax, (23.6, 33), (27.8, 33), BLUE)
    _arrow(ax, (48.1, 33), (52.8, 33), TEAL)
    _arrow(ax, (78.1, 33), (82.8, 33), PURPLE)
    _arrow(ax, (75, 13.1), (75, 15.8), PURPLE)

    _input_panel(ax, font_scale)
    _configuration_panel(ax, font_scale)
    _analysis_panel(ax, font_scale)
    _output_panel(ax, font_scale)
    _workflow_band(ax, font_scale)


def save_panel_a_svg(path=None):
    """Save a standalone SVG with editable text and vector shapes."""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "figures" / "figure_01_panel_a.svg"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with plt.rc_context({"svg.fonttype": "none", "font.family": "DejaVu Sans"}):
        fig, ax = plt.subplots(figsize=(10, 6))
        fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
        draw_panel_a(ax, font_scale=1.65)
        fig.savefig(path, format="svg", facecolor="white")
        plt.close(fig)
    return path


if __name__ == "__main__":
    print(f"Saved {save_panel_a_svg()}")
