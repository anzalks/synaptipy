# -*- coding: utf-8 -*-
"""Regression tests for Audit-55 IO, Exporter, Shared Utility, Plugin, and Tooling fixes."""

from __future__ import annotations

import copy
import importlib.util
import json
import logging
import struct
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import h5py
import neo
import numpy as np
import pandas as pd
import pytest
import quantities as pq

from synaptipy.core.analysis.registry import AnalysisRegistry
from synaptipy.core.data_model import Channel, Recording
from synaptipy.infrastructure.exporters.csv_exporter import CSVExporter, _build_tidy_row
from synaptipy.infrastructure.exporters.nwb_exporter import NWBExporter
from synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter
from synaptipy.infrastructure.neo_patches import apply_winwcp_patch
from synaptipy.shared.logging_config import setup_logging
from synaptipy.shared.plot_exporter import PlotExporter
from synaptipy.shared.xlsx_exporter import _normalise_sheet_name, write_dataframe_to_xlsx

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_plugin_module(rel_path: str, module_name: str):
    """Load an example plugin or script module from *rel_path*."""
    full_path = PROJECT_ROOT / rel_path
    spec = importlib.util.spec_from_file_location(module_name, str(full_path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def isolated_registry():
    """Save and restore AnalysisRegistry state around plugin tests."""
    saved_reg = dict(AnalysisRegistry._registry)
    saved_meta = copy.deepcopy(AnalysisRegistry._metadata)
    saved_orig = copy.deepcopy(AnalysisRegistry._original_metadata)
    yield
    AnalysisRegistry._registry.clear()
    AnalysisRegistry._metadata.clear()
    AnalysisRegistry._original_metadata.clear()
    AnalysisRegistry._registry.update(saved_reg)
    AnalysisRegistry._metadata.update(saved_meta)
    AnalysisRegistry._original_metadata.update(saved_orig)


# ---------------------------------------------------------------------------
# D1: _allen_nwb_rescue h5py 3.x string units & partial/absent Current channel
# ---------------------------------------------------------------------------


class TestAllenNwbRescueD1:
    """Verify NWBv1 h5py rescue handles str/bytes units and partial/missing stimulus channels."""

    def test_string_units_and_voltage_only_nwbv1(self, tmp_path):
        nwb_path = tmp_path / "allen_v1_voltage_only.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            ts = f.create_group("acquisition/timeseries/Sweep_1")
            ds = ts.create_dataset("data", data=np.array([-65.0, -64.0, -63.0], dtype=np.float64))
            ds.attrs["unit"] = "millivolts"  # h5py 3.x str attribute
            st = ts.create_dataset("starting_time", data=0.0)
            st.attrs["rate"] = 10000.0

        adapter = NeoAdapter()
        with patch.object(adapter, "_get_neo_io_class") as mock_get_io:
            mock_io = MagicMock()
            mock_io.return_value.read_block.side_effect = TypeError("Missing NWB version")
            mock_get_io.return_value = mock_io
            rec = adapter.read_recording(nwb_path)

        assert list(rec.channels.keys()) == ["0"]
        ch_v = rec.channels["0"]
        assert ch_v.name == "Voltage"
        assert ch_v.units == "mV"
        np.testing.assert_allclose(ch_v.get_data(0), np.array([-65.0, -64.0, -63.0]))

    def test_partial_current_channel_preserves_non_none_sweeps(self, tmp_path):
        nwb_path = tmp_path / "allen_v1_partial_stim.nwb"
        with h5py.File(str(nwb_path), "w") as f:
            for idx, sw_name in enumerate(("Sweep_1", "Sweep_2", "Sweep_3")):
                ts = f.create_group(f"acquisition/timeseries/{sw_name}")
                ds = ts.create_dataset("data", data=np.array([0.001 * (idx + 1)] * 4, dtype=np.float64))
                ds.attrs["unit"] = "Volts" if idx % 2 == 0 else b"volts"
                st = ts.create_dataset("starting_time", data=0.0)
                st.attrs["rate"] = 10000.0

            # Only Sweep_1 and Sweep_3 have stimulus datasets (Sweep_2 has none)
            for idx, sw_name in ((0, "Sweep_1"), (2, "Sweep_3")):
                stim = f.create_group(f"stimulus/presentation/{sw_name}")
                sds = stim.create_dataset("data", data=np.array([10.0 * (idx + 1)] * 4, dtype=np.float64))
                sds.attrs["unit"] = "picoamperes" if idx == 0 else b"picoampere"
                sst = stim.create_dataset("starting_time", data=0.0)
                sst.attrs["rate"] = 10000.0

        adapter = NeoAdapter()
        with patch.object(adapter, "_get_neo_io_class") as mock_get_io:
            mock_io = MagicMock()
            mock_io.return_value.read_block.side_effect = TypeError("Missing NWB version")
            mock_get_io.return_value = mock_io
            rec = adapter.read_recording(nwb_path)

        assert "0" in rec.channels and "1" in rec.channels
        assert rec.channels["0"].num_trials == 3
        assert rec.channels["1"].num_trials == 2
        assert rec.channels["1"].units == "pA"
        np.testing.assert_allclose(rec.channels["1"].get_data(0), np.array([10.0] * 4))
        np.testing.assert_allclose(rec.channels["1"].get_data(1), np.array([30.0] * 4))


# ---------------------------------------------------------------------------
# D2: Multi-channel 2D AnalogSignal splitting & protocol split-all
# ---------------------------------------------------------------------------


class TestMultiChannel2DSplittingD2:
    """Verify 2D AnalogSignal splitting in eager/lazy modes and protocol split-all fallback."""

    def test_protocol_read_tries_split_all_with_typeerror_fallback(self, tmp_path):
        dummy_file = tmp_path / "nested.nwb"
        dummy_file.touch()
        seen_kwargs = []

        class SplitUnsupportedReader:
            header = {"signal_channels": [{"id": "0", "name": "Vm"}]}

            def __init__(self, filename):
                self.closed = False

            def read(self, lazy=False, **kwargs):
                seen_kwargs.append(dict(kwargs))
                if "signal_group_mode" in kwargs:
                    raise TypeError("unexpected keyword argument 'signal_group_mode'")
                blk = neo.Block(name="ProtoA")
                seg = neo.Segment()
                sig = neo.AnalogSignal(
                    np.array([-70.0, -69.0, -68.0]) * pq.mV,
                    sampling_rate=10000.0 * pq.Hz,
                    t_start=0.0 * pq.s,
                )
                sig.annotate(channel_id="0")
                seg.analogsignals.append(sig)
                blk.segments.append(seg)
                return [blk]

            def close(self):
                self.closed = True

        adapter = NeoAdapter()
        with patch.object(adapter, "_get_neo_io_class", return_value=SplitUnsupportedReader):
            rec = adapter.read_recording(dummy_file, lazy=False, protocol="ProtoA")

        assert seen_kwargs == [{"signal_group_mode": "split-all"}, {}]
        assert "0" in rec.channels
        assert rec.imported_protocol_label == "ProtoA"

    @pytest.mark.parametrize("lazy_mode", [False, True])
    def test_2d_analogsignal_splits_columns_without_interleaving(self, tmp_path, lazy_mode):
        dummy_file = tmp_path / "grouped.wcp"
        dummy_file.touch()

        col0 = np.array([-70.0, -65.0, -60.0, -55.0])
        col1 = np.array([100.0, 200.0, 300.0, 400.0])
        matrix = np.column_stack([col0, col1]) * pq.mV

        class GroupedReader:
            header = {
                "signal_channels": [
                    {"id": "ch0", "name": "Vm_Primary"},
                    {"id": "ch1", "name": "Vm_Secondary"},
                ]
            }

            def __init__(self, filename):
                pass

            def read_block(self, lazy=False, **kwargs):
                blk = neo.Block()
                seg = neo.Segment()
                sig = neo.AnalogSignal(
                    matrix,
                    sampling_rate=10000.0 * pq.Hz,
                    t_start=0.0 * pq.s,
                    name="Stream0",
                )
                sig.array_annotate(
                    channel_ids=np.array(["ch0", "ch1"]),
                    channel_names=np.array(["Vm_Primary", "Vm_Secondary"]),
                )
                seg.analogsignals.append(sig)
                blk.segments.append(seg)
                return blk

        adapter = NeoAdapter()
        with patch.object(adapter, "_get_neo_io_class", return_value=GroupedReader):
            rec = adapter.read_recording(dummy_file, lazy=lazy_mode)

        assert set(rec.channels.keys()) == {"ch0", "ch1"}
        assert rec.channels["ch0"].name == "Vm_Primary"
        assert rec.channels["ch1"].name == "Vm_Secondary"
        np.testing.assert_allclose(rec.channels["ch0"].get_data(0), col0)
        np.testing.assert_allclose(rec.channels["ch1"].get_data(0), col1)


# ---------------------------------------------------------------------------
# D5: Handle leaks, Quantity rescaling, t_starts, and neo_patches.py
# ---------------------------------------------------------------------------


class TestHandlesTimeUnitsAndWcpPatchesD5:
    """Verify reader closing, ms->s Quantity conversion, t_starts, and WCP truncation safety."""

    def test_get_neo_io_class_and_get_file_protocols_close_handles(self, tmp_path):
        f_path = tmp_path / "sample.abf"
        f_path.touch()

        probe_io = MagicMock()
        probe_io.__class__ = neo.io.AxonIO

        adapter = NeoAdapter()
        with patch("neo.io.get_io", return_value=probe_io):
            cls = adapter._get_neo_io_class(f_path)
        assert cls is neo.io.AxonIO
        probe_io.close.assert_called_once()

        proto_reader = MagicMock()
        b1 = neo.Block(name="P1")
        b2 = neo.Block(name="P2")
        proto_reader.read.return_value = [b1, b2]
        mock_io_cls = MagicMock(return_value=proto_reader)
        with patch.object(adapter, "_get_neo_io_class", return_value=mock_io_cls):
            protos = adapter.get_file_protocols(f_path)
        assert protos == ["P1", "P2"]
        proto_reader.close.assert_called_once()

    def test_read_recording_closes_failed_and_eager_readers_and_rescales_ms_t_starts(self, tmp_path):
        f_path = tmp_path / "sweeps.dat"
        f_path.touch()
        created_readers = []

        class MsTimingReader:
            header = {"signal_channels": [{"id": "0", "name": "Vm"}]}

            def __init__(self, filename):
                self.closed = False
                created_readers.append(self)

            def read_block(self, lazy=False, **kwargs):
                blk = neo.Block()
                for idx, t0_ms in enumerate((250.0, 750.0)):
                    seg = neo.Segment(index=idx)
                    sig = neo.AnalogSignal(
                        np.linspace(-70.0, -60.0, 50) * pq.mV,
                        sampling_rate=10000.0 * pq.Hz,
                        t_start=t0_ms * pq.ms,
                    )
                    sig.annotate(channel_id="0")
                    seg.analogsignals.append(sig)
                    blk.segments.append(seg)
                return blk

            def close(self):
                self.closed = True

        adapter = NeoAdapter()
        with patch.object(adapter, "_get_neo_io_class", return_value=MsTimingReader):
            rec_eager = adapter.read_recording(f_path, lazy=False)
            assert created_readers[-1].closed is True
            assert rec_eager.channels["0"].t_start == pytest.approx(0.25)
            assert rec_eager.channels["0"].t_starts == pytest.approx([0.25, 0.75])

            rec_lazy = adapter.read_recording(f_path, lazy=True)
            assert created_readers[-1].closed is False
            assert rec_lazy.duration == pytest.approx(50 / 10000.0)
            assert rec_lazy.channels["0"].t_starts == pytest.approx([0.25, 0.75])
            rec_lazy.source_handle.close()
            assert created_readers[-1].closed is True

    def test_winwcp_patch_handles_equals_in_values_and_truncated_segments(self, tmp_path):
        apply_winwcp_patch()
        sectorsize = 512
        nbd = 1
        nc = 1
        np_samples = (sectorsize * nbd) // 2 // nc

        header_lines = [
            "VER=9",
            "NC=1",
            "NR=3",  # Claims 3 segments, but only 1 segment is written to disk
            "NBH=2",
            "NBA=2",
            f"NBD={nbd}",
            "ADCMAX=2048",
            f"NP={np_samples}",
            "NZ=0",
            "DT=0.1",
            "AD=3276.8",
            "TX0=Holding=-70mV",  # Contains multiple '=' characters
            "YN0=Vm",
            "YO0=0",
            "YU0=mV",
            "YG0=1",
        ]
        header_bytes = ("\r\n".join(header_lines) + "\r\n").encode("ascii")[:1024].ljust(1024, b"\x00")
        analysis_block = struct.pack(
            "<4sHHHHHHHfHHHHHHHH128f",
            b"RTYP",
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0.1e-3,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            *([1.0] * 128),
        )[:1024].ljust(1024, b"\x00")
        data_block = (b"\x10\x00" * (np_samples * nc)).ljust(sectorsize * nbd, b"\x00")

        wcp_path = tmp_path / "truncated_multi_eq.wcp"
        with open(wcp_path, "wb") as fh:
            fh.write(header_bytes)
            fh.write(analysis_block)
            fh.write(data_block)

        io_reader = neo.io.WinWcpIO(filename=str(wcp_path))
        block = io_reader.read_block(lazy=False)
        assert len(block.segments) == 1
        assert io_reader.header["nb_segment"] == [1]


# ---------------------------------------------------------------------------
# D3, D4, D6-csv: NWBExporter & CSVExporter fixes
# ---------------------------------------------------------------------------


class TestExportersLazyAndSchemaD3D4D6:
    """Verify lazy NWB export, NumPy scalar tidy export, metadata filtering, and CSV nested/provenance fixes."""

    def test_nwb_exporter_exports_untouched_and_partially_viewed_lazy_channels(self, tmp_path):
        pynwb = pytest.importorskip("pynwb")

        rec = Recording(source_file=tmp_path / "lazy_source.abf")
        rec.sampling_rate = 10000.0
        sweeps = [np.linspace(-70.0, -60.0, 20), np.linspace(-68.0, -58.0, 20)]

        # Channel 0: untouched lazy channel (data_trials=[])
        ch0 = Channel("0", "Vm_Untouched", "mV", 10000.0, [], loader=lambda idx: sweeps[idx])
        ch0.metadata["num_trials"] = 2

        # Channel 1: partially viewed lazy channel ([None, ndarray])
        ch1 = Channel("1", "Vm_Partial", "mV", 10000.0, [], loader=lambda idx: sweeps[idx])
        ch1.metadata["num_trials"] = 2
        ch1.data_trials = [None, sweeps[1]]

        rec.channels = {"0": ch0, "1": ch1}
        meta = {
            "session_description": "Lazy NWB export test",
            "identifier": str(uuid.uuid4()),
            "session_start_time": datetime.now(timezone.utc),
            "subject_id": "SUBJ_LAZY",
            "device_description": "Multiclamp 700B",
            "species": "Mus musculus",
            "device_name": "Amp",
        }
        analysis_rows = [
            {
                "channel_name": "Vm_Untouched",
                "analysis_name": "rmp_analysis",
                "trial_index": 0,
                "trial_count": 2,
                "sampling_rate": 10000.0,
                "io_time_s": 0.01,
                "compute_time_s": 0.02,
                "schema_version": 1,
                "rmp_mv": np.float64(-65.2),
            }
        ]

        out_nwb = tmp_path / "nested_nwb" / "lazy_export.nwb"
        NWBExporter().export(rec, out_nwb, meta, analysis_results=analysis_rows)
        assert out_nwb.is_file()

        with pynwb.NWBHDF5IO(str(out_nwb), "r") as io:
            nwbfile = io.read()
            acq_names = set(nwbfile.acquisition.keys())
            assert "Vm_Untouched_trial_000" in acq_names
            assert "Vm_Untouched_trial_001" in acq_names
            assert "Vm_Partial_trial_000" in acq_names
            assert "Vm_Partial_trial_001" in acq_names

            scalar_tbl = nwbfile.processing["analysis"].data_interfaces["scalar_metrics"]
            exported_metrics = list(scalar_tbl["metric"][:])
            assert exported_metrics == ["rmp_mv"]

    def test_csv_exporter_numpy_scalars_schema_v1_metadata_and_nested_mkdir(self, tmp_path):
        row = {
            "file": "cell1.abf",
            "analysis_name": "spike_detection",
            "subject_id": "S1",
            "cell_id": "C1",
            "protocol_family": "current_step",
            "protocol_source": "recorded",
            "io_time_s": np.float64(0.012),
            "compute_time_s": np.float64(0.034),
            "sampling_rate": np.float64(20000.0),
            "trial_index": np.int64(0),
            "trial_count": np.int64(5),
            "schema_version": np.int64(1),
            "plot_payload": {"x": [0.0, 1.0], "y": [-70.0, 20.0]},
            "summary_stats": {"count": np.int64(4), "_internal_cache": [1, 2, 3]},
            "spike_count": np.int64(4),
            "mean_frequency": np.float32(12.5),
            "accepted": np.bool_(True),
        }

        tidy_rows = _build_tidy_row(row, "cell1.abf", "WT", 0, "Vm", "spike_detection", "mV")
        tidy_map = {r["Metric"]: r["Value"] for r in tidy_rows}
        assert set(tidy_map.keys()) == {"spike_count", "mean_frequency", "accepted"}
        assert type(tidy_map["spike_count"]) is int
        assert type(tidy_map["mean_frequency"]) is float
        assert type(tidy_map["accepted"]) is bool

        exporter = CSVExporter()
        wide_out = tmp_path / "deep" / "sub" / "wide.csv"
        assert exporter.export_analysis_results([row], wide_out) is True
        wide_text = wide_out.read_text(encoding="utf-8")
        assert "plot_payload" not in wide_text
        assert "_internal_cache" not in wide_text
        assert "summary_stats.count" in wide_text

        prov = json.loads((wide_out.parent / "wide_provenance.json").read_text(encoding="utf-8"))
        assert prov["analysis_types"] == ["spike_detection"]

        tidy_out = tmp_path / "deep" / "tidy" / "long.csv"
        assert exporter.export_tidy([row], tidy_out) is True
        tidy_df = pd.read_csv(tidy_out)
        assert list(tidy_df["Analysis"].unique()) == ["spike_detection"]


# ---------------------------------------------------------------------------
# D6: Shared Utilities (xlsx_exporter, plot_exporter, logging_config)
# ---------------------------------------------------------------------------


class TestSharedUtilitiesD6:
    """Verify XLSX NA/complex/sheet sanitization, PlotExporter format/mkdir, and logging resilience."""

    def test_xlsx_exporter_na_complex_decimal_nan_sheet_name_and_mkdir(self, tmp_path):
        assert _normalise_sheet_name("'Sheet\x00Name'") == "SheetName"
        assert _normalise_sheet_name("A" * 30 + "'B") == "A" * 30

        df = pd.DataFrame(
            {
                "na_col": [pd.NA],
                "nat_col": [pd.NaT],
                "complex_col": [complex(2.0, 3.0)],
                "dec_nan": [Decimal("NaN")],
                "dec_inf": [Decimal("Infinity")],
                "num_col": [np.float64(42.5)],
            }
        )
        out_xlsx = tmp_path / "nested_xlsx" / "table.xlsx"
        write_dataframe_to_xlsx(df, out_xlsx, sheet_name="'Quoted\x01Sheet'")
        assert out_xlsx.is_file()

        with zipfile.ZipFile(out_xlsx) as zf:
            wb_xml = zf.read("xl/workbook.xml").decode("utf-8")
            ws_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")

        assert 'name="QuotedSheet"' in wb_xml
        assert '<c r="A2"/>' in ws_xml
        assert '<c r="B2"/>' in ws_xml
        assert '<c r="C2" t="inlineStr">' in ws_xml
        assert '<c r="D2"/>' in ws_xml
        assert '<c r="E2" t="inlineStr">' in ws_xml
        assert '<c r="F2"><v>42.5</v></c>' in ws_xml

    def test_plot_exporter_normalizes_format_and_creates_parent_dirs(self, qapp, tmp_path):
        import pyqtgraph as pg

        widget = pg.PlotWidget()
        widget.resize(320, 240)
        widget.plot(np.array([0.0, 1.0]), np.array([-70.0, -60.0]), name="Average")
        try:
            svg_out = tmp_path / "figs" / "vector" / "trace.svg"
            png_out = tmp_path / "figs" / "raster" / "trace.png"
            pdf_out = tmp_path / "figs" / "pdf" / "trace.pdf"

            exporter = PlotExporter(recording=None, plot_canvas_widget=widget)
            assert exporter.export(str(svg_out), ".SVG", 300) is True
            assert exporter.export(str(png_out), ".PNG", 150) is True
            assert exporter.export(str(pdf_out), ".PDF", 150) is True

            svg_text = svg_out.read_text(encoding="utf-8")
            assert "<image" not in svg_text
            sidecar = json.loads((svg_out.with_suffix(".svg.provenance.json")).read_text(encoding="utf-8"))
            assert sidecar["format"] == "svg"
        finally:
            widget.close()

    def test_logging_config_closes_old_handlers_and_survives_unwritable_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        logger = setup_logging(dev_mode=False, log_dir=log_dir, log_filename="first.log")
        old_file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(old_file_handlers) == 2
        assert all(getattr(h, "encoding", "").lower() == "utf-8" for h in old_file_handlers)

        # Re-initializing with an unwritable path (a regular file blocking mkdir) must close old handlers
        # and continue with console logging without raising OSError.
        blocker = tmp_path / "file_not_dir"
        blocker.write_text("locked", encoding="utf-8")
        logger2 = setup_logging(dev_mode=False, log_dir=blocker, log_filename="second.log")
        assert all(h.stream is None or h.stream.closed for h in old_file_handlers)
        assert any(isinstance(h, logging.StreamHandler) for h in logger2.handlers)


# ---------------------------------------------------------------------------
# E1, E2-plugin, E4: Bundled Plugins, Notebook, Offline Help & Scripts
# ---------------------------------------------------------------------------


class TestPluginsNotebookHelpAndToolingE1E2E4:
    """Verify plugin bug fixes, notebook region keys, offline help missing-link guard, and scripts."""

    def test_evoked_responses_multi_pulse_vlines_and_trace_overlays(self, qapp):
        import pyqtgraph as pg

        import synaptipy.core.analysis  # noqa: F401
        from synaptipy.application.gui.analysis_tabs.metadata_driven import MetadataDrivenAnalysisTab
        from synaptipy.core.data_model import Channel, Recording
        from synaptipy.infrastructure.file_readers import NeoAdapter

        fs = 20000.0
        t = np.arange(0.0, 0.6, 1.0 / fs)
        n = t.size
        pulse_times = (0.10, 0.25, 0.40)
        ttl = np.zeros(n, dtype=float)
        for st in pulse_times:
            i0 = int(round(st * fs))
            ttl[i0 : i0 + 40] = 5.0

        sweeps = []
        for sw in range(3):
            v = np.full(n, -65.0, dtype=float)
            for p_idx, st in enumerate(pulse_times):
                mask = t >= (st + 0.003)
                rel = t[mask] - (st + 0.003)
                v[mask] += (8.0 + p_idx * 1.5 + sw * 0.2) * (np.exp(-rel / 0.012) - np.exp(-rel / 0.0015))
            sweeps.append(v)

        opto_fn = AnalysisRegistry.get_function("optogenetic_sync")
        ppr_fn = AnalysisRegistry.get_function("paired_pulse_ratio")
        stp_fn = AnalysisRegistry.get_function("stimulus_train_stp")
        opto_res = opto_fn(np.mean(sweeps, axis=0), t, fs, ttl_data=ttl, response_window_ms=50.0)
        ppr_res = ppr_fn(np.mean(sweeps, axis=0), t, fs, ttl_data=ttl)
        stp_res = stp_fn(np.mean(sweeps, axis=0), t, fs, ttl_data=ttl, n_pulses=3)

        assert len(opto_res["metrics"]["stimulus_onsets"]) == 3
        assert len(opto_res["metrics"]["_window_starts_s"]) == 3
        assert len(opto_res["metrics"]["_window_ends_s"]) == 3
        assert len(ppr_res["metrics"]["_window_starts_s"]) == 2
        assert len(stp_res["metrics"]["_window_starts_s"]) == 3

        rec = Recording(source_file=PROJECT_ROOT / "examples" / "data" / "2023_04_11_0022.abf")
        rec.sampling_rate = fs
        rec.duration = 0.6
        rec.channels = {
            "0": Channel("0", "IN0", "mV", fs, sweeps),
            "1": Channel("1", "FrameTTL", "V", fs, [ttl.copy() for _ in range(3)]),
        }
        tab = MetadataDrivenAnalysisTab("optogenetic_sync", NeoAdapter())
        try:
            tab._analysis_items = [{"path": rec.source_file, "target_type": "Recording"}]
            tab._selected_item_index = 0
            tab._on_item_load_success(rec, seq=tab._item_load_seq)
            idx = tab._secondary_channel_combobox.findData("1")
            if idx >= 0:
                tab._secondary_channel_combobox.setCurrentIndex(idx)
            tab._trigger_analysis()
            qapp.processEvents()

            vlines = [it for it in tab._dynamic_plot_items if isinstance(it, pg.InfiniteLine) and it.angle == 90]
            overlays = [
                it
                for it in tab._dynamic_plot_items
                if isinstance(it, pg.PlotCurveItem) and getattr(it, "_synaptipy_role", None) == "trace_overlay"
            ]
            assert len(vlines) == 3
            assert len(overlays) == 3
        finally:
            tab.close()

    def test_opto_jitter_handles_ragged_sweep_lists_cleanly(self, isolated_registry):
        mod = _load_plugin_module("examples/plugins/opto_jitter.py", "audit55_opto")
        fs = 10000.0
        lengths = [1000, 950, 980]
        v_sweeps = []
        ttl_sweeps = []
        for idx, n_pts in enumerate(lengths):
            v = np.full(n_pts, -70.0)
            ttl = np.zeros(n_pts)
            ttl[100:] = 5.0
            v[150 + idx * 5] = 20.0
            v_sweeps.append(v)
            ttl_sweeps.append(ttl)

        t = np.arange(lengths[0]) / fs
        res = mod.run_opto_jitter_wrapper(
            v_sweeps,
            t,
            fs,
            secondary_data=ttl_sweeps,
            ttl_threshold=2.5,
            search_start=0.001,
            search_end=0.02,
            spike_threshold=-20.0,
        )
        assert "error" not in res
        assert res["metrics"]["N_Sweeps_Detected"] == 3

        short_res = mod.run_opto_jitter_wrapper(
            [np.array([1.0]), np.array([1.0, 2.0])],
            np.array([0.0, 0.0001]),
            fs,
            secondary_data=[np.array([5.0]), np.array([5.0, 5.0])],
        )
        assert "error" in short_res

    def test_synaptic_charge_hides_legacy_pre_window_duration_param(self, isolated_registry):
        _load_plugin_module("examples/plugins/synaptic_charge.py", "audit55_syn_charge")
        meta = AnalysisRegistry.get_metadata("synaptic_charge")
        pre_param = next(p for p in meta["ui_params"] if p["name"] == "pre_window_duration")
        assert pre_param.get("hidden") is True
        assert "visible_when" not in pre_param

    def test_spike_interface_plugin_applies_t0_and_raw_trace_dc_offset(self, isolated_registry):
        mod = _load_plugin_module("examples/plugins/spike_interface_integration.py", "audit55_si")
        fs = 20000.0
        n = 2000
        dc_offset = -65.0
        raw_trace = np.full(n, dc_offset, dtype=np.float64)
        raw_trace[400] = -265.0  # Peak on raw DC-shifted trace
        filt_zero_mean = np.where(np.arange(n) % 2 == 0, 1.0, -1.0).astype(np.float32).reshape(-1, 1)
        filt_zero_mean[400, 0] = -200.0  # Bandpass-filtered trace has 0 baseline and non-zero MAD

        sc_mock = MagicMock()
        spp_mock = MagicMock()
        pd_mock = MagicMock()
        mock_filt_rec = MagicMock()
        mock_filt_rec.get_traces.return_value = filt_zero_mean
        spp_mock.bandpass_filter.return_value = mock_filt_rec
        peaks_dtype = np.dtype([("sample_index", np.int64), ("amplitude", np.float32)])
        peaks = np.array([(400, -200.0)], dtype=peaks_dtype)
        pd_mock.detect_peaks.return_value = peaks

        si_top = MagicMock()
        si_top.core = sc_mock
        si_top.preprocessing = spp_mock
        si_top.sortingcomponents = MagicMock(peak_detection=pd_mock)
        si_mods = {
            "spikeinterface": si_top,
            "spikeinterface.core": sc_mock,
            "spikeinterface.preprocessing": spp_mock,
            "spikeinterface.sortingcomponents": si_top.sortingcomponents,
            "spikeinterface.sortingcomponents.peak_detection": pd_mock,
        }
        t_shifted = np.arange(n) / fs + 2.5  # Non-zero t0 = 2.5 s
        with patch.dict(sys.modules, si_mods):
            res = mod.run_spike_interface_wrapper(raw_trace, t_shifted, fs)

        assert res["_spike_times"] == pytest.approx([2.5 + 400 / fs])
        assert res["_spike_amplitudes"] == pytest.approx([-265.0])
        assert res["_spike_trace_y"] == pytest.approx([-265.0])
        assert res["_spike_filtered_amplitudes"] == pytest.approx([-200.0])

    def test_miniml_plugin_input_validation_and_core_path_reload(self, isolated_registry, tmp_path):
        mod = _load_plugin_module("examples/plugins/miniml_integration.py", "audit55_miniml")
        data = np.zeros(100)
        time = np.arange(100) * 1e-4

        assert "sampling_rate" in mod.run_miniml_detection(data, time, 0.0, model_path="m.h5")["error"]
        assert "mismatch" in mod.run_miniml_detection(data, time[:50], 10000.0, model_path="m.h5")["error"]

        core_a = tmp_path / "miniml_a" / "core"
        core_b = tmp_path / "miniml_b" / "core"
        core_a.mkdir(parents=True)
        core_b.mkdir(parents=True)
        (core_a / "miniML.py").write_text("class MiniTrace:\n    ORIGIN='A'\nclass EventDetection:\n    pass\n")
        (core_b / "miniML.py").write_text("class MiniTrace:\n    ORIGIN='B'\nclass EventDetection:\n    pass\n")

        saved_path = list(sys.path)
        try:
            mt_a, _ = mod._import_miniml(str(core_a))
            assert mt_a.ORIGIN == "A"
            mt_b, _ = mod._import_miniml(str(core_b))
            assert mt_b.ORIGIN == "B"
        finally:
            sys.path[:] = saved_path
            sys.modules.pop("miniML", None)

    def test_notebook_help_browser_and_scripts_integrity(self, qapp, tmp_path):
        # 1. Notebook JSON & interactive_region param keys
        nb = json.loads((PROJECT_ROOT / "examples" / "03_custom_plugin.ipynb").read_text(encoding="utf-8"))
        code_sources = "\n".join("".join(c.get("source", [])) for c in nb["cells"] if c.get("cell_type") == "code")
        assert '"data": ["window_start", "window_end"]' in code_sources
        assert '"data": ["_window_start", "_window_end"]' not in code_sources

        # 2. _LocalHtmlBrowser missing-link guard
        from PySide6 import QtCore, QtWidgets

        from synaptipy.application.gui.help_window import _LocalHtmlBrowser

        html_dir = tmp_path / "html"
        html_dir.mkdir()
        (html_dir / "index.html").write_text("<html><body><h1>Home Doc</h1></body></html>", encoding="utf-8")

        win = QtWidgets.QMainWindow()
        win.statusBar()
        browser = _LocalHtmlBrowser(html_dir, win)
        win.setCentralWidget(browser)
        browser.go_home()
        assert "Home Doc" in browser.toPlainText()

        missing_url = QtCore.QUrl("_modules/synaptipy/core/analysis.html#func")
        browser._navigate(missing_url)
        assert "Home Doc" in browser.toPlainText()
        assert "not included in offline help" in win.statusBar().currentMessage()
        win.close()

        # 3. build_offline_help.py ignores .doctrees/_sources/.buildinfo & stale .doctrees is absent
        assert not (PROJECT_ROOT / "src" / "synaptipy" / "resources" / "docs" / "html" / ".doctrees").exists()
        help_script = _load_plugin_module("scripts/build_offline_help.py", "audit55_build_help")
        src_html = tmp_path / "build_html"
        dest_html = tmp_path / "dest_html"
        (src_html / ".doctrees").mkdir(parents=True)
        (src_html / "_sources").mkdir(parents=True)
        (src_html / "index.html").write_text("<html>ok</html>", encoding="utf-8")
        (src_html / ".buildinfo").write_text("info", encoding="utf-8")
        (src_html / ".doctrees" / "env.pickle").write_bytes(b"bin")
        (src_html / "_sources" / "index.rst.txt").write_text("rst", encoding="utf-8")
        help_script.HTML_BUILD = src_html
        help_script.HTML_DEST_DIR = dest_html
        help_script.DEST_DIR = tmp_path / "dest_docs"
        help_script.QCH_FILE = tmp_path / "missing.qch"
        help_script.QHC_FILE = tmp_path / "missing.qhc"
        help_script.step_copy_artefacts()
        assert (dest_html / "index.html").is_file()
        assert not (dest_html / ".doctrees").exists()
        assert not (dest_html / "_sources").exists()
        assert not (dest_html / ".buildinfo").exists()

        # 4. run_flexible_batch.py & dependabot-auto-merge.yml
        batch_src = (PROJECT_ROOT / "scripts" / "run_flexible_batch.py").read_text(encoding="utf-8")
        assert "import synaptipy.core.analysis" in batch_src
        assert "spike_analysis" not in batch_src
        assert '"refractory_period": 0.002' in batch_src
        assert "refractory_ms" not in batch_src

        dep_yml = (PROJECT_ROOT / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text(encoding="utf-8")
        assert "--delete-branch" in dep_yml
        assert "git push origin --delete" not in dep_yml
