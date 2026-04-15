# Synaptipy Examples

This directory contains runnable examples that demonstrate Synaptipy's
programmatic API and plugin system.

## Jupyter Notebooks

| Notebook | Description |
|---|---|
| [01_batch_analysis.ipynb](01_batch_analysis.ipynb) | Load ABF files, run spike detection across multiple recordings, export a Pandas DataFrame to CSV |
| [02_optogenetics.ipynb](02_optogenetics.ipynb) | Extract TTL epochs, correlate spikes with optical stimuli, compute optical latency and response probability |
| [03_custom_plugin.ipynb](03_custom_plugin.ipynb) | Walk through creating a custom analysis plugin using `@AnalysisRegistry.register` |

## Python Script

| Script | Description |
|---|---|
| [basic_usage.py](basic_usage.py) | Minimal script showing the `Recording` / `Channel` data model and `calculate_input_resistance` |

## Sample Data

The `data/` folder contains sample recordings for testing:

| File | Format | Description |
|---|---|---|
| `2023_04_11_0018.abf` | Axon Binary | Whole-cell patch-clamp recording |
| `2023_04_11_0019.abf` | Axon Binary | Whole-cell patch-clamp recording |
| `2023_04_11_0021.abf` | Axon Binary | Whole-cell patch-clamp recording |
| `2023_04_11_0022.abf` | Axon Binary | Whole-cell patch-clamp recording |
| `240326_003.wcp` | WinWCP | Whole-cell patch-clamp recording |

## Example Plugins

The `plugins/` folder contains ready-to-run analysis plugins that demonstrate
Synaptipy's plugin system and serve as copyable templates:

| Plugin file | Analyser tab label | What it measures |
|-------------|--------------------|------------------|
| `plugins/synaptic_charge.py` | Synaptic Charge (AUC) | Integrates a postsynaptic current trace over a user-defined window; reports total charge (pC) and peak amplitude, with a shaded fill overlay and a star at the peak |
| `plugins/opto_jitter.py` | Opto Latency Jitter | Trial-to-trial latency jitter of the first spike following an optogenetic TTL pulse (requires a secondary digital channel) |
| `plugins/ap_repolarization.py` | AP Repolarization Rate | Maximum repolarization rate (dV/dt minimum) of the first action potential in a search window |

These plugins are loaded automatically when **Enable Custom Plugins** is checked
in **Edit > Preferences** (or **Synaptipy > Preferences** on macOS).  Copy any
file to `~/.synaptipy/plugins/` to create a personal variant that takes
precedence over the bundled copy.

## Batch Processing

The `BatchAnalysisEngine` can chain any registered analysis (built-in or plugin)
across multiple files. Results are exported to a Pandas DataFrame with
standardised metadata columns, suitable for direct import into Python, R, or
MATLAB. See [01_batch_analysis.ipynb](01_batch_analysis.ipynb) for a full
walkthrough.

## Running

```bash
# From the repository root
pip install -e .
pip install jupyter matplotlib pandas

cd examples
jupyter notebook
```
