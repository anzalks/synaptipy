# NWB Export Mapping

This page documents how Synaptipy maps electrophysiology data to the
[Neurodata Without Borders (NWB) 2.x](https://nwb.org/) format when
exporting via the Exporter tab or the `NWBExporter` API
(`src/synaptipy/infrastructure/exporters/nwb_exporter.py`).

:::{important}
The NWB exporter writes pre-scaled SI voltage and current traces, electrode and
device metadata, required MINDS/DANDI subject and session records, session
provenance notes (temperature, liquid junction potential, digital filter
parameters), stimulus waveforms (3-step fallback including ABF step and linear
ramp reconstruction), NWB 2.x intracellular sweep grouping tables, and embedded
analysis and preprocessing `DynamicTable` containers under `/processing`.
See [Container Mapping](#container-mapping) and
[Limitations and Future Work](#limitations-and-future-work) for details.
:::

---

## Container Mapping

| Synaptipy Concept | NWB Container | Notes |
|-------------------|---------------|-------|
| Recording session | `NWBFile` | Top-level container with session metadata and provenance `notes` |
| Amplifier | `Device` | Required `device_description` (`ValueError` if missing); `device_name` defaults to `"Generic Amplifier"` |
| Per-channel electrode | `IntracellularElectrode` | One per channel (`electrode_<chan_id>`); linked to `Device` |
| Voltage trace (CC mode) | `CurrentClampSeries` | Selected when channel units are `uV`, `mV`, or `V` |
| Current trace (VC mode) | `VoltageClampSeries` | Selected when channel units are `pA`, `nA`, `uA`, or `A` |
| Unknown clamp mode | `PatchClampSeries` | Fallback when channel units are unrecognised |
| Animal metadata | `Subject` | Required `subject_id` (`ValueError` if missing); `species` defaults to `"unknown species"` |
| Command waveform (raw) | `CurrentClampStimulusSeries` / `VoltageClampStimulusSeries` | Attempt 1: digitized command array from `channel.current_data_trials` |
| Command waveform (synthetic) | `CurrentClampStimulusSeries` / `VoltageClampStimulusSeries` | Attempt 2: step (`nEpochType == 1`) and linear ramp (`nEpochType == 2`) waveforms reconstructed from ABF `EpochSections` metadata |
| Missing command waveform | *(none)* | Attempt 3: `stimulus=None`; warning appended to response series `description` |
| Sweep-level linkage | `IntracellularRecordingsTable` | Response + stimulus series linked per trial |
| Simultaneous recording group | `SimultaneousRecordingsTable` | One row per `(electrode, trial)` pair |
| Sequential recording group | `SequentialRecordingsTable` | Groups trials by `stimulus_type` (`current_clamp`, `voltage_clamp`, or `unknown`) |
| Embedded scalar metrics | `/processing/analysis` (`ProcessingModule` -> `DynamicTable`) | `scalar_metrics` table with columns `channel`, `analysis`, `metric`, `value` |
| Discrete event arrays | `/processing/analysis` (`ProcessingModule` -> `DynamicTable`) | `{channel}_{analysis}` tables (`time_s`, optional `amplitude`) from `_raw_arrays` |
| Preprocessing audit trail | `/processing/preprocessing` (`ProcessingModule` -> `DynamicTable`) | `preprocessing_steps` table (`timestamp`, `operation`, `parameters`) |

---

## Series Class Selection

The exporter inspects the `units` attribute on each `Channel` (case-insensitive)
to determine the appropriate NWB series class:

| Channel Units | Interpreted Clamp Mode | NWB Series Class |
|---------------|----------------------|------------------|
| `uV`, `microvolt`, `microvolts` | Current-clamp (records voltage) | `CurrentClampSeries` |
| `mV`, `millivolt`, `millivolts` | Current-clamp (records voltage) | `CurrentClampSeries` |
| `V`, `volt`, `volts` | Current-clamp | `CurrentClampSeries` |
| `pA`, `picoampere`, `picoamperes` | Voltage-clamp (records current) | `VoltageClampSeries` |
| `nA`, `nanoampere`, `nanoamperes` | Voltage-clamp | `VoltageClampSeries` |
| `uA`, `microampere`, `microamperes` | Voltage-clamp | `VoltageClampSeries` |
| `A`, `ampere`, `amperes` | Voltage-clamp | `VoltageClampSeries` |
| Other / unknown | Unknown | `PatchClampSeries` (generic parent) |

---

## SI Unit Conversion

NWB and DANDI best practices require data arrays to be stored directly in SI
base units (`volts` or `amperes`). `NWBExporter` pre-scales each trial array to
64-bit floating-point SI values prior to writing and sets `conversion=1.0` on
every exported series so that `value_SI = data * conversion` is exact and never
double-scaled by downstream NWB, DANDI, or Neo readers:

| Original Channel Unit | Pre-Scale Multiplier Applied to `data` | Stored NWB `unit` | Stored NWB `conversion` |
|-----------------------|----------------------------------------|-------------------|-------------------------|
| `uV` / `microvolt(s)` | $\times 10^{-6}$ | `"volts"` | `1.0` |
| `mV` / `millivolt(s)` | $\times 10^{-3}$ | `"volts"` | `1.0` |
| `V` / `volt(s)` | $\times 1$ | `"volts"` | `1.0` |
| `pA` / `picoampere(s)` | $\times 10^{-12}$ | `"amperes"` | `1.0` |
| `nA` / `nanoampere(s)` | $\times 10^{-9}$ | `"amperes"` | `1.0` |
| `uA` / `microampere(s)` | $\times 10^{-6}$ | `"amperes"` | `1.0` |
| `A` / `ampere(s)` | $\times 1$ | `"amperes"` | `1.0` |
| Unrecognised | $\times 1$ (unmodified) | Original unit string | `1.0` |

Stimulus waveforms (`_make_stim_series`) apply the same SI pre-scaling (`mV` ->
`1e-3` `"volts"`, `nA` -> `1e-9` `"amperes"`, `pA` -> `1e-12` `"amperes"`).

---

## Electrode Metadata

Each channel is associated with an `IntracellularElectrode` object named
`electrode_{chan_id}`. Fields are populated from channel attributes or fallback
defaults in `session_metadata`:

| Field | Source | Default |
|-------|--------|---------|
| `description` | `channel.electrode_description` or `electrode_description_default` | `"Recording Pipette"` |
| `location` | `channel.electrode_location` or `electrode_location_default` | `"Unknown"` |
| `filtering` | `channel.electrode_filtering` or `electrode_filtering_default` | `"unknown"` |
| `device` | Linked `Device` object | - |
| `resistance` | `channel.electrode_resistance` | Omitted when `None` |
| `seal` | `channel.electrode_seal` | Omitted when `None` |

`resistance` and `seal` are written as strings in the units stored by the
acquisition software (e.g., `"10 MOhm"`, `"5 GOhm"`). These fields are omitted
when the corresponding channel attribute is `None`.

---

## Session, Device, and Provenance Metadata

`NWBExporter.export()` validates five mandatory MINDS/DANDI fields before
creating the `NWBFile`, raising `ValueError` if any is missing or empty:

| Metadata Key | NWB Target | Required | Notes / Fallback |
|--------------|------------|----------|------------------|
| `session_description` | `NWBFile.session_description` | **Yes** (`ValueError` if missing) | Protocol or experiment summary |
| `identifier` | `NWBFile.identifier` | **Yes** (`ValueError` if missing) | Unique session UUID string |
| `session_start_time` | `NWBFile.session_start_time` | **Yes** (`ValueError` if missing) | `datetime`; naive timestamps are localised via `tzlocal` or UTC |
| `subject_id` | `Subject.subject_id` | **Yes** (`ValueError` if missing) | Can also be passed via `subject_id=` keyword argument |
| `device_description` | `Device.description` | **Yes** (`ValueError` if missing) | Can also be passed via `device_description=` keyword argument |
| `device_name` | `Device.name` | No | Defaults to `"Generic Amplifier"` |
| `device_manufacturer` | `Device.manufacturer` | No | Defaults to `"Unknown"` |
| `experimenter` | `NWBFile.experimenter` | No | Optional |
| `lab` | `NWBFile.lab` | No | Optional |
| `institution` | `NWBFile.institution` | No | Optional |
| `session_id` | `NWBFile.session_id` | No | Optional |

### Session `notes` Provenance

`NWBFile.notes` combines any user-supplied `notes` string with structured
acquisition and preprocessing provenance lines:

- `Original file: <source_file_name>`
- `Imported protocol label: <imported_protocol_label>` (when present on `Recording`)
- `Recording temperature: <temp> degC (account for Q10 kinetic scaling when comparing across preparations)` (resolved from `session_metadata["recording_temperature"]`, `recording.recording_temperature`, or `recording.metadata["recording_temperature"]`, defaulting to `22.0` degC)
- `Liquid junction potential (mV): <ljp_mv>` (when `liquid_junction_potential_mv` is present in `session_metadata` or `recording.metadata`)
- `Digital filter provenance: <filter_params>` (when `session_metadata["filter_params"]` is supplied)

---

## Subject Metadata

Populated from `session_metadata` (and the **Subject** tab in the NWB Export
Dialog):

| NWB Field | Metadata Key | Required | Notes |
|-----------|--------------|----------|-------|
| `subject_id` | `subject_id` | **Yes** (`ValueError` if missing) | Unique animal/specimen identifier |
| `species` | `species` | No | Defaults to `"unknown species"` with a warning if omitted; e.g. `"Mus musculus"` |
| `age` | `age` | No | ISO 8601 duration, e.g. `"P90D"` |
| `sex` | `sex` | No | `"M"`, `"F"`, or `"U"` (default `"U"`) |
| `genotype` | `genotype` | No | Optional |
| `weight` | `weight` | No | Optional |
| `description` | `subject_description` | No | Optional |

---

## Sweep Organisation and Stimulus Reconstruction

Each trial within a channel is stored as a separate `PatchClampSeries`
subclass with a unique `sweep_number` (`np.uint64`). Response and stimulus
series follow the naming conventions:

```text
{channel_name}_trial_{index:03d}
{channel_name}_stim_trial_{index:03d}        # raw digitized command
{channel_name}_stim_trial_{index:03d}_synth  # reconstructed from ABF epochs
```

Stimulus resolution uses a 3-step per-trial fallback:

1. **Attempt 1 (raw command)**: Digitized command waveform from
   `channel.current_data_trials[trial_idx]`.
2. **Attempt 2 (ABF epoch synthesis)**: Reconstructs both **step**
   (`nEpochType == 1`) and **linear ramp** (`nEpochType == 2`, via
   `numpy.linspace` from the preceding epoch level to the target level,
   incorporating per-sweep level increments `fEpochLevelInc`, duration
   increments `lEpochDurationInc`, `abf_holding_level`, and
   `abf_pre_epoch_samples`) command waveforms from
   `recording.metadata["abf_epochs"]`. The series description records
   `"Synthetic stimulus array reconstructed from protocol metadata."`
3. **Attempt 3 (unavailable)**: Sets `stimulus=None` and appends
   `"WARNING: No stimulus waveform captured during acquisition; command waveform is unavailable."`
   to the response series description.

Each trial is linked through the NWB 2.x intracellular electrophysiology table
hierarchy:

- **`IntracellularRecordingsTable`** - one row per trial binding the response
  series, electrode, and (when available) stimulus series.
- **`SimultaneousRecordingsTable`** - one row per `(electrode, trial)` pair.
- **`SequentialRecordingsTable`** - groups simultaneous recordings with
  `stimulus_type` (`"current_clamp"`, `"voltage_clamp"`, or `"unknown"`).

---

## Embedded Analysis and Preprocessing Containers (`/processing`)

When HDMF is installed (included with PyNWB), `NWBExporter` writes two
dedicated `ProcessingModule` containers under `nwbfile.processing`:

```text
NWBFile
  processing
    analysis (ProcessingModule - populated when analysis_results is provided)
      scalar_metrics (DynamicTable)
        channel    : string - channel identifier or name
        analysis   : string - registry analysis identifier
        metric     : string - scalar metric key
        value      : float64 - finite numeric metric value
      {channel}_{analysis}[_{n}] (DynamicTable - when _raw_arrays["event_times"] exists)
        time_s     : float64 - discrete event or spike timestamp (s)
        amplitude  : float64 - event amplitude in channel units (optional)
    preprocessing (ProcessingModule - populated when recording.metadata["processing_history"] exists)
      preprocessing_steps (DynamicTable)
        timestamp  : string - ISO 8601 timestamp when the step was applied
        operation  : string - operation name (e.g. "lowpass", "baseline_subtract")
        parameters : string - JSON-encoded parameter dictionary
```

After writing the file to disk, `NWBExporter` runs `pynwb.validate` in read
mode and logs any DANDI-compliance warnings without aborting the export.

---

## Limitations and Future Work

1. **Non-ABF synthetic stimulus reconstruction** - Formats other than ABF that
   lack a digitized command channel fall through to Attempt 3 (`stimulus=None`
   with an explicit warning in the response description).
2. **Continuous fit curves and `Units` table** - `/processing/analysis` embeds
   all finite scalar metrics in `scalar_metrics` and discrete event arrays from
   `_raw_arrays["event_times"]` as `DynamicTable` objects; continuous 10-50 kHz
   fitted overlay curves (such as `_fit_values`) are excluded to avoid file
   bloat, and migration of spike times to the top-level `pynwb.misc.Units`
   table is planned for a future release.
3. **`RepetitionsTable` / `ExperimentalConditionsTable`** - Higher-level NWB
   icephys grouping tables above `SequentialRecordingsTable` are not yet
   populated.

---

## Per-Analysis-Module PyNWB Class Mapping

The table below lists all 16 built-in leaf analysis routines across Synaptipy's
five core pillars, the acquisition series class used for raw trace export, and
the implemented `/processing/analysis` containers written when batch results
are passed via `analysis_results`.

| # | Pillar | Analysis Routine | Registry Name | Trace Export Class | `/processing/analysis` NWB Container |
|---|--------|------------------|---------------|--------------------|--------------------------------------|
| 1 | Intrinsic Properties | Baseline (RMP) | `rmp_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`rmp_mv`, `rmp_std`, `rmp_drift_rate_mv_per_sweep`) |
| 2 | Intrinsic Properties | Input Resistance | `rin_analysis` | `CurrentClampSeries` (CC) / `VoltageClampSeries` (VC) | `scalar_metrics` `DynamicTable` (`rin_mohm`, `rin_peak_mohm`, `rin_steady_state_mohm`, `conductance_us`) |
| 3 | Intrinsic Properties | Tau (Time Constant) | `tau_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`tau_ms` or `tau_fast_ms`/`tau_slow_ms`, `r_squared`, `tau_decay_after_stimulus_ms`) |
| 4 | Intrinsic Properties | Sag Ratio (Ih) | `sag_ratio_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`sag_ratio`, `sag_percentage`, `v_peak`, `v_ss`, `v_baseline`, `rebound_depolarization`) |
| 5 | Intrinsic Properties | I-V Curve | `iv_curve_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`rin_aggregate_mohm`, `iv_intercept`, `iv_r_squared`, `rectification_index`) |
| 6 | Intrinsic Properties | Capacitance | `capacitance_analysis` | `CurrentClampSeries` (CC) / `VoltageClampSeries` (VC) | `scalar_metrics` `DynamicTable` (`capacitance_pf`, `rs_cc_mohm` or `series_resistance_mohm`) |
| 7 | Spike Analysis | Spike Detection | `spike_detection` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`spike_count`, `mean_freq_hz`, 18 AP feature means/SDs) |
| 8 | Spike Analysis | Phase Plane | `phase_plane_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`threshold_v`, `threshold_mean`, `max_dvdt`, `trace_max_dvdt`) |
| 9 | Excitability | Excitability (F-I Curve) | `excitability_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`rheobase_pa`, `fi_slope`, `fi_r_squared`, `fi_p_value`, `max_freq_hz`) |
| 10 | Excitability | Burst Analysis | `burst_analysis` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`burst_count`, `spikes_per_burst_avg`, `burst_duration_avg`, `burst_freq_hz`) |
| 11 | Excitability | Spike Train Dynamics | `train_dynamics` | `CurrentClampSeries` | `scalar_metrics` `DynamicTable` (`mean_isi_s`, `cv`, `cv2`, `lv`, `adaptation_index`, `spike_broadening_index`) |
| 12 | Synaptic Events | Event (Amplitude) | `event_detection_threshold` | `CurrentClampSeries` / `VoltageClampSeries` | `scalar_metrics` `DynamicTable` + `{chan}_event_detection_threshold` event `DynamicTable` (`time_s`, `amplitude`) |
| 13 | Synaptic Events | Event (Template) | `event_detection_deconvolution` | `CurrentClampSeries` / `VoltageClampSeries` | `scalar_metrics` `DynamicTable` + `{chan}_event_detection_deconvolution` event `DynamicTable` (`time_s`, `amplitude`) |
| 14 | Evoked Responses | Evoked Sync | `optogenetic_sync` | `CurrentClampSeries` / `VoltageClampSeries` + stimulus series | `scalar_metrics` `DynamicTable` + `{chan}_optogenetic_sync` event `DynamicTable` (`time_s`) |
| 15 | Evoked Responses | Paired-Pulse Ratio | `paired_pulse_ratio` | `CurrentClampSeries` / `VoltageClampSeries` | `scalar_metrics` `DynamicTable` (`amplitude_raw_pN`, `amplitude_corrected_pN`, `ratio_pN`, `decay_tau_ms_pN`) |
| 16 | Evoked Responses | Stimulus Train (STP) | `stimulus_train_stp` | `CurrentClampSeries` / `VoltageClampSeries` | `scalar_metrics` `DynamicTable` (`r1_amplitude`, `steady_state_ratio`, `R2/R1` ... `Rn/R1`) |

---

## Programmatic Usage

```python
from datetime import datetime, timezone
from pathlib import Path
import uuid

from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

exporter = NWBExporter()
exporter.export(
    recording=my_recording,
    output_path=Path("output.nwb"),
    session_metadata={
        "session_description": "Whole-cell patch-clamp recording in acute slice",
        "identifier": str(uuid.uuid4()),
        "session_start_time": datetime.now(timezone.utc),
        "subject_id": "mouse_001",
        "species": "Mus musculus",
        "device_name": "MultiClamp 700B",
        "device_description": "Axon MultiClamp 700B patch-clamp amplifier",
        "experimenter": "J. Smith",
        "recording_temperature": 23.5,
        "liquid_junction_potential_mv": 14.2,
    },
    analysis_results=batch_rows,  # optional list of dicts from BatchAnalysisEngine
)
```
