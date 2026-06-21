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
    "dark_grey": "#424242",
    "grey": "#9E9E9E",
    "light_grey": "#BDBDBD",
    "very_light_grey": "#E0E0E0",
    "black": "#000000",
}

# ---------------------------------------------------------------------------
# Global Design Tokens (eNeuro Guidelines)
# ---------------------------------------------------------------------------
FONT_FAMILY = "sans-serif"
FONT_SANS_SERIF = ["Arial", "Helvetica", "DejaVu Sans"]

# Font Sizes
SUPTITLE_SIZE = 18
TITLE_SIZE = 14
PANEL_LABEL_SIZE = 16
AXES_LABEL_SIZE = 12
TICK_LABEL_SIZE = 10
LEGEND_SIZE = 10

# Aesthetics
LINE_WIDTH = 2.5
MARKER_SIZE = 8
ERRORBAR_CAPSIZE = 5

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

# ---------------------------------------------------------------------------
# 2. Typography Standardizers
# ---------------------------------------------------------------------------
def add_figure_suptitle(fig, title, y=1.02):
    """Standardized overarching figure title."""
    fig.suptitle(title, fontsize=SUPTITLE_SIZE, fontweight="bold", y=y)

def add_panel_title(ax, title, pad=15):
    """Standardized subplot title."""
    ax.set_title(title, fontsize=TITLE_SIZE, pad=pad)

def add_panel_label(ax, label, x=-0.15, y=1.05):
    """Standardized panel label generator (A, B, C...)."""
    ax.text(x, y, label, transform=ax.transAxes, fontsize=PANEL_LABEL_SIZE, fontweight="bold", va="top", ha="right")

def add_legend(ax, loc='best', **kwargs):
    """Standardized legend."""
    ax.legend(fontsize=LEGEND_SIZE, loc=loc, frameon=False, **kwargs)

# ---------------------------------------------------------------------------
# 3. Axis Formatters by Plot Type
# ---------------------------------------------------------------------------
def style_line_axis(ax):
    """Standard styling for line/errorbar plots (time series, speedup curves)."""
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

def style_bar_axis(ax):
    """Standard styling for bar plots (absolute values, fractions)."""
    # Grid only on y-axis for bar plots
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    ax.grid(axis='x', visible=False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

def style_scatter_axis(ax, unity_line=False, lims=None):
    """Standard styling for scatter plots (e.g. biological validation)."""
    ax.grid(True, alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    
    # Optional unity line for correlation scatters
    if unity_line and lims is not None:
        ax.plot(lims, lims, "--", color=COLORS["grey"], alpha=0.5, zorder=0, label="Unity (y=x)")

def style_trace_axis(ax, hide_x=False):
    """Standard styling for raw electrophysiology traces (removes all spines)."""
    ax.grid(False)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_visible(False)
    if hide_x:
        ax.spines['bottom'].set_visible(False)
        ax.set_xticks([])
    ax.set_yticks([])
