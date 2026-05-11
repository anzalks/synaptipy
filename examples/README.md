# Synaptipy Examples

This directory is split into two distinct categories.

---

## Section 1: Programmatic & Headless Scripts

These files run without the GUI and are intended for batch processing,
programmatic data access, and generating publication-quality figures.
All figures are saved to disk (`plt.savefig`) and the scripts close them
immediately (`plt.close('all')`), so they run cleanly in headless CI
environments.

| File | What it does |
|---|---|
| [basic_usage.py](basic_usage.py) | Minimal script: load synthetic data, compute input resistance, save a two-panel voltage/current figure with L-shaped scale bars |
| [01_batch_analysis.ipynb](01_batch_analysis.ipynb) | Load ABF files, run spike detection across recordings, plot raw traces with scale bars and per-file spike counts as a strip plot, export results to CSV |
| [02_optogenetics.ipynb](02_optogenetics.ipynb) | Simulate TTL-driven spiking, extract TTL epochs, compute optical latency/response probability, generate raster and PSTH figures |
| [03_custom_plugin.ipynb](03_custom_plugin.ipynb) | Walkthrough of creating a custom analysis plugin with `@AnalysisRegistry.register` |

**Sample data** for the notebooks lives in `data/`
(ABF and WCP whole-cell patch-clamp recordings).

---

## Section 2: GUI Plugin Templates

The files in `plugins/` are **`@AnalysisRegistry.register` UI templates**
that integrate directly into the Analyser tab -- they are **not** standalone
scripts and cannot be executed directly from the command line.

| Plugin file | Analyser tab label | What it measures |
|---|---|---|
| `plugins/synaptic_charge.py` | Synaptic Charge (AUC) | Postsynaptic charge (pC) via trapezoidal integration; shaded fill + peak star overlay |
| `plugins/opto_jitter.py` | Opto Latency Jitter | Trial-to-trial spike-latency jitter after an optogenetic TTL pulse (requires a TTL channel) |
| `plugins/ap_repolarization.py` | AP Repolarization Rate | Maximum repolarization rate (dV/dt minimum) of the first action potential in a search window |
| `plugins/miniml_integration.py` | miniML Events | Demonstrates deep-learning integration via delvendahl/miniML for synaptic event detection using a pre-trained Keras model. |

To activate: check **Enable Custom Plugins** in
**Edit > Preferences** (or **Synaptipy > Preferences** on macOS), then
restart. Copy any file to `~/.synaptipy/plugins/` to create a personal variant.

See [docs/extending_synaptipy.md](../docs/extending_synaptipy.md) for a
complete guide to writing your own plugin.
