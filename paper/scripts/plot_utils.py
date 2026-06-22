import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Core Color Palette (Colorblind-friendly where possible)
# ---------------------------------------------------------------------------
COLORS = {
    "blue": "#1565C0",
    "light_blue": "#90CAF9",
    "red": "#B71C1C",
    "light_red": "#EF9A9A",
    "orange": "#E65100",
    "green": "#4CAF50",
    "light_green": "#81C784",
    "dark_grey": "#424242",
    "grey": "#9E9E9E",
    "light_grey": "#BDBDBD",
    "very_light_grey": "#E0E0E0",
    "black": "#000000",
    "white": "#FFFFFF",
}

# ---------------------------------------------------------------------------
# Global Design Tokens (eNeuro Guidelines)
# ---------------------------------------------------------------------------
FONT_FAMILY = "sans-serif"
FONT_SANS_SERIF = ["Arial", "Helvetica", "DejaVu Sans"]

# Font Sizes
SUPTITLE_SIZE = 14
TITLE_SIZE = 12
PANEL_LABEL_SIZE = 14
AXES_LABEL_SIZE = 10
TICK_LABEL_SIZE = 8
LEGEND_SIZE = 8

# Aesthetics
LINE_WIDTH = 2.0
MARKER_SIZE = 5
ERRORBAR_CAPSIZE = 6

# Geometry & Transparencies
BAR_WIDTH = 0.6
SCATTER_AREA = 50
SCATTER_EDGE_WIDTH = 0.75
ALPHA_SOLID = 0.9
ALPHA_MUTED = 0.8
ALPHA_FAINT = 0.6


# ---------------------------------------------------------------------------
# 1. Global Setup
# ---------------------------------------------------------------------------
def set_paper_styles():
    """Apply standard eNeuro aesthetics to matplotlib globally."""
    plt.rcParams["font.family"] = FONT_FAMILY
    plt.rcParams["font.sans-serif"] = FONT_SANS_SERIF
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.labelsize"] = AXES_LABEL_SIZE
    plt.rcParams["axes.titlesize"] = TITLE_SIZE
    plt.rcParams["xtick.labelsize"] = TICK_LABEL_SIZE
    plt.rcParams["ytick.labelsize"] = TICK_LABEL_SIZE
    plt.rcParams["legend.fontsize"] = LEGEND_SIZE
    plt.rcParams["lines.linewidth"] = LINE_WIDTH
    plt.rcParams["lines.markersize"] = MARKER_SIZE
    plt.rcParams["errorbar.capsize"] = ERRORBAR_CAPSIZE
    plt.rcParams["lines.markeredgewidth"] = 1.5  # Controls cap thickness globally


# ---------------------------------------------------------------------------
# 2. Figure Generation & Typography Standardizers
# ---------------------------------------------------------------------------
def create_paper_figure(nrows=1, ncols=1, figsize=None):
    """Standardized figure creation for eNeuro sizing."""
    if nrows == 0 and ncols == 0:
        return plt.figure(figsize=figsize if figsize else (18, 12))
    return plt.subplots(nrows, ncols, figsize=figsize if figsize else (12, 10))


def save_paper_figure(fig, filename, rect=[0, 0, 1, 0.95], dpi=300):
    """Standardized layout application and saving."""
    fig.tight_layout(rect=rect)
    fig.savefig(filename, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def add_figure_suptitle(fig, title, y=1.02):
    """Standardized overarching figure title."""
    fig.suptitle(title, fontsize=SUPTITLE_SIZE, fontweight="bold", y=y)


def add_panel_title(ax, title, pad=15):
    """Standardized subplot title."""
    ax.set_title(title, fontsize=TITLE_SIZE, pad=pad)


def add_panel_label(ax, label, x=-0.15, y=1.05):
    """Standardized panel label generator (A, B, C...)."""
    ax.text(x, y, label, transform=ax.transAxes, fontsize=PANEL_LABEL_SIZE, fontweight="bold", va="top", ha="right")


def add_legend(ax, loc="best", **kwargs):
    """Standardized legend."""
    ax.legend(fontsize=LEGEND_SIZE, loc=loc, frameon=False, **kwargs)


# ---------------------------------------------------------------------------
# 3. Axis Formatters by Plot Type
# ---------------------------------------------------------------------------
def _apply_axis_labels(ax, xlabel, ylabel, xticks, xticklabels):
    """Internal helper to apply standardized labels and ticks."""
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)
    if xticks is not None:
        ax.set_xticks(xticks)
    if xticklabels is not None:
        ax.set_xticklabels(xticklabels)


