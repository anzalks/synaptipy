# Synaptipy API Reference

This document provides reference information for developers using Synaptipy as a
library. Autodoc-generated class and function signatures are included below each
section alongside usage examples.

## Table of Contents

- [Core Components](#core-components)
  - [Data Model](#data-model)
  - [Result Dataclasses](#result-dataclasses)
  - [Protocol Mapping and Validation](#protocol-mapping-and-validation)
  - [Trial Quality Control and Time-Aligned Averaging](#trial-quality-control-and-time-aligned-averaging)
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
from pathlib import Path
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

adapter = NeoAdapter()
recording = adapter.read_recording(Path("/path/to/data.abf"))

sampling_rate = recording.sampling_rate
duration = recording.duration

for chan_id, channel in recording.channels.items():
    trial_0_trace = channel.get_data(0)
    trial_0_time = channel.get_relative_time_vector(0)
```

### Result Dataclasses

Typed dataclasses returned by core pure-logic analysis functions in
`synaptipy.core.analysis`.

```{eval-rst}
.. automodule:: synaptipy.core.results
   :members:
   :undoc-members: False
   :show-inheritance:
   :no-index:
```

### Protocol Mapping and Validation

Protocol assignment structures and compatibility checks used to validate whether
a recording or trial segment supplies the stimulus or command context required
by an analysis.

```{eval-rst}
.. automodule:: synaptipy.core.protocols
   :members:
   :undoc-members: False
   :show-inheritance:
```

### Trial Quality Control and Time-Aligned Averaging

Auditable per-trial eligibility checks and physical-time interpolation routines
used when computing trial averages across sweeps.

#### Trial Quality Control

```{eval-rst}
.. automodule:: synaptipy.core.trial_qc
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Time-Aligned Averaging

```{eval-rst}
.. automodule:: synaptipy.core.averaging
   :members:
   :undoc-members: False
   :show-inheritance:
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
from pathlib import Path
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

adapter = NeoAdapter()

# List file extensions supported by the Neo reader layer
supported_exts = set(adapter.get_supported_extensions())
data_dir = Path("/path/to/directory")
compatible_files = sorted(
    p for p in data_dir.iterdir()
    if p.is_file() and p.suffix.lstrip(".").lower() in supported_exts
)

# Inspect multi-protocol containers (returns [] for single-protocol files)
protocols = adapter.get_file_protocols(Path("/path/to/session.nwb"))

# Load a recording (optionally specifying protocol or lazy=True)
recording = adapter.read_recording(Path("/path/to/data.abf"))
```

---

### Analysis Modules

Synaptipy organises its 16 built-in leaf analysis routines across 5 pillar
modules, plus 7 registered preprocessing processors. Each pillar module
corresponds to a tab in the GUI Analyser and exposes its leaf analyses to both
the interactive GUI and the headless batch processing pipeline.

#### Cross-File Averaging Safety

`synaptipy.core.analysis.cross_file_utils.compute_cross_file_average` returns
a `CrossFileAverageResult`: time axis, average, contributor count,
unequal-length indicator, and a `CrossFileCompatibilityReport`. The report
records each included or excluded source, channel ID, original units, canonical
units, and reason. Averaging uses relative acquisition time; it does not infer
stimulus onset or manually placed markers.

#### Analysis Result Contract

All registered analyses execute through `AnalysisRegistry.execute`, which emits
`AnalysisResult` schema version 1. The object separates scalar `metrics`,
`warnings`, `plot_payload`, and `provenance`; batch and tidy export flatten only
metrics while retaining schema/version and provenance columns. Analysis
implementations and third-party plugins may return a flat metrics dictionary
(or the legacy `{"module_used": ..., "metrics": {...}}` mapping), which is
normalised at this single registry boundary.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.contracts
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 1 - Passive Membrane Properties

Six leaf routines: Baseline (`rmp_analysis`), Input Resistance (`rin_analysis`),
Membrane Time Constant (`tau_analysis`), Sag Ratio (`sag_ratio_analysis`),
I-V Curve (`iv_curve_analysis`), and Capacitance (`capacitance_analysis`).

```{eval-rst}
.. automodule:: synaptipy.core.analysis.passive_properties
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 2 - Single Spike Analysis

Two leaf routines: Spike Detection (`spike_detection`) and Phase Plane `dV/dt`
vs `V` analysis (`phase_plane_analysis`).

```{eval-rst}
.. automodule:: synaptipy.core.analysis.single_spike
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 3 - Firing Dynamics

Three leaf routines: Excitability F-I Curve (`excitability_analysis`), Burst
Analysis (`burst_analysis`), and Spike Train Dynamics (`train_dynamics`).

```{eval-rst}
.. automodule:: synaptipy.core.analysis.firing_dynamics
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 4 - Synaptic Events

Two leaf routines: Amplitude-based threshold detection
(`event_detection_threshold`) and Template deconvolution detection
(`event_detection_deconvolution`).

```{eval-rst}
.. automodule:: synaptipy.core.analysis.synaptic_events
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Module 5 - Evoked Responses

Three leaf routines: Evoked Sync TTL-gated stimulus correlation, latency,
response probability, and jitter (`optogenetic_sync`), N-pulse Paired-Pulse
Ratio with iterative cumulative decay subtraction (`paired_pulse_ratio`), and
Stimulus Train short-term plasticity analysis (`stimulus_train_stp`).

```{eval-rst}
.. automodule:: synaptipy.core.analysis.evoked_responses
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Analysis Registry

The central decorator-based registry that maps named analysis and preprocessing
functions to the GUI and batch engine.

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

# List registered leaf analyses (excludes preprocessors) and preprocessors
analysis_names = AnalysisRegistry.list_analysis()
preprocessor_names = AnalysisRegistry.list_preprocessing()

# Inspect parameter and plot metadata
meta = AnalysisRegistry.get_metadata("sag_ratio_analysis")

# Execute through the canonical AnalysisResult (schema v1) boundary
result = AnalysisRegistry.execute(
    "sag_ratio_analysis",
    data,
    time,
    sampling_rate,
    baseline_start=0.0,
    baseline_end=0.1,
)
sag_ratio = result.metrics.get("sag_ratio")
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
from pathlib import Path
from synaptipy.core.analysis.batch_engine import BatchAnalysisEngine

engine = BatchAnalysisEngine(max_workers=4)

pipeline = [
    {
        "analysis": "lowpass_filter",
        "scope": "all_trials",
        "params": {"cutoff_hz": 2000.0, "order": 4, "filter_type": "bessel"},
    },
    {
        "analysis": "spike_detection",
        "scope": "all_trials",
        "params": {"threshold": -20.0, "refractory_period": 0.002},
    },
]

files = [Path("file1.abf"), Path("file2.abf")]
results_df = engine.run_batch(files, pipeline)
```

#### Registered Batch Preprocessors

Seven signal-preprocessing processors registered via
`@AnalysisRegistry.register_processor` (`baseline_subtraction`,
`lowpass_filter`, `highpass_filter`, `bandpass_filter`, `notch_filter`,
`comb_filter`, and `detrend_filter`) so batch and CLI pipelines execute the same
DSP steps as the interactive GUI.

```{eval-rst}
.. automodule:: synaptipy.core.analysis.preprocessing
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Epoch Manager

```{eval-rst}
.. automodule:: synaptipy.core.analysis.epoch_manager
   :members:
   :undoc-members: False
   :show-inheritance:
   :no-index:
```

#### Headless Batch CLI

Command-line interface backing the `synaptipy-batch` entry point (`run` and
`list-analyses` subcommands).

```{eval-rst}
.. automodule:: synaptipy.application.cli.main
   :members:
   :undoc-members: False
   :show-inheritance:
```

##### CLI Usage Example

```bash
synaptipy-batch list-analyses
synaptipy-batch run recording1.abf recording2.abf \
    --pipeline pipeline.json \
    --output batch_results.csv \
    --max-workers 4
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

**Relational per-event CSV (`<stem>_events.csv`)**

When batch result rows include `_raw_arrays` (`event_times` and
`event_amplitudes`), `export_events` writes a companion `<stem>_events.csv`
table with one row per detected event (`File`, `Channel`, `Trial`,
`Event_Index`, `Time_s`, `Amplitude`):

```python
exporter.export_events(results, Path("summary.csv"))
```

**Raw recording sweep CSVs**

`export_recording` writes one `<stem>_chan_<id>_trial_<idx>.csv` file per
channel and sweep into `output_dir`, returning `(success_count, error_count)`:

```python
success_count, error_count = exporter.export_recording(
    recording,
    Path("exported_traces"),
)
```

**GraphPad Prism grouped-column format**

`export_to_prism_format` writes one column per experimental group, with each
row representing an observation. Unequal-N groups are padded with empty cells
for direct import into GraphPad Prism. Set `aggregate_by_file=True` (`False` by
default) to average sweeps belonging to the same source file within each group
into a single biological-replicate mean before export, avoiding sweep-level
pseudoreplication.

```python
# Export input resistance grouped by treatment condition (averaged per cell/file)
exporter.export_to_prism_format(
    results,
    Path("out.csv"),          # base path; actual file is out_prism_rin_mohm.csv
    metric="rin_mohm",
    group_by_key="Condition",  # key in each result row that labels the group
    aggregate_by_file=True,    # False by default; True averages sweeps per file
)
```

The resulting CSV has the structure:

```text
Wild Type,Knockout
150.2,98.4
162.7,104.1
145.0,
```

A companion `<stem>_provenance.json` file is written alongside exported
analysis CSVs (`export_analysis_results`, `export_tidy`, and
`export_to_prism_format`).

---

#### XLSX Exporter

Dependency-free Excel workbook writer for exporting tabular results (`DataFrame`
objects) without requiring external spreadsheet libraries.

```{eval-rst}
.. automodule:: synaptipy.shared.xlsx_exporter
   :members:
   :undoc-members: False
   :show-inheritance:
```

##### Usage Example

```python
from pathlib import Path
from synaptipy.shared.xlsx_exporter import write_dataframe_to_xlsx

write_dataframe_to_xlsx(results_df, Path("batch_results.xlsx"), sheet_name="Results")
```

---

#### NWB Exporter

```{eval-rst}
.. automodule:: synaptipy.infrastructure.exporters.nwb_exporter
   :members:
   :undoc-members: False
   :show-inheritance:
```

#### Usage Example

`NWBExporter.export` enforces five mandatory MINDS/DANDI metadata fields in
`session_metadata` (or via keyword overrides): `session_description`,
`identifier`, `session_start_time` (timezone-aware `datetime`), `subject_id`,
and `device_description`.

```python
from datetime import datetime, timezone
from pathlib import Path
from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

exporter = NWBExporter()
metadata = {
    "session_description": "Whole-cell current-clamp recording in acute slice",
    "identifier": "cell_2026_04_11_001",
    "session_start_time": datetime(2026, 4, 11, 14, 30, 0, tzinfo=timezone.utc),
    "subject_id": "Mouse_01",
    "species": "Mus musculus",
    "device_name": "MultiClamp 700B",
    "device_description": "Axon MultiClamp 700B patch-clamp amplifier",
    "experimenter": "Researcher Name",
    "lab": "Electrophysiology Lab",
    "institution": "Research Institute",
    "session_id": "session_001",
}
exporter.export(recording, Path("/path/to/output.nwb"), metadata)
```

---

## Licensing

Synaptipy is released under the GNU Affero General Public License Version 3
(AGPL-3.0). See the repository `LICENSE` file for full terms.
