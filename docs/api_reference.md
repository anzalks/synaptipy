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
