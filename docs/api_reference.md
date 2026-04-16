# Synaptipy API Reference

This document provides reference information for developers using Synaptipy as a library.

## Table of Contents

- [Core Components](#core-components)
 - [Data Model](#data-model)
 - [File Readers](#file-readers)
 - [Analysis](#analysis)
 - [Batch Processing](#batch-processing)
 - [Signal Processing](#signal-processing)
 - [Plugin System](#plugin-system)
 - [Exporters](#exporters)
- [Licensing](#licensing)

## Core Components

### Data Model

#### Recording

```python
from Synaptipy.core.data_model import Recording

# Create a new recording
recording = Recording(source_file=Path("/path/to/file.abf"))

# Access recording properties
sampling_rate = recording.sampling_rate
duration = recording.duration
channels = recording.channels

# Get a specific channel
channel = recording.get_channel_by_name("Vm")
```

#### Channel

```python
from Synaptipy.core.data_model import Channel

# A channel represents a single data stream
channel = Channel(
 id="ch1",
 name="Vm",
 units="mV",
 sampling_rate=10000.0,
 data_trials=[numpy_array_with_data]
)

# Access channel properties
name = channel.name
units = channel.units
data = channel.data_trials[0] # Get first trial's data
```

### File Readers

#### NeoAdapter

File reading is implemented via the [Neo](https://neo.readthedocs.io) library
(Garcia et al., 2014, *Frontiers in Neuroinformatics* 8:10,
[doi:10.3389/fninf.2014.00010](https://doi.org/10.3389/fninf.2014.00010)).
`NeoAdapter` translates Neo blocks into the Synaptipy core data model.

```python
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

# Create adapter
adapter = NeoAdapter()

# Read a recording
recording = adapter.read_recording("/path/to/data.abf")

# List files in a directory
files = adapter.list_compatible_files("/path/to/directory")
```

### Analysis

#### Input Resistance

```python
from Synaptipy.core.analysis.passive_properties import calculate_rin

# Calculate input resistance from a voltage trace and a known current step
result = calculate_rin(
 voltage_trace=voltage_array, # 1D NumPy array (mV)
 time_vector=time_array, # 1D NumPy array (s)
 current_amplitude=-100.0, # Current step amplitude (pA)
 baseline_window=(0.1, 0.2), # seconds
 response_window=(0.5, 0.6), # seconds
)

# result is a RinResult dataclass
if result.is_valid:
 input_resistance = result.value # Input resistance in MOhm
```

#### Sag Ratio

```python
from Synaptipy.core.analysis.passive_properties import calculate_sag_ratio

# Compute sag ratio from a hyperpolarising current-step trace
result = calculate_sag_ratio(
 voltage_trace=voltage_array, # 1D NumPy array (mV)
 time_vector=time_array, # 1D NumPy array (s)
 baseline_window=(0.0, 0.1), # seconds
 response_peak_window=(0.1, 0.3), # seconds (early sag)
 response_steady_state_window=(0.8, 1.0), # seconds (late plateau)
 peak_smoothing_ms=5.0, # Savitzky-Golay smoothing
 rebound_window_ms=100.0, # post-stimulus window
)

# result is a dict
sag_ratio = result["sag_ratio"] # >1 means Ih sag present
sag_pct = result["sag_percentage"] # 0-100 %
v_peak = result["v_peak"] # mV
v_ss = result["v_ss"] # mV
v_baseline = result["v_baseline"] # mV
rebound = result["rebound_depolarization"] # mV
```

#### Spike Detection

```python
from Synaptipy.core.analysis.single_spike import detect_spikes_threshold

# Detect spikes using threshold crossing
spike_result = detect_spikes_threshold(
 data=voltage_array,
 time=time_array,
 threshold=-20.0, # mV
 refractory_period=0.002, # seconds
)

# spike_result is a SpikeTrainResult dataclass
spike_times = spike_result.spike_times # np.ndarray (seconds)
mean_freq = spike_result.mean_frequency # Hz
```

#### Analysis Registry (Plugin Interface)

```python
import Synaptipy.core.analysis # triggers all @register decorators
from Synaptipy.core.analysis.registry import AnalysisRegistry

# List all registered analyses (built-in + plugins)
names = AnalysisRegistry.list_registered() # list[str]

# List only 'analysis'-type entries
analysis_names = AnalysisRegistry.list_analysis() # list[str]

# Get metadata (ui_params, plots, label, type)
meta = AnalysisRegistry.get_metadata("sag_ratio_analysis")

# Get the callable function
func = AnalysisRegistry.get_function("sag_ratio_analysis")
result = func(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.1)
```

### Batch Processing

#### BatchAnalysisEngine

The batch engine runs any combination of registered analysis functions across
multiple files and collects results into a single Pandas DataFrame.

Pass `max_workers > 1` to enable multi-core parallelism via
`concurrent.futures.ProcessPoolExecutor`.  Worker processes are spawned with
the `"spawn"` start method for Qt/numpy safety.  Call `update_performance_settings()`
at runtime (wired to `SessionManager.preferences_changed`) to change the
worker count without restarting.

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

# Sequential (default)
engine = BatchAnalysisEngine()

# Multi-core: use 4 worker processes
engine = BatchAnalysisEngine(max_workers=4)

# Dynamic update (no restart required)
engine.update_performance_settings({"max_cpu_cores": 8, "max_ram_allocation_gb": 16.0})

# Define a multi-step pipeline
pipeline = [
    {
        'analysis': 'spike_detection',
        'scope': 'all_trials',       # or 'average'
        'params': {'threshold': -20.0, 'refractory_ms': 2.0}
    },
    {
        'analysis': 'excitability_analysis',
        'scope': 'all_trials',
        'params': {'threshold': -20.0}
    },
]

# Run across multiple files (auto-routes to parallel when max_workers > 1)
files = [Path("file1.abf"), Path("file2.abf")]
results_df = engine.run_batch(files, pipeline)

# results_df columns (order):
#   file_name, protocol, channel, channel_units, analysis, scope,
#   trial_index, sampling_rate, <analysis-specific metrics>,
#   batch_timestamp, error, debug_trace

# List available analyses
available = engine.list_available_analyses()  # list[str]

# Get info about a specific analysis
info = engine.get_analysis_info("spike_detection")  # dict

# Cancel a running batch
engine.cancel()
```

**Output conventions:**

| Convention | Behaviour |
|---|---|
| Metadata columns first | `file_name`, `protocol`, `channel`, `channel_units`, `analysis`, `scope`, `trial_index`, `sampling_rate` |
| Private keys (`_` prefix) | Array data hidden from CSV export |
| Human-readable aliases | `cv` becomes `coeff_of_variation`, `fi_slope` becomes `fi_gain_hz_per_pa` |
| Error column | Contains error message if analysis failed for a given file/trial |

#### BatchWorker (QThread)

For GUI applications use `BatchWorker` instead of calling `run_batch()` directly.
It wraps the engine in a `QThread` so the GUI remains 100% responsive.

```python
from Synaptipy.application.gui.analysis_worker import BatchWorker

worker = BatchWorker(engine, files, pipeline, channel_filter=["IN_0"])
worker.progress.connect(lambda cur, tot, msg: progress_bar.setValue(cur))
worker.batch_finished.connect(lambda df: results_table.load(df))
worker.batch_error.connect(lambda err: QMessageBox.critical(None, "Batch Error", err))
worker.start()          # non-blocking — runs in a separate thread
# worker.cancel()       # request early stop
```

#### EpochManager

Manage experimental epoch boundaries (Baseline, Stim, Washout) derived from
hardware TTL pulses or defined manually.

```python
from Synaptipy.core.analysis.epoch_manager import Epoch, EpochManager

em = EpochManager()

# Auto-detect from TTL channel
em.from_ttl(ttl_data, time_vector, ttl_threshold=2.5, pre_stim_s=1.0, post_stim_s=1.0)

# Manual definition
em.add_manual_epoch("Baseline", 0.0, 60.0)
em.add_manual_epoch("Stim",     60.0, 120.0)
em.add_manual_epoch("Washout",  120.0, 300.0)

# Extract per-epoch data slices from a channel
slices = em.get_epoch_slices(channel, trial_index=0)
# slices = {"Baseline": (data_array, time_array), "Stim": ..., "Washout": ...}
```

### Signal Processing

#### compute_psd / multi_harmonic_notch

```python
from Synaptipy.core.signal_processor import compute_psd, multi_harmonic_notch, comb_filter

# Power Spectral Density (Welch's method)
freqs, psd = compute_psd(data, sampling_rate=20000.0)

# Multi-harmonic notch: strip 50 Hz and all harmonics (100, 150, 200 Hz …)
clean = multi_harmonic_notch(data, fundamental_hz=50.0, fs=20000.0, Q=30.0)

# IIR comb filter (equivalent, uses scipy.signal.iircomb internally)
clean = comb_filter(data, freq=50.0, Q=30.0, fs=20000.0)
```

#### UndoStack (Channel.push_undo / Channel.undo)

Non-destructive editing via a lightweight state-history stack.

```python
channel.push_undo("apply lowpass 300 Hz")   # snapshot before change
channel.data_trials = filtered_trials       # mutate

if channel.can_undo:
    channel.undo()                          # restore previous state
```

#### ProcessingPipeline

Chain preprocessing steps (filters, baseline subtraction, artifact blanking)
into a reusable pipeline.

```python
from Synaptipy.core.processing_pipeline import ProcessingPipeline

pipeline = ProcessingPipeline()

# Add a bandpass filter
pipeline.add_step({
    "type": "bandpass",
    "low_cutoff": 1.0,       # Hz
    "high_cutoff": 5000.0,   # Hz
    "order": 4,
})

# Add baseline subtraction
pipeline.add_step({
    "type": "baseline",
    "method": "median",       # "mean", "median", "mode", "detrend", "window"
})

# Add artifact blanking
pipeline.add_step({
    "type": "artifact",
    "onset_time": 0.1,        # seconds
    "duration_ms": 5.0,       # milliseconds
    "method": "linear",       # "hold", "zero", or "linear"
})

# Apply to data
processed_data = pipeline.apply(raw_data, sampling_rate)
```

### Plugin System

#### PluginManager

Discover and load user plugins at runtime.

```python
from Synaptipy.application.plugin_manager import PluginManager

# Load all plugins from both directories
#   1. examples/plugins/  (bundled)
#   2. ~/.synaptipy/plugins/  (user)
PluginManager.load_plugins()

# Reload plugins (unregister old, re-discover and re-register)
PluginManager.reload_plugins()
```

Plugin discovery paths and precedence:
- `examples/plugins/` is scanned first (bundled examples).
- `~/.synaptipy/plugins/` is scanned second (user additions).
- A user file with the same stem name as a bundled file takes precedence.

### Exporters

#### NWB Exporter

```python
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

# Create exporter
exporter = NWBExporter()

# Set metadata
metadata = {
 'session_description': 'Recording session',
 'experimenter': 'Researcher Name',
 'lab': 'Lab Name',
 'institution': 'Institution',
 'experiment_description': 'Experiment details',
 'session_id': 'session123'
}

# Export to NWB format
exporter.export(recording, "/path/to/output.nwb", metadata)
```

## Licensing

Synaptipy is released under the GNU Affero General Public License Version 3 (AGPL-3.0). This has important implications for developers integrating Synaptipy into their projects:

### Integration Considerations

1. **Library Use**: Applications that directly import and use Synaptipy will generally need to be licensed under AGPL-3.0 as well.

2. **Network Services**: If your application uses Synaptipy to provide a service over a network (e.g., a web application for electrophysiology analysis), you must make the complete source code available to users of that service.

3. **Modifications**: Any modifications to Synaptipy code must be released under the same license and made available to users.

### Alternatives for Commercial Integration

If the AGPL-3.0 license is not compatible with your use case, consider:

1. **Process Separation**: Running Synaptipy as a separate process and communicating with it via standard I/O or another interface may allow you to keep your code separate.

2. **Data Format Conversion**: Convert data to/from Synaptipy-compatible formats without directly integrating with the library.

3. **Custom Licensing**: Contact the Synaptipy authors to discuss potential custom licensing arrangements for commercial use.

For the full license text, see the LICENSE file in the root of the Synaptipy repository.
