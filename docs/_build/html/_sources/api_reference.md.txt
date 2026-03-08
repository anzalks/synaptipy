# Synaptipy API Reference

This document provides reference information for developers using Synaptipy as a library.

## Table of Contents

- [Core Components](#core-components)
  - [Data Model](#data-model)
  - [File Readers](#file-readers)
  - [Analysis](#analysis)
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
data = channel.data_trials[0]  # Get first trial's data
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
from Synaptipy.core.analysis.intrinsic_properties import calculate_rin

# Calculate input resistance from a voltage trace and a known current step
result = calculate_rin(
    voltage_trace=voltage_array,       # 1D NumPy array (mV)
    time_vector=time_array,            # 1D NumPy array (s)
    current_amplitude=-100.0,          # Current step amplitude (pA)
    baseline_window=(0.1, 0.2),        # seconds
    response_window=(0.5, 0.6),        # seconds
)

# result is a RinResult dataclass
if result.is_valid:
    input_resistance = result.value    # Input resistance in MOhm
```

#### Sag Ratio

```python
from Synaptipy.core.analysis.intrinsic_properties import calculate_sag_ratio

# Compute sag ratio from a hyperpolarising current-step trace
result = calculate_sag_ratio(
    voltage_trace=voltage_array,                  # 1D NumPy array (mV)
    time_vector=time_array,                       # 1D NumPy array (s)
    baseline_window=(0.0, 0.1),                   # seconds
    response_peak_window=(0.1, 0.3),              # seconds (early sag)
    response_steady_state_window=(0.8, 1.0),      # seconds (late plateau)
    peak_smoothing_ms=5.0,                        # Savitzky-Golay smoothing
    rebound_window_ms=100.0,                      # post-stimulus window
)

# result is a dict
sag_ratio    = result["sag_ratio"]              # >1 means Ih sag present
sag_pct      = result["sag_percentage"]         # 0-100 %
v_peak       = result["v_peak"]                 # mV
v_ss         = result["v_ss"]                   # mV
v_baseline   = result["v_baseline"]             # mV
rebound      = result["rebound_depolarization"] # mV
```

#### Spike Detection

```python
from Synaptipy.core.analysis.spike_analysis import detect_spikes_threshold

# Detect spikes using threshold crossing
spike_result = detect_spikes_threshold(
    data=voltage_array,
    time=time_array,
    threshold=-20.0,                   # mV
    refractory_period=0.002,           # seconds
)

# spike_result is a SpikeTrainResult dataclass
spike_times  = spike_result.spike_times      # np.ndarray (seconds)
mean_freq    = spike_result.mean_frequency   # Hz
```

#### Analysis Registry (Plugin Interface)

```python
import Synaptipy.core.analysis            # triggers all @register decorators
from Synaptipy.core.analysis.registry import AnalysisRegistry

# List all registered analyses (built-in + plugins)
names = AnalysisRegistry.list_registered()   # list[str]

# List only 'analysis'-type entries
analysis_names = AnalysisRegistry.list_analysis()  # list[str]

# Get metadata (ui_params, plots, label, type)
meta = AnalysisRegistry.get_metadata("sag_ratio_analysis")

# Get the callable function
func = AnalysisRegistry.get_function("sag_ratio_analysis")
result = func(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.1)
```

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
