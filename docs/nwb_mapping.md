# NWB Export Mapping

This page documents how Synaptipy maps electrophysiology data to the
[Neurodata Without Borders (NWB) 2.x](https://www.nwb.org/) format when
exporting via **File - Export to NWB** or the `NWBExporter` API.

:::{important}
The NWB exporter writes voltage/current traces, electrode metadata, and
session information. **Stimulus waveforms**, the
**IntracellularRecordingsTable**, and **embedded analysis results** are not
yet exported. See [Limitations and Future Work](#limitations-and-future-work)
for details.
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

---

## Limitations and Future Work

1. **Stimulus data** - Stimulus waveforms are not currently exported to
 `nwbfile.stimulus`. This is planned for a future release.
2. **IntracellularRecordingsTable** - NWB 2.x icephys best practices
 recommend using the `IntracellularRecordingsTable` for organising
 sweeps. Synaptipy currently uses per-series `sweep_number` attributes
 instead.
3. **Analysis results** - Computed features (Rin, spike metrics, etc.) are
 exported to CSV/JSON but not embedded in the NWB file. Future versions
 may write these to NWB `ProcessingModule` containers.

---

## Per-Analysis-Module PyNWB Class Mapping

The table below documents which PyNWB classes are used (or will be used in
the planned embedded-analysis export) for each of the 15 analysis modules.
The **Trace export** column reflects the class used when writing raw data
in the current exporter.  The **Planned analysis object** column documents
the target container for embedding computed metrics in future releases.

| # | Analysis Module | Registry Name | Trace Export Class | Planned Analysis NWB Object |
|---|----------------|--------------|-------------------|----------------------------|
| 1 | Baseline / RMP | `rmp_analysis` | `CurrentClampSeries` | `ProcessingModule` ("ecephys") - scalar `TimeSeries` for RMP per sweep |
| 2 | Input Resistance (Rin) | `rin_analysis` | `CurrentClampSeries` | `ProcessingModule` - `NWBDataInterface` storing delta-V, delta-I, Rin (MOhm) |
| 3 | Membrane Time Constant (Tau) | `tau_analysis` | `CurrentClampSeries` | `ProcessingModule` - `TimeSeries` overlay of exponential fit; scalar tau_ms |
| 4 | Sag Ratio (Ih) | `sag_ratio_analysis` | `CurrentClampSeries` | `ProcessingModule` - scalars V_peak, V_ss, sag_ratio, rebound |
| 5 | Capacitance (Cm) | `capacitance_analysis` | `CurrentClampSeries` (CC) / `VoltageClampSeries` (VC) | `ProcessingModule` - scalars Cm_pF, Rs_MOhm via `NWBDataInterface` |
| 6 | Spike Detection | `spike_detection` | `CurrentClampSeries` | `Units` table (`pynwb.misc.Units`) - spike_times column |
| 7 | Single-Spike Features | `single_spike_features` | `CurrentClampSeries` | `Units` table - columns for threshold_mv, amplitude_mv, half_width_ms, fAHP, mAHP |
| 8 | Paired-Pulse Ratio (PPR) | `ppr_analysis` | `CurrentClampSeries` / `VoltageClampSeries` | `ProcessingModule` - scalars R1, R2, PPR, decay_tau_ms |
| 9 | Event Detection | `event_detection_threshold` / `event_detection_deconvolution` | `CurrentClampSeries` | `ProcessingModule` - `TimeSeries` of event times and amplitudes |
| 10 | I-V Curve | `iv_curve_analysis` | `CurrentClampSeries` | `ProcessingModule` - arrays delta_V, delta_I; scalar Rin_aggregate, R2 |
| 11 | Burst Analysis | `burst_analysis` | `CurrentClampSeries` | `ProcessingModule` - burst times, durations, intra-burst frequency |
| 12 | F-I Curve / Excitability | `excitability_analysis` | `CurrentClampSeries` | `ProcessingModule` - arrays firing_rate, current_step; scalars rheobase, fi_slope |
| 13 | Phase Plane | `phase_plane_analysis` | `CurrentClampSeries` | `ProcessingModule` - 2-D `TimeSeries` (V vs dV/dt) for each sweep |
| 14 | Spike Train Dynamics | `train_dynamics` | `CurrentClampSeries` | `Units` table plus `ProcessingModule` scalars CV, CV2, LV, adaptation_index |
| 15 | Optogenetic Synchronisation | `optogenetic_sync` | `CurrentClampSeries` + `VoltageClampSeries` (opto channel) | `ProcessingModule` - scalars latency_ms, jitter_ms, response_probability |

### Notes on icephys best-practice containers

When `IntracellularRecordingsTable` support is added (planned), the above
`ProcessingModule` approach will be complemented by structured sweep-level
tables following the NWB icephys extension hierarchy:

```
NWBFile
 |- intracellular_recordings (IntracellularRecordingsTable)
 |   |- row per sweep: electrode ref, stimulus series, response series
 |- icephys_simultaneous_recordings (SimultaneousRecordingsTable)
 |- icephys_sequential_recordings (SequentialRecordingsTable)
 \- icephys_repetitions (RepetitionsTable)
```

The relevant PyNWB classes are:
- `pynwb.icephys.IntracellularRecordingsTable`
- `pynwb.icephys.SimultaneousRecordingsTable`
- `pynwb.icephys.SequentialRecordingsTable`
- `pynwb.icephys.RepetitionsTable`
- `pynwb.icephys.ExperimentalConditionsTable`

Spike times will be stored in `pynwb.misc.Units` which is the NWB standard
for sorted or unsorted spike times across all clamp modes.

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
