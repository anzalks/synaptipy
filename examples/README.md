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
| [05_protocol_aware_batch.py](05_protocol_aware_batch.py) | Canonical current workflow: reviewed protocol assignments, selected trials, compatible cross-file averaging, and provenance-preserving CSV output |

**Sample data** for the notebooks lives in `data/`
(ABF and WCP whole-cell patch-clamp recordings).

---

## Section 2: GUI Plugin Templates

The files in `plugins/` are **`@AnalysisRegistry.register` UI plugins**
that integrate directly into the Analyser tab - they are **not** standalone
scripts and are not executed directly from the command line.

| Plugin file | Analyser tab label | What it measures |
|---|---|---|
| `plugins/synaptic_charge.py` | Synaptic Charge (AUC) | Postsynaptic charge (`pC`) or potential AUC (`mV*ms`) via trapezoidal integration; shaded fill, baseline line, and peak star overlay |
| `plugins/opto_jitter.py` | Opto Latency Jitter | Trial-to-trial evoked spike or EPSP/EPSC latency jitter after TTL pulses (requires a TTL channel) |
| `plugins/miniml_integration.py` | miniML Events | Deep-learning synaptic event detection via `delvendahl/miniML` using a pre-trained Keras model |
| `plugins/spike_interface_integration.py` | Spike Detection (SpikeInterface) | Extracellular spike detection and sorting wrapper integrating `SpikeInterface` pipelines |

The plugin API supports optional `protocol_requirements`, `supported_channel_units`,
and a dictionary-valued `requires_secondary_channel` declaration. Use the TTL
selector declaration for stimulus-dependent plugins; batch pipelines then set
`secondary_channel` to the channel ID or native channel name used in every file.

To activate: check **Enable Custom Plugins** in
**Edit > Preferences > Extensions** (or **Synaptipy > Preferences** on macOS).
Plugins hot-reload in-process without restarting the application. Copy any file
to `~/.synaptipy/plugins/` (or select **Help > Download Example Plugins...**) to
create a personal variant.

See [docs/extending_synaptipy.md](../docs/extending_synaptipy.md) for a
complete guide to writing your own plugin.

---

## miniML Plugin Setup

The `miniml_integration.py` plugin adds a deep-learning event detector
([delvendahl/miniML](https://github.com/delvendahl/miniML)) as an Analyser tab.
Follow these steps carefully to avoid environment conflicts.

### Step 1 - Clone miniML (once, outside the Synaptipy directory)

```bash
git clone https://github.com/delvendahl/miniML.git ~/miniML
```

Do **not** clone it inside the Synaptipy repo so git does not track it.
The exact location does not matter; you will browse to it in the GUI.

### Step 2 - Install miniML's Python dependencies into the Synaptipy env

```bash
conda activate synaptipy
pip install "tensorflow>=2.17" tf_keras h5py scikit-learn ruptures==1.1.10
```

> **TensorFlow version note:** Synaptipy requires `numpy>=2.0`.
> TensorFlow 2.15 and earlier use deprecated NumPy 1.x internals and crash on
> import. TensorFlow `>=2.17` is compatible with NumPy 2.x.
>
> TensorFlow 2.16+ ships Keras 3 by default; `GC_lstm_model.h5` bundled with
> miniML was saved under Keras 2. The `tf_keras` package provides the Keras 2
> compatibility layer, and the plugin sets `TF_USE_LEGACY_KERAS=1` automatically.

> **Do NOT run `pip install -r ~/miniML/requirements.txt`.**
> That file pins `numpy==1.23.5` and `pandas==1.5.3`, which conflict with
> Synaptipy's `numpy>=2.0` requirement and break `np.trapezoid` calls.
>
> If you accidentally ran it, restore the supported versions with:
>
> ```bash
> conda activate synaptipy
> pip install --force-reinstall "numpy>=2.0,<3" "pandas>=2.3.0"
> ```

### Step 3 - Install the plugin

Copy the plugin file to your personal plugins directory:

```bash
mkdir -p ~/.synaptipy/plugins
cp examples/plugins/miniml_integration.py ~/.synaptipy/plugins/
```

Then open Synaptipy, go to **Edit > Preferences > Extensions**, and check
**Enable Custom Plugins** (plugins reload immediately in-process).

### Step 4 - Use the miniML Events tab

1. Open a recording in the Explorer tab and switch to the Analyser tab.
2. Select the **miniML Events** sub-tab.
3. Click **Browse...** next to **miniML core/ Path** and select the `core/`
   sub-directory inside the cloned miniML repo (e.g. `~/miniML/core/`).
4. Click **Browse...** next to **Model Path (.h5)** and select a `.h5` model
   file in `models/` (e.g. `~/miniML/models/GC_lstm_model.h5`).
5. Adjust **Prediction Threshold** and **Direction** as needed.
6. Click **Run Analysis**.

### Conda environment / NumPy version notes

- `pip install -e ".[dev]"` installs packages according to `pyproject.toml`
  (`numpy>=2.0`). Verify NumPy afterward with
  `python -c "import numpy; print(numpy.__version__)"`.
- Do not mix `conda install numpy` and `pip install numpy` in the same
  environment - their file trees differ and can leave stale `.dist-info` metadata.
- Validate any alternate TensorFlow or Keras version in a separate environment
  before modifying your primary `synaptipy` installation.
