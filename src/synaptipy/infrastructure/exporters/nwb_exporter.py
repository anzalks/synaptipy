# src/synaptipy/infrastructure/exporters/nwb_exporter.py
# -*- coding: utf-8 -*-
"""
Exporter for saving Recording data to the NWB:N 2.0 format.
Uses metadata extracted by NeoAdapter and stored in data_model objects.
"""

__author__ = "Anzal K Shahul"
__copyright__ = "Copyright 2024-, Anzal K Shahul"
__maintainer__ = "Anzal K Shahul"
__email__ = "anzalks@ncbs.res.in"

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Ensure pynwb is installed: pip install pynwb
try:  # noqa: C901
    from pynwb import NWBHDF5IO, NWBFile
    from pynwb.icephys import (
        CurrentClampSeries,
        CurrentClampStimulusSeries,
        IntracellularElectrode,
        PatchClampSeries,
        VoltageClampSeries,
        VoltageClampStimulusSeries,
    )

    try:
        from hdmf.common import DynamicTable

        HDMF_AVAILABLE = True
    except ImportError:
        HDMF_AVAILABLE = False

    PYNWB_AVAILABLE = True
except ImportError:
    # Define sentinel classes if pynwb not installed, so rest of file can be parsed.
    # The export() method checks PYNWB_AVAILABLE and raises ExportError before
    # any of these classes would be instantiated.
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning(
        "pynwb library not found. NWB Export functionality will be disabled. " "Install it with: pip install pynwb"
    )
    PYNWB_AVAILABLE = False

    class NWBHDF5IO:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class NWBFile:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class PatchClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class CurrentClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class VoltageClampSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class CurrentClampStimulusSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class VoltageClampStimulusSeries:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")

    class IntracellularElectrode:  # type: ignore[no-redef]
        """Sentinel: pynwb not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("pynwb is required for NWB export. Install with: pip install pynwb")


# Import from our package structure using relative paths
try:
    from ...core.data_model import Channel, Recording
    from ...shared.error_handling import ExportError
except ImportError:
    # Fallback for standalone execution or if package structure isn't fully resolved
    log_fallback = logging.getLogger(__name__)
    log_fallback.warning("Could not perform relative imports for data_model/error_handling. Using placeholders.")

    class Recording:  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass

    class Channel:  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass

    class ExportError(IOError):  # type: ignore[no-redef]
        """Sentinel: package imports not resolved."""

        pass


# Configure logging (use specific logger for this module)
log = logging.getLogger(__name__)


class NWBExporter:
    """Handles exporting Recording domain objects to NWB files."""

    # ------------------------------------------------------------------
    # Stimulus resolution helpers (3-step fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _make_stim_series(
        cmd_data: np.ndarray,
        cmd_units_raw: str,
        stim_name: str,
        description: str,
        ic_electrode: Any,
        rate: float,
        t_start: float,
        trial_idx: int,
        nwbfile: Any,
    ) -> Optional[Any]:
        """Create and register one NWB stimulus series; return it or None on failure.

        Unit conversion follows NWB best practice (SI: volts / amperes).
        Selects ``CurrentClampStimulusSeries`` for current-units commands and
        ``VoltageClampStimulusSeries`` for voltage-units commands.
        """
        units_lower = cmd_units_raw.lower()
        cmd_export = np.asarray(cmd_data, dtype=np.float64)
        if units_lower in ("mv", "millivolt", "millivolts"):
            cmd_export = cmd_export * 1e-3
            stim_unit = "volts"
            StimulusClass = VoltageClampStimulusSeries
        elif units_lower in ("v", "volt", "volts"):
            stim_unit = "volts"
            StimulusClass = VoltageClampStimulusSeries
        elif units_lower in ("na", "nanoampere", "nanoamperes"):
            cmd_export = cmd_export * 1e-9
            stim_unit = "amperes"
            StimulusClass = CurrentClampStimulusSeries
        elif units_lower in ("pa", "picoampere", "picoamperes"):
            cmd_export = cmd_export * 1e-12
            stim_unit = "amperes"
            StimulusClass = CurrentClampStimulusSeries
        else:
            stim_unit = units_lower or "unknown"
            StimulusClass = CurrentClampStimulusSeries  # safe default
        try:
            stim = StimulusClass(
                name=stim_name,
                data=cmd_export,
                unit=stim_unit,
                description=description,
                electrode=ic_electrode,
                rate=float(rate) if rate else 1000.0,
                starting_time=t_start,
                gain=1.0,
                sweep_number=np.uint64(trial_idx),
            )
            nwbfile.add_stimulus(stim)
            return stim
        except Exception as exc:
            log.warning("Could not add stimulus series '%s': %s", stim_name, exc)
            return None

    @staticmethod
    def _build_stim_from_abf_epochs(
        epochs: Any,
        trial_idx: int,
        n_samples: int,
        holding_level: float = 0.0,
        pre_epoch_samples: int = 0,
    ) -> Optional[np.ndarray]:
        """Synthesize a command waveform from ABF EpochSections metadata.

        Epoch types: 1 = step, 2 = linear ramp.
        Returns a float64 array of length *n_samples*, or None when the epoch
        data cannot produce a non-zero waveform.
        """
        try:
            if not isinstance(epochs, (list, np.ndarray)) or len(epochs) == 0 or n_samples <= 0:
                return None
            waveform = np.full(n_samples, float(holding_level), dtype=np.float64)
            cursor = max(0, min(int(pre_epoch_samples), n_samples))
            prev_level = float(holding_level)
            for ep in epochs:
                ep_dict = ep if isinstance(ep, dict) else {}
                ep_type = int(ep_dict.get("nEpochType", 0))
                if ep_type == 0:
                    continue
                level = (
                    float(ep_dict.get("fEpochInitLevel", 0.0)) + float(ep_dict.get("fEpochLevelInc", 0.0)) * trial_idx
                )
                dur = int(ep_dict.get("lEpochInitDuration", 0)) + int(ep_dict.get("lEpochDurationInc", 0)) * trial_idx
                if dur <= 0:
                    continue
                end = min(cursor + dur, n_samples)
                seg_len = end - cursor
                if seg_len <= 0:
                    break
                if ep_type == 2 and seg_len > 1:
                    waveform[cursor:end] = np.linspace(prev_level, level, seg_len, dtype=np.float64)
                else:
                    waveform[cursor:end] = level
                prev_level = level
                cursor = end
                if cursor >= n_samples:
                    break
            return waveform if np.any(waveform != 0.0) else None
        except Exception:
            return None

    @staticmethod
    def _resolve_trial_t_start(channel: Any, trial_idx: int) -> float:
        """Return per-trial start time when available, falling back to channel.t_start."""
        t_starts = getattr(channel, "t_starts", None)
        if isinstance(t_starts, (list, tuple, np.ndarray)) and 0 <= trial_idx < len(t_starts):
            try:
                return float(t_starts[trial_idx])
            except (TypeError, ValueError):
                pass
        return float(getattr(channel, "t_start", 0.0) or 0.0)

    @staticmethod
    def _resolve_stimulus_series(
        channel: Any,
        trial_idx: int,
        recording: Any,
        ic_electrode: Any,
        channel_rate: float,
        n_samples: int,
        nwbfile: Any,
    ) -> "Tuple[Optional[Any], str]":
        """Resolve the stimulus series for one trial using a 3-step fallback.

        Attempt 1 - raw digitized command waveform from
            ``channel.current_data_trials[trial_idx]``.
        Attempt 2 - synthetic step/ramp waveform reconstructed from ABF epoch
            metadata stored in ``recording.metadata["abf_epochs"]``.
        Attempt 3 - ``(None, warning_string)`` noting that no waveform is
            available; the caller should append the warning to the response
            trace description.
        """
        stim_name_base = f"{channel.name}_stim_trial_{trial_idx:03d}"
        t_start = NWBExporter._resolve_trial_t_start(channel, trial_idx)

        # ------ Attempt 1: raw digitized command waveform ------
        raw_trials = getattr(channel, "current_data_trials", None)
        if raw_trials and trial_idx < len(raw_trials):
            cmd_data = raw_trials[trial_idx]
            if cmd_data is not None and np.asarray(cmd_data).size > 0:
                stim = NWBExporter._make_stim_series(
                    cmd_data,
                    (getattr(channel, "current_units", None) or "pA"),
                    stim_name_base,
                    "Raw digitized command waveform from acquisition hardware.",
                    ic_electrode,
                    channel_rate,
                    t_start,
                    trial_idx,
                    nwbfile,
                )
                if stim is not None:
                    return stim, ""

        # ------ Attempt 2: synthetic from ABF epoch metadata ------
        abf_epochs = None
        holding_level = 0.0
        pre_epoch_samples = 0
        if hasattr(recording, "metadata") and isinstance(recording.metadata, dict):
            abf_epochs = recording.metadata.get("abf_epochs")
            holding_level = float(recording.metadata.get("abf_holding_level", 0.0) or 0.0)
            pre_epoch_samples = int(recording.metadata.get("abf_pre_epoch_samples", 0) or 0)
        if abf_epochs is not None:
            synth = NWBExporter._build_stim_from_abf_epochs(
                abf_epochs,
                trial_idx,
                n_samples,
                holding_level=holding_level,
                pre_epoch_samples=pre_epoch_samples,
            )
            if synth is not None:
                resp_units = str(getattr(channel, "units", "") or "").strip().lower()
                synth_units = "mV" if resp_units in ("pa", "picoampere", "picoamperes", "na", "a", "amperes") else "pA"
                stim = NWBExporter._make_stim_series(
                    synth,
                    synth_units,
                    stim_name_base + "_synth",
                    "Synthetic stimulus array reconstructed from protocol metadata.",
                    ic_electrode,
                    channel_rate,
                    t_start,
                    trial_idx,
                    nwbfile,
                )
                if stim is not None:
                    return stim, ""

        # ------ Attempt 3: no stimulus available ------
        warning = "WARNING: No stimulus waveform captured during acquisition; command waveform is unavailable."
        return None, warning

    def export(  # noqa: C901
        self,
        recording: Recording,
        output_path: Path,
        session_metadata: Dict[str, Any],
        analysis_results: Optional[Dict[str, Any]] = None,
        subject_id: Optional[str] = None,
        session_start_time: Optional[datetime] = None,
        device_description: Optional[str] = None,
    ):
        """
        Exports the given Recording object to an NWB file.

        Args:
            recording: The Recording object containing data and metadata.
            output_path: The Path object where the .nwb file will be saved.
            session_metadata: A dictionary containing user-provided or default
                              metadata required for NWBFile creation. Expected keys:
                              'session_description', 'identifier', 'session_start_time',
                              plus optional 'experimenter', 'lab', 'institution', 'session_id',
                              and Subject/Device/Electrode info.
            analysis_results: Optional dict (or list of dicts) produced by
                              ``BatchAnalysisEngine.run_batch``.  When provided,
                              discrete-event arrays stored under the
                              ``_raw_arrays`` key are written into an NWB
                              ``ProcessingModule`` as ``DynamicTable`` objects.
                              No analysis computation is re-run.

        Raises:
            ExportError: If any error occurs during the NWB file creation or writing.
        """
        if not PYNWB_AVAILABLE:
            raise ExportError("pynwb library is not installed. Cannot export to NWB.")

        source_file = getattr(recording, "source_file", None)
        log.debug("Starting NWB export for recording from: %s", getattr(source_file, "name", "Unknown Source"))
        log.debug(f"Output path: {output_path}")

        # --- Validate Recording Object ---
        if not isinstance(recording, Recording):
            raise TypeError("Invalid 'recording' object provided to NWBExporter.")
        if not hasattr(recording, "channels") or not isinstance(recording.channels, dict):
            raise ValueError("Recording object is missing 'channels' dictionary or is not a dictionary.")

        # --- Inject required metadata defaults for DANDI compliance ---
        session_metadata = dict(session_metadata)  # avoid mutating caller's dict
        if subject_id:
            session_metadata["subject_id"] = subject_id
        if session_start_time:
            session_metadata["session_start_time"] = session_start_time
        if device_description:
            session_metadata["device_description"] = device_description

        # Subject ID and Species are required by NWB/DANDI validators.
        if not session_metadata.get("subject_id"):
            raise ValueError("NWB export requires a valid 'subject_id' MINDS metadata field.")
        if not session_metadata.get("species"):
            session_metadata.setdefault("species", "unknown species")
            log.warning("NWB export: 'species' not provided; defaulting to 'unknown species'.")
        if not session_metadata.get("device_name"):
            session_metadata.setdefault("device_name", "Generic Amplifier")
            log.warning("NWB export: 'device_name' not provided; defaulting to 'Generic Amplifier'.")
        if not session_metadata.get("device_description"):
            raise ValueError("NWB export requires a valid 'device_description' MINDS metadata field.")

        # --- Validate Metadata & Prepare NWBFile ---
        required_keys = ["session_description", "identifier", "session_start_time", "subject_id", "device_description"]
        missing_keys = [key for key in required_keys if key not in session_metadata or not session_metadata[key]]
        if missing_keys:
            raise ValueError(f"Missing required NWB MINDS session metadata: {missing_keys}")

        start_time = session_metadata["session_start_time"]
        if not isinstance(start_time, datetime):
            raise ValueError(f"session_start_time must be a datetime object, got {type(start_time)}.")

        # Ensure session_start_time is timezone-aware
        if start_time.tzinfo is None:
            log.warning("NWB session_start_time is timezone naive. Attempting to localize.")
            try:
                import tzlocal

                local_tz = tzlocal.get_localzone()
                start_time = start_time.replace(tzinfo=local_tz)
            except Exception:
                start_time = start_time.replace(tzinfo=timezone.utc)

        # --- Create Subject Object ---
        subject = None
        # Extract subject specific keys (assuming flattened structure from dialog or specific keys)
        subj_id = session_metadata.get("subject_id")
        if subj_id:
            try:
                from pynwb.file import Subject

                subject = Subject(
                    subject_id=subj_id,
                    species=session_metadata.get("species"),
                    sex=session_metadata.get("sex", "U"),  # Default Unknown
                    age=session_metadata.get("age"),
                    description=session_metadata.get("subject_description"),
                    genotype=session_metadata.get("genotype"),
                    weight=session_metadata.get("weight"),
                )
                log.debug(f"Created NWB Subject object for ID: {subj_id}")
            except Exception as e_subj:
                log.error(f"Failed to create Subject object: {e_subj}")
                # Continue without subject if it fails, or raise? Proceeding is safer for user exp.

        # --- Create NWB File Object ---
        try:
            # Construct notes
            notes_list = []
            if session_metadata.get("notes"):
                notes_list.append(session_metadata["notes"])

            # Append technical details to notes
            source_file_name = getattr(recording, "source_file", Path("Unknown")).name
            notes_list.append(f"Original file: {source_file_name}")
            if getattr(recording, "imported_protocol_label", None):
                notes_list.append(f"Imported protocol label: {recording.imported_protocol_label}")

            # Recording temperature for FAIR / Q10 compliance.
            # Precedence: explicit session_metadata > recording attribute > recording.metadata dict.
            rec_temp = (
                session_metadata.get("recording_temperature")
                or getattr(recording, "recording_temperature", None)
                or recording.metadata.get("recording_temperature")
                or 22.0
            )
            try:
                rec_temp = float(rec_temp)
            except (TypeError, ValueError):
                rec_temp = 22.0
            notes_list.append(
                f"Recording temperature: {rec_temp:.1f} degC "
                "(account for Q10 kinetic scaling when comparing across preparations)"
            )

            ljp_mv = session_metadata.get(
                "liquid_junction_potential_mv",
                recording.metadata.get("liquid_junction_potential_mv"),
            )
            if ljp_mv is not None:
                try:
                    notes_list.append(f"Liquid junction potential (mV): {float(ljp_mv):.3f}")
                except (TypeError, ValueError):
                    pass

            if session_metadata.get("filter_params"):
                notes_list.append(f"Digital filter provenance: {session_metadata['filter_params']}")

            notes_combined = "\n".join(notes_list)

            nwbfile = NWBFile(
                session_description=session_metadata["session_description"],
                identifier=session_metadata["identifier"],
                session_start_time=start_time,
                experimenter=session_metadata.get("experimenter"),
                lab=session_metadata.get("lab"),
                institution=session_metadata.get("institution"),
                session_id=session_metadata.get("session_id"),
                notes=notes_combined,
                subject=subject,  # Attach Subject
            )

            # --- Device ---
            # Prefer metadata from dialog, fallback to recording metadata, then defaults
            dev_name = (
                session_metadata.get("device_name") or recording.metadata.get("device_name") or "Generic Amplifier"
            )
            dev_descr = (
                session_metadata.get("device_description")
                or recording.metadata.get("device_description")
                or "Electrophysiology amplifier"
            )
            dev_manu = (
                session_metadata.get("device_manufacturer")
                or recording.metadata.get("device_manufacturer")
                or "Unknown"
            )

            device = nwbfile.create_device(name=dev_name, description=dev_descr, manufacturer=dev_manu)
            log.debug(f"Using device: {device.name}")

            # --- Electrode Defaults ---
            # Defaults from dialog
            elec_desc_def = session_metadata.get("electrode_description_default", "Recording Pipette")
            elec_loc_def = session_metadata.get("electrode_location_default", "Unknown")
            elec_filt_def = session_metadata.get("electrode_filtering_default", "unknown")

            # --- Add Channels ---
            num_channels_processed = 0
            if not recording.channels:
                log.warning("Recording contains no channels to export.")

            for chan_id, channel in recording.channels.items():
                if not isinstance(channel, Channel):
                    continue
                if not getattr(channel, "data_trials", None):
                    continue

                log.debug(f"Processing channel '{channel.name}' (ID: {chan_id})")

                # --- Create/Get IntracellularElectrode ---
                electrode_name = f"electrode_{chan_id}"

                # Check for specific channel overrides (if any in future) -> currently use defaults from dialog
                # unless channel object has specific metadata populated
                ic_desc = getattr(channel, "electrode_description", None) or elec_desc_def
                ic_loc = getattr(channel, "electrode_location", None) or elec_loc_def
                ic_filt = getattr(channel, "electrode_filtering", None) or elec_filt_def

                # Extract electrode resistance and seal from channel metadata
                # These are stored as strings (e.g., "10 MOhm", "5 GOhm") in data_model
                ic_resistance = getattr(channel, "electrode_resistance", None)
                ic_seal = getattr(channel, "electrode_seal", None)

                # Since we iterate, check if electrode exists (though unique per channel usually)
                if electrode_name in nwbfile.icephys_electrodes:
                    ic_electrode = nwbfile.icephys_electrodes[electrode_name]
                else:
                    try:
                        # Build electrode parameters dict
                        electrode_params = {
                            "name": electrode_name,
                            "description": str(ic_desc),
                            "device": device,
                            "location": str(ic_loc),
                            "filtering": str(ic_filt),
                        }

                        # Add optional resistance and seal if available
                        if ic_resistance is not None:
                            electrode_params["resistance"] = str(ic_resistance)
                        if ic_seal is not None:
                            electrode_params["seal"] = str(ic_seal)

                        ic_electrode = nwbfile.create_icephys_electrode(**electrode_params)
                    except Exception as e_elec:
                        log.error(f"Failed to create electrode '{electrode_name}': {e_elec}")
                        continue

                # --- Create PatchClampSeries ---
                for trial_idx, trial_data in enumerate(channel.data_trials):
                    if trial_data.size == 0:
                        continue

                    ts_name = f"{channel.name}_trial_{trial_idx:03d}"
                    ts_desc = f"Raw data for channel '{channel.name}', trial {trial_idx + 1}"

                    # Units & Verification
                    # If units imply voltage -> CurrentClampSeries (measures V)
                    # If units imply current -> VoltageClampSeries (measures I)
                    # For now, generic PatchClampSeries is safer if mode unknown,
                    # BUT PyNWB encourages specific if possible.
                    # NWB: VoltageClampSeries (records Current, units=Amps). CurrentClampSeries (records Voltage,
                    # units=Volts).

                    units = getattr(channel, "units", "unknown").lower()

                    # --- SI unit conversion and series class selection ---
                    # NWB best practice: store data directly in SI base units (volts, amperes)
                    # with conversion=1.0 so that value_SI = data * conversion is exact and
                    # never double-scaled by downstream NWB/DANDI/Neo readers.
                    export_data = trial_data.copy().astype(np.float64)
                    conversion = 1.0

                    # Select the appropriate NWB series class based on
                    # channel units, which indicate the clamp mode:
                    #   voltage units (mV, V) -> CurrentClampSeries
                    #   current units (pA, nA, A) -> VoltageClampSeries
                    SeriesClass = PatchClampSeries  # fallback

                    if units in ("mv", "millivolt", "millivolts"):
                        export_data = export_data * 1e-3  # mV -> V
                        final_units = "volts"
                        SeriesClass = CurrentClampSeries
                    elif units in ("v", "volt", "volts"):
                        final_units = "volts"
                        SeriesClass = CurrentClampSeries
                    elif units in ("uv", "microvolt", "microvolts"):
                        export_data = export_data * 1e-6  # uV -> V
                        final_units = "volts"
                        SeriesClass = CurrentClampSeries
                    elif units in ("pa", "picoampere", "picoamperes"):
                        export_data = export_data * 1e-12  # pA -> A
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    elif units in ("na", "nanoampere", "nanoamperes"):
                        export_data = export_data * 1e-9  # nA -> A
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    elif units in ("ua", "microampere", "microamperes"):
                        export_data = export_data * 1e-6  # uA -> A
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    elif units in ("a", "ampere", "amperes"):
                        final_units = "amperes"
                        SeriesClass = VoltageClampSeries
                    else:
                        final_units = getattr(channel, "units", "unknown")
                        log.warning(
                            "Unrecognised channel units '%s' for '%s'. Using generic PatchClampSeries.",
                            units,
                            channel.name,
                        )

                    channel_rate = getattr(channel, "sampling_rate", recording.sampling_rate)
                    trial_t_start = NWBExporter._resolve_trial_t_start(channel, trial_idx)

                    # --- Stimulus Series (3-step fallback) ---
                    stim_series, stim_note = NWBExporter._resolve_stimulus_series(
                        channel,
                        trial_idx,
                        recording,
                        ic_electrode,
                        float(channel_rate) if channel_rate else 1000.0,
                        int(export_data.size),
                        nwbfile,
                    )
                    if stim_note:
                        ts_desc = ts_desc + " " + stim_note

                    try:
                        series_kwargs = dict(
                            name=ts_name,
                            description=ts_desc,
                            data=export_data,
                            unit=final_units,
                            electrode=ic_electrode,
                            rate=float(channel_rate) if channel_rate else 1000.0,
                            starting_time=trial_t_start,
                            gain=1.0,
                            sweep_number=np.uint64(trial_idx),
                            conversion=conversion,
                        )
                        time_series = SeriesClass(**series_kwargs)
                        nwbfile.add_acquisition(time_series)

                        # --- Relational linking via IntracellularRecordingsTable ---
                        # Links each acquired series to its electrode in the NWB
                        # icephys table.  stimulus=None documents that the command
                        # waveform was not captured (valid per NWB:N 2.0 spec).
                        try:
                            _icr_kwargs: Dict[str, Any] = dict(
                                electrode=ic_electrode,
                                response=time_series,
                                response_start_index=0,
                                response_index_count=int(len(export_data)),
                            )
                            if stim_series is not None:
                                _icr_kwargs["stimulus"] = stim_series
                                _icr_kwargs["stimulus_start_index"] = 0
                                _icr_kwargs["stimulus_index_count"] = int(len(stim_series.data))
                            icr_row = nwbfile.add_intracellular_recording(**_icr_kwargs)

                            # --- NWB 2.x Sweep Grouping ---
                            # Group each (electrode, trial) as a simultaneous recording
                            # then all trials of the same trial_idx across channels
                            # as a sequential recording for FAIR sweep linkage.
                            try:
                                sim_row = nwbfile.add_icephys_simultaneous_recording(recordings=[icr_row])
                                nwbfile.add_icephys_sequential_recording(
                                    simultaneous_recordings=[sim_row],
                                    stimulus_type=(
                                        "current_clamp"
                                        if SeriesClass is CurrentClampSeries
                                        else ("voltage_clamp" if SeriesClass is VoltageClampSeries else "unknown")
                                    ),
                                )
                            except Exception as e_grp:
                                log.debug(
                                    "Sweep grouping failed for '%s' trial %d: %s",
                                    ts_name,
                                    trial_idx,
                                    e_grp,
                                )
                        except Exception as e_icr:
                            log.debug(
                                "Could not add intracellular_recording entry for '%s': %s",
                                ts_name,
                                e_icr,
                            )
                    except Exception as e_ts:
                        log.error(f"Failed to add series '{ts_name}': {e_ts}")
                        continue

                num_channels_processed += 1

            if num_channels_processed == 0:
                log.warning("No valid channels exported.")

            # --- Analysis Embedding (ProcessingModule) ---
            # Ingest pre-computed ``_raw_arrays`` from batch-engine results.
            # No analysis is re-run; only discrete-event arrays are written.
            if analysis_results is not None and HDMF_AVAILABLE:
                rows = analysis_results if isinstance(analysis_results, list) else [analysis_results]
                try:
                    pm = nwbfile.create_processing_module(
                        name="analysis",
                        description="Batch analysis results produced by Synaptipy BatchAnalysisEngine.",
                    )
                    _table_counts: Dict[str, int] = {}
                    for row in rows:
                        raw = row.get("_raw_arrays") if isinstance(row, dict) else None
                        if not isinstance(raw, dict):
                            continue
                        event_times = raw.get("event_times")
                        event_amplitudes = raw.get("event_amplitudes")
                        if event_times is None:
                            continue
                        # Derive a unique table name from channel/analysis metadata
                        chan_label = row.get("channel_name") or row.get("channel") or "ch"
                        analysis_label = row.get("analysis") or row.get("analysis_type") or "events"
                        base_name = f"{chan_label}_{analysis_label}"
                        suffix = _table_counts.get(base_name, 0)
                        _table_counts[base_name] = suffix + 1
                        tbl_name = f"{base_name}_{suffix}" if suffix else base_name

                        times_arr = np.asarray(event_times, dtype=np.float64)
                        dt = DynamicTable(
                            name=tbl_name,
                            description=(f"Discrete events for channel={chan_label}, " f"analysis={analysis_label}."),
                        )
                        dt.add_column(name="time_s", description="Event time in seconds relative to sweep onset.")
                        if event_amplitudes is not None:
                            amps_arr = np.asarray(event_amplitudes, dtype=np.float64)
                            dt.add_column(name="amplitude", description="Event amplitude in channel units.")
                            for t_val, a_val in zip(times_arr, amps_arr):
                                dt.add_row(time_s=float(t_val), amplitude=float(a_val))
                        else:
                            for t_val in times_arr:
                                dt.add_row(time_s=float(t_val))
                        pm.add(dt)
                        log.debug("NWB ProcessingModule: added table '%s' (%d rows)", tbl_name, len(times_arr))

                    scalar_rows: List[Tuple[str, str, str, float]] = []
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        chan_label = str(row.get("channel_name") or row.get("channel") or "ch")
                        analysis_label = str(row.get("analysis") or row.get("analysis_type") or "summary")
                        metrics_map = row.get("metrics") if isinstance(row.get("metrics"), dict) else row
                        for m_key, m_val in metrics_map.items():
                            if str(m_key).startswith("_") or m_key in ("metrics", "parameters"):
                                continue
                            if isinstance(m_val, (int, float, np.integer, np.floating)) and not isinstance(m_val, bool):
                                f_val = float(m_val)
                                if np.isfinite(f_val):
                                    scalar_rows.append((chan_label, analysis_label, str(m_key), f_val))
                    if scalar_rows:
                        summary_dt = DynamicTable(
                            name="scalar_metrics",
                            description="Scalar electrophysiology metrics exported by Synaptipy.",
                        )
                        summary_dt.add_column(name="channel", description="Channel identifier or name.")
                        summary_dt.add_column(name="analysis", description="Analysis identifier.")
                        summary_dt.add_column(name="metric", description="Metric name.")
                        summary_dt.add_column(name="value", description="Numeric metric value.")
                        for ch_s, an_s, mk_s, mv_f in scalar_rows:
                            summary_dt.add_row(channel=ch_s, analysis=an_s, metric=mk_s, value=mv_f)
                        pm.add(summary_dt)
                except Exception as e_pm:
                    log.warning("NWB analysis ProcessingModule failed (non-fatal): %s", e_pm)

            # --- Preprocessing History Export (FAIR Compliance) ---
            # Export any logged preprocessing steps to NWB for reproducibility
            if "processing_history" in recording.metadata and HDMF_AVAILABLE:
                try:
                    history = recording.metadata["processing_history"]
                    if history and isinstance(history, list):
                        # Create preprocessing module if it doesn't exist
                        if "preprocessing" not in nwbfile.processing:
                            preproc_module = nwbfile.create_processing_module(
                                name="preprocessing", description="Signal preprocessing steps applied in Synaptipy"
                            )
                        else:
                            preproc_module = nwbfile.processing["preprocessing"]

                        # ``DynamicTable`` is imported at module level when
                        # HDMF is available.  Importing it locally here would
                        # make it a function-local name and prevent the
                        # analysis-results table above from being created.
                        from hdmf.common import VectorData

                        timestamps = VectorData(
                            name="timestamp",
                            description="ISO timestamp when preprocessing was applied",
                            data=[str(step.get("timestamp", "")) for step in history],
                        )
                        operations = VectorData(
                            name="operation",
                            description="Name of preprocessing operation (e.g., lowpass, baseline_subtract)",
                            data=[str(step.get("operation", "")) for step in history],
                        )
                        parameters = VectorData(
                            name="parameters",
                            description="JSON-encoded parameters for the operation",
                            data=[str(step.get("parameters", {})) for step in history],
                        )

                        preproc_table = DynamicTable(
                            name="preprocessing_steps",
                            description="Log of all preprocessing operations applied to this recording",
                            columns=[timestamps, operations, parameters],
                        )
                        preproc_module.add(preproc_table)
                        log.debug(f"NWB: Exported {len(history)} preprocessing steps")
                except Exception as e_preproc:
                    log.warning("Failed to export preprocessing history (non-fatal): %s", e_preproc)

            # --- Write File ---
            log.debug(f"Writing NWB to: {output_path}")
            with NWBHDF5IO(str(output_path), "w") as io:
                io.write(nwbfile)

            # --- pynwb post-write validation ---
            # Validate the written file to flag DANDI-compliance issues.
            # Done after the write so that container_source is already set
            # on the nwbfile object (avoids "Cannot change container_source" error).
            try:
                from pynwb import validate as pynwb_validate

                with NWBHDF5IO(str(output_path), "r") as _io_val:
                    _validation_errors = pynwb_validate(io=_io_val)

                if _validation_errors:
                    err_lines = "\n  ".join(str(e) for e in _validation_errors)
                    log.warning(
                        "NWB validation found %d issue(s) — file may not be DANDI-compliant:\n  %s",
                        len(_validation_errors),
                        err_lines,
                    )
                else:
                    log.info("NWB validation passed (0 errors).")
            except ImportError:
                log.debug("pynwb.validate not available; skipping post-write validation.")
            except Exception as exc_val:
                log.warning("NWB validation step raised an unexpected error: %s", exc_val)

            log.info("NWB export complete.")

        except Exception as e:
            log.error(f"NWB Export failed: {e}", exc_info=True)
            raise ExportError(f"Failed to export to NWB: {e}") from e
