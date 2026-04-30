# NWB Export Mapping

This page documents how Synaptipy maps electrophysiology data to the
[Neurodata Without Borders (NWB) 2.x](https://nwb.org/) format when
exporting via **File - Export to NWB** or the `NWBExporter` API.

:::{important}
The NWB exporter writes voltage/current traces, electrode metadata, session
information, stimulus waveforms (3-step fallback), NWB 2.x icephys sweep
grouping tables, and embedded analysis results via a `ProcessingModule`.
See [Container Mapping](#container-mapping) and
[Limitations and Future Work](#limitations-and-future-work) for details.
:::

---

## Container Mapping

| Synaptipy Concept | NWB Container | Notes |
|-------------------|---------------|-------|
| Recording session | `NWBFile` | Top-level container with session metadata |
| Amplifier | `Device` | Name, description, manufacturer from dialog |
| Per-channel electrode | `IntracellularElectrode` | One per channel; linked to Device |
| Voltage trace (CC mode) | `CurrentClampSeries` | Selected when channel units are mV or V |
| Current trace (VC mode) | `VoltageClampSeries` | Selected when channel units are pA, nA, or A |
| Unknown clamp mode | `PatchClampSeries` | Fallback when units are unrecognised |
| Animal metadata | `Subject` | Optional; populated from the export dialog |
| Command waveform (raw) | `CurrentClampStimulusSeries` / `VoltageClampStimulusSeries` | Attempt 1: digitized from `channel.current_data_trials` |
| Command waveform (synthetic) | `CurrentClampStimulusSeries` | Attempt 2: reconstructed from ABF epoch metadata; description notes "Synthetic stimulus array reconstructed from protocol metadata." |
| Missing command waveform | *(none)* | Attempt 3: `stimulus=None`; warning appended to response trace description |
| Sweep-level linkage | `IntracellularRecordingsTable` | Response + stimulus series linked per trial |
| Simultaneous recording group | `SimultaneousRecordingsTable` | One row per (electrode, trial) pair |
| Sequential recording group | `SequentialRecordingsTable` | Groups trials by `stimulus_type` (`current_clamp` / `voltage_clamp`) |
| Discrete event arrays | `ProcessingModule` → `DynamicTable` | Spike times / synaptic event times from batch-engine `_raw_arrays`; requires HDMF |

---

## Series Class Selection

The exporter inspects the **units** attribute on each channel to determine the
appropriate NWB series class:

| Channel Units | Interpreted Clamp Mode | NWB Series Class |
|---------------|----------------------|------------------|
| `mV`, `millivolt` | Current-clamp (records voltage) | `CurrentClampSeries` |
| `V`, `volt` | Current-clamp | `CurrentClampSeries` |
| `pA`, `picoampere` | Voltage-clamp (records current) | `VoltageClampSeries` |
| `nA`, `nanoampere` | Voltage-clamp | `VoltageClampSeries` |
| `A`, `ampere` | Voltage-clamp | `VoltageClampSeries` |
| Other / unknown | Unknown | `PatchClampSeries` (generic parent) |

---

## SI Unit Conversion

NWB best practices require data in SI base units. Synaptipy and Neo
typically store data in millivolts (mV) or picoamperes (pA). The exporter
converts automatically:

| Original Unit | SI Unit | Conversion Factor | Stored in NWB `conversion` field |
|---------------|---------|-------------------|----------------------------------|
| mV | V (volts) | $\times 10^{-3}$ | `1e-3` |
| V | V | $\times 1$ | `1.0` |
| pA | A (amperes) | $\times 10^{-12}$ | `1e-12` |
| nA | A | $\times 10^{-9}$ | `1e-9` |
| A | A | $\times 1$ | `1.0` |

The `conversion` field is written to the NWB file so that downstream tools
can recover the original units if needed.

---

## Electrode Metadata

Each channel is associated with an `IntracellularElectrode` object. The
following metadata fields are populated from the NWB Export Dialog or from
channel attributes:

| Field | Source | Default |
|-------|--------|---------|
| `description` | Dialog or `channel.electrode_description` | `"Intracellular Electrode"` |
| `location` | Dialog or `channel.electrode_location` | `"Unknown"` |
| `filtering` | Dialog or `channel.electrode_filtering` | `"unknown"` |
| `device` | Linked `Device` object | - |

---

## Session Metadata

The `NWBFile` top-level container is populated from the export dialog:

| NWB Field | Dialog Tab | Required |
|-----------|-----------|----------|
| `session_description` | Session | Yes |
| `identifier` | Session (auto-generated UUID) | Yes |
| `session_start_time` | Session | Yes (timezone-aware) |
| `experimenter` | Session | No |
| `lab` | Session | No |
| `institution` | Session | No |
| `session_id` | Session | No |

If the `session_start_time` is timezone-naive, Synaptipy localises it to
the system timezone (via `tzlocal`) or falls back to UTC.

---

## Subject Metadata

Populated from the **Subject** tab in the export dialog:

| NWB Field | Type | Notes |
|-----------|------|-------|
| `subject_id` | string | Required to create Subject object |
| `species` | string | e.g. `"Mus musculus"` |
| `age` | string | ISO 8601 duration, e.g. `"P90D"` |
| `sex` | string | `"M"`, `"F"`, or `"U"` (default) |
| `genotype` | string | Optional |
| `weight` | string | Optional |
| `description` | string | Optional |

---

## Sweep Organisation

Each trial within a channel is stored as a separate `PatchClampSeries`
(or subclass) with a unique `sweep_number` (`np.uint64`). The naming
convention is:

```
{channel_name}_trial_{index:03d}
```

For example, `Vm_trial_000`, `Vm_trial_001`, etc.

Each trial is also linked via the NWB 2.x icephys hierarchy:

- **`IntracellularRecordingsTable`** - one row per trial; binds the response
  series to its electrode and (when available) its stimulus series.
- **`SimultaneousRecordingsTable`** - one row per (electrode, trial) pair;
  groups simultaneous multi-channel recordings.
- **`SequentialRecordingsTable`** - groups simultaneous recordings by
  `stimulus_type` (`"current_clamp"` or `"voltage_clamp"`).

---

## Limitations and Future Work

1. **Stimulus data** - A 3-step fallback is applied per trial: (1) raw
   digitized command waveform; (2) synthetic step waveform from ABF epoch
   metadata; (3) `stimulus=None` with a warning in the response description.
   Non-ABF formats without command channel support will always fall through to
   Attempt 3.
2. **Embedded scalar analysis** - Scalar results (Rin, tau, etc.) are exported
   to CSV/JSON but not yet embedded in the NWB `ProcessingModule`. Only
   discrete event arrays (spike times, synaptic event times) from the batch
   engine `_raw_arrays` sub-dict are currently written as `DynamicTable` rows.
3. **RepetitionsTable / ExperimentalConditionsTable** - Higher-level NWB icephys
   grouping tables are not yet populated.

---

## Per-Analysis-Module PyNWB Class Mapping

The table below documents which PyNWB classes are used for each of the 15
analysis modules.  The **Trace export** column reflects the class used when
writing raw data.  The **Analysis NWB object** column shows implemented
export (marked **✓**) or the planned container for future embedding.

| # | Analysis Module | Registry Name | Trace Export Class | Analysis NWB Object |
|---|----------------|--------------|-------------------|-----------------------------|
| 1 | Baseline / RMP | `rmp_analysis` | `CurrentClampSeries` | `ProcessingModule` - scalar `TimeSeries` for RMP per sweep (planned) |
| 2 | Input Resistance (Rin) | `rin_analysis` | `CurrentClampSeries` | `ProcessingModule` - scalars delta-V, delta-I, Rin MOhm (planned) |
| 3 | Membrane Time Constant (Tau) | `tau_analysis` | `CurrentClampSeries` | `ProcessingModule` - `TimeSeries` overlay of fit; scalar tau_ms (planned) |
| 4 | Sag Ratio (Ih) | `sag_ratio_analysis` | `CurrentClampSeries` | `ProcessingModule` - scalars V_peak, V_ss, sag_ratio, rebound (planned) |
| 5 | Capacitance (Cm) | `capacitance_analysis` | `CurrentClampSeries` (CC) / `VoltageClampSeries` (VC) | `ProcessingModule` - scalars Cm_pF, Rs_MOhm (planned) |
| 6 | Spike Detection | `spike_detection` | `CurrentClampSeries` | `Units` table - spike_times column (planned) |
| 7 | Single-Spike Features | `single_spike_features` | `CurrentClampSeries` | `Units` table - threshold_mv, amplitude_mv, half_width_ms, fAHP, mAHP (planned) |
| 8 | Paired-Pulse Ratio (PPR) | `ppr_analysis` | `CurrentClampSeries` / `VoltageClampSeries` | `ProcessingModule` - scalars R1, R2, PPR, decay_tau_ms (planned) |
| 9 | Event Detection | `event_detection_threshold` / `event_detection_deconvolution` | `CurrentClampSeries` | **✓** `ProcessingModule` → `DynamicTable` with `time_s` and `amplitude` columns per channel/trial (requires HDMF; populated from batch-engine `_raw_arrays`) |
| 10 | I-V Curve | `iv_curve_analysis` | `CurrentClampSeries` | `ProcessingModule` - arrays delta_V, delta_I; scalar Rin_aggregate, R2 (planned) |
| 11 | Burst Analysis | `burst_analysis` | `CurrentClampSeries` | `ProcessingModule` - burst times, durations, intra-burst frequency (planned) |
| 12 | F-I Curve / Excitability | `excitability_analysis` | `CurrentClampSeries` | `ProcessingModule` - arrays firing_rate, current_step; scalars rheobase, fi_slope (planned) |
| 13 | Phase Plane | `phase_plane_analysis` | `CurrentClampSeries` | `ProcessingModule` - 2-D `TimeSeries` (V vs dV/dt) per sweep (planned) |
| 14 | Spike Train Dynamics | `train_dynamics` | `CurrentClampSeries` | `Units` table plus `ProcessingModule` scalars CV, CV2, LV, adaptation_index (planned) |
| 15 | Optogenetic Synchronisation | `optogenetic_sync` | `CurrentClampSeries` + `VoltageClampSeries` (opto channel) | `ProcessingModule` - scalars latency_ms, jitter_ms, response_probability (planned) |

### Notes on icephys best-practice containers

`IntracellularRecordingsTable`, `SimultaneousRecordingsTable`, and
`SequentialRecordingsTable` are **implemented** and populated for every
exported trial.  The higher-level `RepetitionsTable` and
`ExperimentalConditionsTable` are not yet populated.

The relevant PyNWB classes in use:
- `pynwb.icephys.IntracellularRecordingsTable`
- `pynwb.icephys.SimultaneousRecordingsTable`
- `pynwb.icephys.SequentialRecordingsTable`

Spike times and synaptic event times will be stored in `pynwb.misc.Units`
(planned); currently they are written as HDMF `DynamicTable` rows inside a
`ProcessingModule` named `"analysis"`.

---

## Programmatic Usage

```python
from Synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter

exporter = NWBExporter()
exporter.export(
 recording=my_recording,
 output_path=Path("output.nwb"),
 session_metadata={
 "session_description": "Whole-cell patch-clamp recording",
 "identifier": str(uuid.uuid4()),
 "session_start_time": datetime.now(timezone.utc),
 "experimenter": "J. Smith",
 },
)
```
