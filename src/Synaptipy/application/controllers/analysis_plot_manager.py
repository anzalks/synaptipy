# src/Synaptipy/application/controllers/analysis_plot_manager.py
from typing import Optional, List, Dict, Any, Tuple, Union
import logging
import numpy as np
from dataclasses import dataclass

from Synaptipy.core.data_model import Channel, Recording

log = logging.getLogger(__name__)


@dataclass
class PlotContextTrace:
    time: np.ndarray
    data: np.ndarray
    pen_color: Tuple[int, int, int] = (200, 200, 200)


@dataclass
class PlotDataPackage:
    main_time: np.ndarray
    main_data: np.ndarray
    label: str
    units: str
    sampling_rate: float
    channel_name: str
    context_traces: List[PlotContextTrace]

    # Metadata for the widget state
    channel_id: str
    data_source: Union[int, str]


class AnalysisPlotManager:
    """
    Manages data retrieval and processing for Analysis Tab plotting.
    Decouples the logic of "what to plot" (filtering, averaging, preprocessing)
    from "how to plot" (PyQtGraph calls).
    """

    @staticmethod
    def prepare_plot_data(
        recording: Recording,
        channel_id: str,
        data_source: Union[int, str],  # trial index or "average"
        preprocessing_settings: Optional[Dict] = None,
        filtered_indices: Optional[List[int]] = None,
        process_callback: Optional[Any] = None  # Callback to self._process_signal_data
    ) -> Optional[PlotDataPackage]:
        """
        Prepares all necessary data for plotting.
        """
        if channel_id not in recording.channels:
            log.error(f"Channel {channel_id} not found in recording")
            return None

        channel = recording.channels[channel_id]

        # 1. Handle Context Traces
        context_traces = AnalysisPlotManager._get_context_traces(
            channel, filtered_indices, data_source, preprocessing_settings, process_callback
        )

        # 2. Handle Main Trace
        main_data, main_time, data_label = AnalysisPlotManager._get_main_trace_raw(
            channel, data_source, filtered_indices
        )

        if main_data is None or main_time is None:
            return None

        # 3. Apply Preprocessing
        if preprocessing_settings and process_callback:
            main_data = AnalysisPlotManager._apply_preprocessing(
                main_data, main_time, channel.sampling_rate, preprocessing_settings, process_callback
            )

        return PlotDataPackage(
            main_time=main_time,
            main_data=main_data,
            label=data_label,
            units=channel.units or "?",
            sampling_rate=channel.sampling_rate,
            channel_name=channel.name or f"Ch {channel_id}",
            context_traces=context_traces,
            channel_id=channel_id,
            data_source=data_source
        )

    @staticmethod
    def _get_context_traces(
        channel: Channel,
        filtered_indices: Optional[List[int]],
        data_source: Union[int, str],
        settings: Optional[Dict],
        callback: Optional[Any]
    ) -> List[PlotContextTrace]:
        traces = []
        if not filtered_indices:
            return traces

        for idx in sorted(list(filtered_indices)):
            if isinstance(data_source, int) and idx == data_source:
                continue

            ctx_d = channel.get_data(idx)
            ctx_t = channel.get_relative_time_vector(idx)

            if ctx_d is not None and ctx_t is not None:
                if settings and callback:
                    try:
                        ctx_d = callback(
                            ctx_d,
                            channel.sampling_rate,
                            settings,
                            time_vector=ctx_t
                        )
                    except Exception:
                        pass
                traces.append(PlotContextTrace(ctx_t, ctx_d))
        return traces

    @staticmethod
    def _get_main_trace_raw(
        channel: Channel,
        data_source: Union[int, str],
        filtered_indices: Optional[List[int]]
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], str]:
        if data_source == "average":
            if filtered_indices:
                msg, d, t = AnalysisPlotManager._calculate_dynamic_average(channel, filtered_indices)
                if d is None:
                    log.warning(msg)
                return d, t, msg if d is not None else ""
            else:
                return (
                    channel.get_averaged_data(),
                    channel.get_relative_averaged_time_vector(),
                    "Average (All)"
                )
        elif isinstance(data_source, int):
            return (
                channel.get_data(data_source),
                channel.get_relative_time_vector(data_source),
                f"Trial {data_source + 1}"
            )
        else:
            log.error(f"Invalid data source: {data_source}")
            return None, None, ""

    @staticmethod
    def _apply_preprocessing(
        data: np.ndarray,
        time: np.ndarray,
        rate: float,
        settings: Dict,
        callback: Any
    ) -> np.ndarray:
        try:
            return callback(data, rate, settings, time_vector=time)
        except Exception as e:
            log.error(f"Failed to apply active preprocessing to main trace: {e}")
            return data

    @staticmethod
    def _calculate_dynamic_average(
        channel: Channel, indices: List[int]
    ) -> Tuple[str, Optional[np.ndarray], Optional[np.ndarray]]:
        active_indices = sorted(indices)
        if not active_indices:
            return "Filtered indices empty", None, None

        first_trace = channel.get_data(active_indices[0])
        if first_trace is None:
            return "First trace is None", None, None

        sum_data = np.zeros_like(first_trace, dtype=float)
        count = 0
        skipped = 0

        for idx in active_indices:
            d = channel.get_data(idx)
            if d is not None and d.shape == sum_data.shape:
                sum_data += d
                count += 1
            else:
                skipped += 1

        if count > 0:
            data = sum_data / count
            time = channel.get_relative_time_vector(active_indices[0])
            label = f"Average (Selected {count})"
            return label, data, time

        return "No valid trials for average", None, None