def style_line_axis(ax, xlabel=None, ylabel=None, xticks=None, xticklabels=None):
    """Standard styling for line/errorbar plots (time series, speedup curves)."""
    _apply_axis_labels(ax, xlabel, ylabel, xticks, xticklabels)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def style_bar_axis(ax, xlabel=None, ylabel=None, xticks=None, xticklabels=None):
    """Standard styling for bar plots (absolute values, fractions)."""
    _apply_axis_labels(ax, xlabel, ylabel, xticks, xticklabels)
    # Grid only on y-axis for bar plots
    ax.grid(axis="y", alpha=0.3, linestyle="--")
    ax.grid(axis="x", visible=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def style_scatter_axis(ax, unity_line=False, lims=None, xlabel=None, ylabel=None, xticks=None, xticklabels=None):
    """Standard styling for scatter plots (e.g. biological validation)."""
    _apply_axis_labels(ax, xlabel, ylabel, xticks, xticklabels)
    ax.grid(True, alpha=0.3, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Optional unity line for correlation scatters
    if unity_line and lims is not None:
        ax.plot(lims, lims, "--", color=COLORS["grey"], alpha=0.5, zorder=0, label="Unity (y=x)")


def add_threshold_line(ax, y_val, label="Threshold"):
    """Standardized grey threshold line."""
    ax.axhline(y_val, color=COLORS["grey"], linestyle=":", alpha=0.5, label=label)


def style_trace_axis(ax, hide_x=False):
    """Standard styling for raw electrophysiology traces (removes all spines)."""
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    if hide_x:
        ax.spines["bottom"].set_visible(False)
        ax.set_xticks([])
    ax.set_yticks([])


def bland_altman_plot(ax, x, y, color, label, marker="o"):
    """Standardized Bland-Altman Limits of Agreement plotting."""
    import numpy as np

    mean_val = (x + y) / 2.0
    diff = y - x  # SynaptiPy - Benchmark

    md = np.mean(diff)
    sd = np.std(diff, axis=0, ddof=1)
    loa_upper = md + 1.96 * sd
    loa_lower = md - 1.96 * sd

    from scipy.stats import pearsonr

    r_val, p_val = pearsonr(x, y)
    p_str = "< 0.0001" if p_val < 0.0001 else f"= {p_val:.4f}"

    full_label = f"{label}\n(r={r_val:.4f}, p{p_str})\nBias: {md:+.2f}"

    ax.scatter(
        mean_val,
        diff,
        color=color,
        s=SCATTER_AREA,
        edgecolors=COLORS["white"],
        linewidths=SCATTER_EDGE_WIDTH,
        marker=marker,
        label=full_label,
        alpha=0.7,
        zorder=3,
    )

    # Plot horizontal lines for mean and LoA
    ax.axhline(md, color=color, linestyle="-", linewidth=1.5, zorder=2, label=f"Mean Bias ({md:+.2f})")
    ax.axhline(loa_upper, color=color, linestyle="--", linewidth=1.0, alpha=0.8, zorder=2, label="95% LoA (Upper)")
    ax.axhline(loa_lower, color=color, linestyle="--", linewidth=1.0, alpha=0.8, zorder=2, label="95% LoA (Lower)")

    return md, loa_upper, loa_lower
