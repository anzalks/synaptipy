import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# Import unified plot formatting
from plot_utils import set_paper_styles, add_panel_label, COLORS

set_paper_styles()

base = Path("paper/results")

# ---------------------------------------------------------
# Figure 1: benchmark_scaling.png
# ---------------------------------------------------------
bench_res = []
with open(base / "benchmark_results.csv", "r") as f:
    for row in csv.DictReader(f):
        bench_res.append(row)

datasets = list(dict.fromkeys(r["dataset"] for r in bench_res))
colors = {"0021 spike_detection": COLORS["blue"], "0022 event_detection": COLORS["red"]}
markers = {"0021 spike_detection": "o", "0022 event_detection": "s"}
panel_labels = ["A", "B", "C", "D"]

fig1, axes1 = plt.subplots(2, 2, figsize=(12, 9))

for row_idx, label in enumerate(datasets):
    rows = [r for r in bench_res if r["dataset"] == label]
    workers = [int(r["max_workers"]) for r in rows]
    times = [float(r["median_time_s"]) for r in rows]
    err_lo = [float(r["median_time_s"]) - float(r["min_time_s"]) for r in rows]
    err_hi = [float(r["max_time_s"]) - float(r["median_time_s"]) for r in rows]

    color = colors.get(label, COLORS["dark_grey"])
    marker = markers.get(label, "o")

    # Time plot
    ax_time = axes1[row_idx, 0]
    ax_time.errorbar(workers, times, yerr=[err_lo, err_hi], fmt=marker+'-', color=color, ecolor=COLORS["light_grey"], capsize=5, linewidth=2, markersize=7, label="Median wall-clock time (± min-max)")
    baseline = times[0]
    ax_time.plot(workers, [baseline / w for w in workers], "--", color=COLORS["grey"], linewidth=1, label="Ideal T\u2081/N")
    ax_time.set_xlabel("CPU Cores (max_workers)")
    ax_time.set_ylabel("Elapsed Time (s)")
    add_panel_label(ax_time, panel_labels[row_idx * 2])
    ax_time.set_xticks(workers)
    ax_time.legend()

    # Speedup plot
    ax_speedup = axes1[row_idx, 1]
    speedup = [baseline / t for t in times]
    ax_speedup.plot(workers, speedup, marker+'-', color=color, linewidth=2, markersize=7, label="Measured speedup")
    ax_speedup.plot(workers, [float(w) for w in workers], "k--", linewidth=1, label="Ideal linear S=W")
    ax_speedup.set_xlabel("CPU Cores (max_workers)")
    ax_speedup.set_ylabel("Speedup (S = T\u2081 / T_W)")
    add_panel_label(ax_speedup, panel_labels[row_idx * 2 + 1])
    ax_speedup.set_xticks(workers)
    ax_speedup.legend()

fig1.tight_layout()
fig1.savefig(base / "benchmark_scaling.png", dpi=300)
plt.close(fig1)

# ---------------------------------------------------------
# Figure 2: rendering_benchmark.png
# ---------------------------------------------------------
opengl_data = {}
software_data = {}
with open(base / "rendering_results.csv", "r") as f:
    for row in csv.DictReader(f):
        mode = row["renderer"]
        n = int(row["n_trials"])
        stats = {
            "median_ms": float(row["median_ms"]),
            "p05_ms": float(row["p05_ms"]),
            "p95_ms": float(row["p95_ms"])
        }
        if mode == "opengl": opengl_data[n] = stats
        elif mode == "software": software_data[n] = stats

levels = sorted(opengl_data.keys())
med_gl = [opengl_data[n]["median_ms"] for n in levels]
lo_gl = [opengl_data[n]["median_ms"] - opengl_data[n]["p05_ms"] for n in levels]
hi_gl = [opengl_data[n]["p95_ms"] - opengl_data[n]["median_ms"] for n in levels]

med_sw = [software_data[n]["median_ms"] for n in levels]
lo_sw = [software_data[n]["median_ms"] - software_data[n]["p05_ms"] for n in levels]
hi_sw = [software_data[n]["p95_ms"] - software_data[n]["median_ms"] for n in levels]

fig2, (ax_abs, ax_ratio) = plt.subplots(1, 2, figsize=(12, 4.5))

# Line plot
ax_abs.errorbar(levels, med_gl, yerr=[lo_gl, hi_gl], fmt="o-", color=COLORS["blue"], ecolor=COLORS["light_blue"], capsize=4, linewidth=2, markersize=6, label="OpenGL (Median ± 5th/95th pct)")
ax_abs.errorbar(levels, med_sw, yerr=[lo_sw, hi_sw], fmt="s--", color=COLORS["red"], ecolor=COLORS["light_red"], capsize=4, linewidth=2, markersize=6, label="Software (Median ± 5th/95th pct)")
ax_abs.set_xlabel("Overlaid trials (N)")
ax_abs.set_ylabel("Per-frame update time (ms)")
ax_abs.set_xticks(levels)
ax_abs.legend()
add_panel_label(ax_abs, "A")

