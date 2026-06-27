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
.. automodule:: synaptipy.core.data_model
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from synaptipy.core.data_model import Recording, Channel
from pathlib import Path

recording = Recording(source_file=Path("/path/to/file.abf"))
sampling_rate = recording.sampling_rate
duration = recording.duration
channels = recording.channels
channel = recording.get_channel_by_name("Vm")
```

### File Readers

```{eval-rst}
.. automodule:: synaptipy.infrastructure.file_readers.neo_adapter
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

adapter = NeoAdapter()
recording = adapter.read_recording("/path/to/data.abf")
files = adapter.list_compatible_files("/path/to/directory")
```

---

### Analysis Modules

Synaptipy organises its 17 built-in analysis routines into five core modules.
Each module corresponds to a tab in the GUI Analyser and is also available as a
composable unit in the batch processing pipeline.

#### Module 1 - Passive Membrane Properties

Baseline (RMP), Input Resistance, Membrane Time Constant (Tau), Sag Ratio,
I-V Curve, and Capacitance.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.passive_properties
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 2 - Single Spike Analysis

Spike Detection and Phase Plane (dV/dt vs V) analysis.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.single_spike
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 3 - Firing Dynamics

Excitability (F-I Curve), Burst Analysis, and Spike Train Dynamics.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.firing_dynamics
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 4 - Synaptic Events

Threshold-based detection, Template Match detection, and Baseline-Peak
detection.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.synaptic_events
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 5 - Evoked Responses

Evoked Sync (TTL-gated stimulus correlation, latency, response probability,
and jitter), Paired-Pulse Ratio with residual decay subtraction, and
Stimulus Train short-term plasticity (STP) analysis.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.evoked_responses
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Analysis Registry

The central decorator-based registry that maps named analysis functions to the
GUI and batch engine.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.registry
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example - Registry

```python
import synaptipy.core.analysis  # triggers all @register decorators
from synaptipy.core.analysis.registry import AnalysisRegistry

names = AnalysisRegistry.list_registered()
meta = AnalysisRegistry.get_metadata("sag_ratio_analysis")
func = AnalysisRegistry.get_function("sag_ratio_analysis")
result = func(data, time, sampling_rate, baseline_start=0.0, baseline_end=0.1)
```

---

### Batch Processing

```{eval-rst}
.. automodule:: synaptipy.core.analysis.batch_engine
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine
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
.. automodule:: synaptipy.core.analysis.epoch_manager
   :members:
   :undoc-members: False
   :show-inheritance:
   :no-index:
```

---

### Signal Processing

```{eval-rst}
.. automodule:: synaptipy.core.signal_processor
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Processing Pipeline

```{eval-rst}
.. automodule:: synaptipy.core.processing_pipeline
   :members:
   :undoc-members: False
   :show-inheritance:
```

---

### Plugin System

```{eval-rst}
.. automodule:: synaptipy.application.plugin_manager
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from synaptipy.application.plugin_manager import PluginManager

PluginManager.load_plugins()
PluginManager.reload_plugins()
```

---

### Exporters

#### CSV Exporter

```{eval-rst}
.. automodule:: synaptipy.infrastructure.exporters.csv_exporter
   :members:
   :undoc-members: False
   :show-inheritance:
```

##### Usage Examples

**Wide-format summary CSV (default)**

```python
from pathlib import Path
from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter

exporter = CSVExporter()
exporter.export_analysis_results(results, Path("summary.csv"))
```

**Tidy (long-format) CSV for R / seaborn**

```python
exporter.export_tidy(results, Path("tidy.csv"))
```

**GraphPad Prism grouped-column format**

`export_to_prism_format` writes one column per experimental group, with each
row being an individual observation.  Unequal-N groups are padded with empty
cells so Prism can import the table directly.

```python
# Export input resistance grouped by treatment condition
exporter.export_to_prism_format(
    results,
    Path("out.csv"),          # base path; actual file is out_prism_rin_mohm.csv
    metric="rin_mohm",
    group_by_key="Condition",  # key in each result row that labels the group
)
```

The resulting CSV looks like:

```
Wild Type,Knockout
150.2,98.4
162.7,104.1
145.0,
```

A companion `_provenance.json` is written alongside every exported file.

---

#### NWB Exporter

```{eval-rst}
.. automodule:: synaptipy.infrastructure.exporters.nwb_exporter
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

```python
from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

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
