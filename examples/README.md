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

---

## miniML Plugin Setup

The `miniml_integration.py` plugin adds a deep-learning event detector
([delvendahl/miniML](https://github.com/delvendahl/miniML)) as an Analyser tab.
Follow these steps exactly to avoid environment breakage.

### Step 1 — Clone miniML (once, outside the Synaptipy directory)

```bash
git clone https://github.com/delvendahl/miniML.git ~/miniML
```

Do **not** clone it inside the Synaptipy repo — git would track it.
The exact location does not matter; you will browse to it in the GUI.

### Step 2 — Install miniML's Python dependencies into the Synaptipy env

```bash
conda activate synaptipy
pip install "tensorflow>=2.17" tf_keras scikit-learn ruptures==1.1.10
```

> **TensorFlow version note:** Synaptipy requires numpy >= 2.0.
> TensorFlow 2.15 and earlier use deprecated numpy 1.x internals and will
> crash on import.  TensorFlow >= 2.17 is the first release fully compatible
> with numpy 2.x.
>
> TensorFlow 2.16+ ships Keras 3 by default; the `GC_lstm_model.h5` bundled
> with miniML was saved under Keras 2.  The `tf_keras` package (installed
> above) provides a Keras 2 compatibility layer.  The plugin sets
> `TF_USE_LEGACY_KERAS=1` automatically so you do not need to do anything
> extra.

> **Do NOT run `pip install -r ~/miniML/requirements.txt`.**
> That file pins `numpy==1.23.5` and `pandas==1.5.3`, which are
> incompatible with Synaptipy's `numpy>=2.0` requirement.
> Installing it will silently downgrade numpy and break all `np.trapezoid`
> calls throughout Synaptipy (they will raise `AttributeError`).
>
> If you accidentally ran it, restore the correct versions with:
> ```bash
> conda activate synaptipy
> pip install --force-reinstall "numpy>=2.0,<3" "pandas>=2.0"
> ```

### Step 3 — Install the plugin

Copy the plugin file to your personal plugins directory:

```bash
mkdir -p ~/.synaptipy/plugins
cp examples/plugins/miniml_integration.py ~/.synaptipy/plugins/
```

Then open Synaptipy, go to **Edit > Preferences**, check
**Enable Custom Plugins**, and restart.

### Step 4 — Use the miniML Events tab

1. Open a recording in the Explorer tab and switch to the Analyser tab.
2. Click the **miniML Events** sub-tab.
3. Click the **Browse...** button next to **miniML core/ Path** and navigate
   to the `core/` sub-directory inside the cloned miniML repo
   (e.g. `~/miniML/core/`).
4. Click the **Browse...** button next to **Model Path (.h5)** and navigate
   to a `.h5` model file in the `models/` sub-directory
   (e.g. `~/miniML/models/GC_lstm_model.h5`).
5. Adjust **Prediction Threshold** and **Direction** as needed.
6. Click **Run Analysis**.

### Conda environment / numpy version notes

- `pip install -e ".[dev]"` will install or upgrade packages according to
  `pyproject.toml` (which requires `numpy>=2.0`).  After running it, verify
  numpy is intact with `python -c "import numpy; print(numpy.__version__)"`.
  If you see `ModuleNotFoundError`, a partial uninstall left a stale dist-info;
  fix it with `pip install --force-reinstall numpy`.
- Never mix `conda install numpy` and `pip install numpy` in the same env —
  conda's numpy and pip's numpy have separate file trees and will clobber each
  other.  This env uses pip exclusively for numpy; keep it that way.
- TensorFlow 2.15 is compatible with numpy 2.x.  TensorFlow 2.16+ and 3.x
  require `tensorflow-macos` on Apple Silicon — stay on 2.15 unless you
  upgrade deliberately.