# Bar chart
width = 0.35
x = np.arange(len(levels))
ax_ratio.bar(x - width/2, med_sw, width, label="Software (Median ± 5th/95th pct)", color=COLORS["red"], yerr=[lo_sw, hi_sw], capsize=4, error_kw={"ecolor": COLORS["light_red"]})
ax_ratio.bar(x + width/2, med_gl, width, label="OpenGL (Median ± 5th/95th pct)", color=COLORS["blue"], yerr=[lo_gl, hi_gl], capsize=4, error_kw={"ecolor": COLORS["light_blue"]})
ax_ratio.set_xticks(x)
ax_ratio.set_xticklabels([str(n) for n in levels])
ax_ratio.set_xlabel("Overlaid trials (N)")
ax_ratio.set_ylabel("Per-frame update time (ms)")
ax_ratio.legend()
add_panel_label(ax_ratio, "B")

fig2.tight_layout()
fig2.savefig(base / "rendering_benchmark.png", dpi=300)
plt.close(fig2)

# ---------------------------------------------------------
# Figure 3: e2e_rendering_benchmark_macos.png
# ---------------------------------------------------------
sw_ov = []
gl_ov = []
sw_cs = None
gl_cs = None
with open(base / "e2e_rendering_results_macos.csv", "r") as f:
    for row in csv.DictReader(f):
        entry = {
            "n_trials": int(row["n_trials"]),
            "median_ms": float(row["median_ms"]),
            "p05_ms": float(row["p05_ms"]),
            "p95_ms": float(row["p95_ms"])
        }
        if row["renderer"] == "software":
            if row["benchmark_mode"] == "overlay_avg": sw_ov.append(entry)
            else: sw_cs = entry
        elif row["renderer"] == "opengl":
            if row["benchmark_mode"] == "overlay_avg": gl_ov.append(entry)
            else: gl_cs = entry

sw_ov = sorted(sw_ov, key=lambda x: x["n_trials"])
gl_ov = sorted(gl_ov, key=lambda x: x["n_trials"])
levels3 = [e["n_trials"] for e in sw_ov]

sw_med = [e["median_ms"] for e in sw_ov]
sw_lo = [e["median_ms"] - e["p05_ms"] for e in sw_ov]
sw_hi = [e["p95_ms"] - e["median_ms"] for e in sw_ov]

gl_med = [e["median_ms"] for e in gl_ov]
gl_lo = [e["median_ms"] - e["p05_ms"] for e in gl_ov]
gl_hi = [e["p95_ms"] - e["median_ms"] for e in gl_ov]

fig3, (ax3a, ax3b) = plt.subplots(1, 2, figsize=(12, 4.5))

# Line plot
ax3a.errorbar(levels3, sw_med, yerr=[sw_lo, sw_hi], fmt="s--", color=COLORS["red"], ecolor=COLORS["light_red"], capsize=4, linewidth=2, markersize=6, label="Software (Median ± 5th/95th pct)")
ax3a.errorbar(levels3, gl_med, yerr=[gl_lo, gl_hi], fmt="o-", color=COLORS["blue"], ecolor=COLORS["light_blue"], capsize=4, linewidth=2, markersize=6, label="OpenGL (Median ± 5th/95th pct)")
ax3a.set_xlabel("Overlaid trials (N)")
ax3a.set_ylabel("_update_plot() time (ms)")
ax3a.set_xticks(levels3)
ax3a.legend()
add_panel_label(ax3a, "A")

# Bar chart
x3 = np.arange(len(levels3))
ax3b.bar(x3 - width/2, sw_med, width, label="Software (Median ± 5th/95th pct)", color=COLORS["red"], yerr=[sw_lo, sw_hi], capsize=4, error_kw={"ecolor": COLORS["light_red"]})
ax3b.bar(x3 + width/2, gl_med, width, label="OpenGL (Median ± 5th/95th pct)", color=COLORS["blue"], yerr=[gl_lo, gl_hi], capsize=4, error_kw={"ecolor": COLORS["light_blue"]})
ax3b.set_xticks(x3)
ax3b.set_xticklabels([str(n) for n in levels3])
ax3b.set_xlabel("Overlaid trials (N)")
ax3b.set_ylabel("Frame time (ms)")
ax3b.legend()
add_panel_label(ax3b, "B")

fig3.tight_layout()
fig3.savefig(base / "e2e_rendering_benchmark_macos.png", dpi=300)
plt.close(fig3)

print("All figures generated successfully with eNeuro styling!")
