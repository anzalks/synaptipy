# Synaptipy Examples

This directory contains runnable examples that demonstrate Synaptipy's
programmatic API.

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

## Running

```bash
# From the repository root
pip install -e .
pip install jupyter matplotlib pandas

cd examples
jupyter notebook
```
