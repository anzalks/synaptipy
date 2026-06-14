import matplotlib.pyplot as plt

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
}


def set_paper_styles():
    """Apply standard eNeuro aesthetics to matplotlib rcParams."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.labelsize"] = 11
    plt.rcParams["axes.titlesize"] = 12
    plt.rcParams["xtick.labelsize"] = 10
    plt.rcParams["ytick.labelsize"] = 10
    plt.rcParams["legend.fontsize"] = 9


def add_panel_label(ax, label, x=-0.15, y=1.05):
    """
    Standardized panel label generator to ensure 100% identical
    typography across all figures.
    """
    ax.text(x, y, label, transform=ax.transAxes, fontsize=16, fontweight="bold", va="top", ha="right")
