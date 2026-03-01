# NWB Export Mapping

This page documents how Synaptipy maps electrophysiology data to the
[Neurodata Without Borders (NWB) 2.x](https://www.nwb.org/) format when
exporting via **File → Export to NWB** or the `NWBExporter` API.

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

NWB best practices require data in SI base units.  Synaptipy and Neo
typically store data in millivolts (mV) or picoamperes (pA).  The exporter
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

Each channel is associated with an `IntracellularElectrode` object.  The
following metadata fields are populated from the NWB Export Dialog or from
channel attributes:

| Field | Source | Default |
|-------|--------|---------|
| `description` | Dialog or `channel.electrode_description` | `"Intracellular Electrode"` |
| `location` | Dialog or `channel.electrode_location` | `"Unknown"` |
| `filtering` | Dialog or `channel.electrode_filtering` | `"unknown"` |
| `device` | Linked `Device` object | — |

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
(or subclass) with a unique `sweep_number` (`np.uint64`).  The naming
convention is:

```
{channel_name}_trial_{index:03d}
```

For example, `Vm_trial_000`, `Vm_trial_001`, etc.

---

## Limitations and Future Work

1. **Stimulus data** — Stimulus waveforms are not currently exported to
   `nwbfile.stimulus`.  This is planned for a future release.
2. **IntracellularRecordingsTable** — NWB 2.x icephys best practices
   recommend using the `IntracellularRecordingsTable` for organising
   sweeps.  Synaptipy currently uses per-series `sweep_number` attributes
   instead.
3. **Analysis results** — Computed features (Rin, spike metrics, etc.) are
   exported to CSV/JSON but not embedded in the NWB file.  Future versions
   may write these to NWB `ProcessingModule` containers.

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
