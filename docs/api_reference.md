# Synaptipy API Reference

This document provides reference information for developers using Synaptipy as a
library. Autodoc-generated class and function signatures are included below each
section alongside usage examples.

## Table of Contents

- [Core Components](#core-components)
  - [Data Model](#data-model)
  - [File Readers](#file-readers)
  - [Analysis Modules](#analysis-modules)
  - [Batch Processing](#batch-processing)
  - [Signal Processing](#signal-processing)
  - [Plugin System](#plugin-system)
  - [Exporters](#exporters)
- [Licensing](#licensing)

---

## Core Components

### Data Model

```{eval-rst}
.. automodule:: Synaptipy.core.data_model
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from Synaptipy.core.data_model import Recording, Channel
from pathlib import Path

recording = Recording(source_file=Path("/path/to/file.abf"))
sampling_rate = recording.sampling_rate
duration = recording.duration
channels = recording.channels
channel = recording.get_channel_by_name("Vm")
```

### File Readers

```{eval-rst}
.. automodule:: Synaptipy.infrastructure.file_readers.neo_adapter
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

adapter = NeoAdapter()
recording = adapter.read_recording("/path/to/data.abf")
files = adapter.list_compatible_files("/path/to/directory")
```

---

### Analysis Modules

Synaptipy organises its 15 built-in analysis routines into five core modules.
Each module corresponds to a tab in the GUI Analyser and is also available as a
composable unit in the batch processing pipeline.

#### Module 1 - Passive Membrane Properties

Baseline (RMP), Input Resistance, Membrane Time Constant (Tau), Sag Ratio,
I-V Curve, and Capacitance.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.passive_properties
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 2 - Single Spike Analysis

Spike Detection and Phase Plane (dV/dt vs V) analysis.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.single_spike
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 3 - Firing Dynamics

Excitability (F-I Curve), Burst Analysis, and Spike Train Dynamics.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.firing_dynamics
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 4 - Synaptic Events

Threshold-based detection, Template Match detection, and Baseline-Peak
detection.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.synaptic_events
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 5 - Evoked Responses (Optogenetics)

TTL-gated optogenetic stimulus synchronisation, latency, response probability,
and jitter.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.evoked_responses
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Analysis Registry

The central decorator-based registry that maps named analysis functions to the
GUI and batch engine.

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.registry
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example - Registry

```python
import Synaptipy.core.analysis  # triggers all @register decorators
from Synaptipy.core.analysis.registry import AnalysisRegistry

names = AnalysisRegistry.list_registered()
meta = AnalysisRegistry.get_metadata("sag_ratio_analysis")
func = AnalysisRegistry.get_function("sag_ratio_analysis")
result = func(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.1)
```

---

### Batch Processing

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.batch_engine
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from Synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
from pathlib import Path

engine = BatchAnalysisEngine(max_workers=4)

pipeline = [
    {
        'analysis': 'spike_detection',
        'scope': 'all_trials',
        'params': {'threshold': -20.0, 'refractory_ms': 2.0}
    },
]

files = [Path("file1.abf"), Path("file2.abf")]
results_df = engine.run_batch(files, pipeline)
```

#### Epoch Manager

```{eval-rst}
.. automodule:: Synaptipy.core.analysis.epoch_manager
   :members:
   :undoc-members: False
   :show-inheritance:
   :no-index:
```

---

### Signal Processing

```{eval-rst}
.. automodule:: Synaptipy.core.signal_processor
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Processing Pipeline

```{eval-rst}
.. automodule:: Synaptipy.core.processing_pipeline
   :members:
   :undoc-members: False
   :show-inheritance:
```

---

### Plugin System

```{eval-rst}
.. automodule:: Synaptipy.application.plugin_manager
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from Synaptipy.application.plugin_manager import PluginManager

PluginManager.load_plugins()
PluginManager.reload_plugins()
```

---

### Exporters

#### NWB Exporter

```{eval-rst}
.. automodule:: Synaptipy.infrastructure.exporters.nwb_exporter
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

exporter = NWBExporter()
metadata = {
    'session_description': 'Recording session',
    'experimenter': 'Researcher Name',
    'lab': 'Lab Name',
    'institution': 'Institution',
    'experiment_description': 'Experiment details',
    'session_id': 'session123'
}
exporter.export(recording, "/path/to/output.nwb", metadata)
```

---

## Licensing

Synaptipy is released under the GNU Affero General Public License Version 3
(AGPL-3.0). See the [LICENSE](https://github.com/anzalks/synaptipy/blob/main/LICENSE)
file for full terms.
