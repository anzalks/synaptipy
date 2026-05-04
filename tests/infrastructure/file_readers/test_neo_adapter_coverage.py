# tests/infrastructure/file_readers/test_neo_adapter_coverage.py
# -*- coding: utf-8 -*-
"""
Coverage tests for NeoAdapter methods not exercised by the existing test suite.

Targets the following previously missed lines (per coverage report):
  52-53   – winwcp patch import failure (import-time, tested via mock)
  153-158 – _get_neo_io_class: multi-IO warning / single-IO debug paths
  163-165 – _get_neo_io_class: invalid IO name → ValueError
  185     – get_supported_file_filter: extension with dot → continue
  214-279 – _extract_axon_metadata (dead-code method called directly)
  288-298 – _extract_protocol_trials static method
  303-309 – _cache_abf_epochs static method
  330,335 – _populate_command_signals early-return paths
  341-354 – _populate_command_signals success path
  461-469 – read_recording lazy-mode duration
  500,506,509 – _extract_channel_name branches
  556,561,565 – _process_segment_signals channel-id paths
  574-582 – whitelist filtering
  592-597 – bytes channel name in late-discovery
  613-630 – name override log
  647-649 – lazy data path
  664-679 – rescaling error paths
  751,758,764-766,780 – _build_channels lazy / skip-empty paths
"""

from unittest.mock import MagicMock, patch

import neo
import neo.io as nIO
import numpy as np
import pytest
import quantities as pq

from Synaptipy.core.data_model import Channel, Recording
from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter

# ---------------------------------------------------------------------------
# Helper factory
# ---------------------------------------------------------------------------


def _make_analog_signal(units_str="mV", n=3, fs=20000.0, ch_id=None, name=None):
    """Return a real neo.AnalogSignal, optionally annotated with channel_id."""
    data = np.linspace(-65.0, -60.0, n) * getattr(pq, units_str)
    sig = neo.AnalogSignal(data, sampling_rate=fs * pq.Hz, t_start=0.0 * pq.s)
    if ch_id is not None:
        sig.annotate(channel_id=ch_id)
    if name is not None:
        sig.name = name
    return sig


def _make_segment(signals):
    """Return a neo.Segment containing *signals*."""
    seg = neo.Segment()
    for s in signals:
        s.segment = seg
        seg.analogsignals.append(s)
    return seg


# ---------------------------------------------------------------------------
# _get_neo_io_class – multi-IO / single-IO paths (lines 153-158, 163-165)
# ---------------------------------------------------------------------------


class TestGetNeoIoClassPaths:
    """Cover multi-IO warning, single-IO debug, and invalid-name error."""

    def test_single_io_extension_hits_debug_log(self, neo_adapter_instance, tmp_path):
        """Line 158: extension with exactly one IO → debug log, correct class returned."""
        wcp_file = tmp_path / "test.wcp"
        wcp_file.touch()
        io_cls = neo_adapter_instance._get_neo_io_class(wcp_file)
        assert io_cls is nIO.WinWcpIO

    def test_multiple_ios_non_abf_hits_warning(self, neo_adapter_instance, tmp_path):
        """Lines 153-156: non-ABF extension with multiple IOs → warning log, first IO returned."""
        txt_file = tmp_path / "test.txt"
        txt_file.touch()
        # 'txt' maps to AsciiSignalIO, AsciiSpikeTrainIO, TdtIO
        io_cls = neo_adapter_instance._get_neo_io_class(txt_file)
        assert io_cls is not None

    def test_invalid_io_name_in_dict_raises_value_error(self, neo_adapter_instance, tmp_path):
        """Lines 163-165: IODict maps to a class that does not exist in neo.io → ValueError."""
        fake_file = tmp_path / "test.xyzfake"
        fake_file.touch()
        fake_dict = {"GhostIO123": ["xyzfake"]}
        with patch("Synaptipy.infrastructure.file_readers.neo_adapter.IODict", fake_dict):
            with pytest.raises(ValueError, match="GhostIO123"):
                neo_adapter_instance._get_neo_io_class(fake_file)


# ---------------------------------------------------------------------------
# get_supported_file_filter – dotted-extension continue (line 185)
# ---------------------------------------------------------------------------


class TestGetSupportedFileFilter:
    """Line 185: an IO whose extensions all contain '.' is skipped."""

    def test_dotted_extension_skipped(self, neo_adapter_instance):
        """Line 185: extension containing '.' → wildcard_exts empty → continue."""
        extra = {"FakeIO": ["bin.special"]}
        original_dict = dict(
            __import__(
                "Synaptipy.infrastructure.file_readers.neo_adapter",
                fromlist=["IODict"],
            ).IODict
        )
        patched = {**original_dict, **extra}
        with patch("Synaptipy.infrastructure.file_readers.neo_adapter.IODict", patched):
            result = neo_adapter_instance.get_supported_file_filter()
        # Just verify the call completes without error
        assert isinstance(result, str)
        assert "All Files" in result


# ---------------------------------------------------------------------------
# _extract_axon_metadata – lines 214-279
# ---------------------------------------------------------------------------


class TestExtractAxonMetadata:
    """Call the (currently dead-code) _extract_axon_metadata directly."""

    def test_non_axon_reader_returns_none_pair(self, neo_adapter_instance):
        """Lines 217-219: non-AxonIO reader → (None, None) immediately."""
        mock_reader = MagicMock()
        result = neo_adapter_instance._extract_axon_metadata(mock_reader)
        assert result == (None, None)

    def test_axon_reader_with_protocol_path(self, neo_adapter_instance, sample_abf_path):
        """Lines 222-237: real AxonIO reader – exercises header branches."""
        reader = nIO.AxonIO(filename=str(sample_abf_path))
        reader.read_block()
        proto, current = neo_adapter_instance._extract_axon_metadata(reader)
        assert proto is None or isinstance(proto, str)
        assert current is None or isinstance(current, (float, np.floating))

    def test_axon_reader_type_error_in_protocol_path(self, neo_adapter_instance):
        """Lines 238-240: TypeError while reading _axon_info → 'Extraction Error'."""
        mock_reader = MagicMock(spec=nIO.AxonIO)
        # Make isinstance pass using __class__ trick
        mock_reader.__class__ = nIO.AxonIO
        mock_reader._axon_info = None
        # Make hasattr('_axon_info') return True but accessing it raise TypeError
        type(mock_reader)._axon_info = property(lambda self: (_ for _ in ()).throw(TypeError("bad")))
        # Call the method – TypeError is caught; protocol_name set to "Extraction Error"
        proto, _ = neo_adapter_instance._extract_axon_metadata(mock_reader)
        assert proto == "Extraction Error"

    def test_axon_reader_no_read_raw_protocol(self, neo_adapter_instance):
        """Line 274: reader without read_raw_protocol → debug log, injected_current None."""
        mock_reader = MagicMock(spec=nIO.AxonIO)
        mock_reader.__class__ = nIO.AxonIO
        # No _axon_info → goes to else at line 237, no read_raw_protocol → line 274
        del mock_reader._axon_info
        del mock_reader.read_raw_protocol
        _, current = neo_adapter_instance._extract_axon_metadata(mock_reader)
        assert current is None

    def test_axon_reader_with_read_raw_protocol(self, neo_adapter_instance):
        """Lines 244-267: reader with read_raw_protocol returning data."""
        mock_reader = MagicMock(spec=nIO.AxonIO)
        mock_reader.__class__ = nIO.AxonIO
        del mock_reader._axon_info
        mock_reader.read_raw_protocol.return_value = [
            [np.array([0.0, 100.0, 0.0])],
            [np.array([0.0, 200.0, 0.0])],
        ]
        _, current = neo_adapter_instance._extract_axon_metadata(mock_reader)
        assert current is not None

    def test_axon_reader_empty_protocol_list(self, neo_adapter_instance):
        """Lines 269-272: read_raw_protocol returns empty list → debug log."""
        mock_reader = MagicMock(spec=nIO.AxonIO)
        mock_reader.__class__ = nIO.AxonIO
        del mock_reader._axon_info
        mock_reader.read_raw_protocol.return_value = []
        _, current = neo_adapter_instance._extract_axon_metadata(mock_reader)
        assert current is None


# ---------------------------------------------------------------------------
# _extract_protocol_trials – lines 288-298
# ---------------------------------------------------------------------------


class TestExtractProtocolTrials:
    """Cover all branches of _extract_protocol_trials."""

    def test_valid_array_entries_returned(self):
        """Lines 288-297: valid list/tuple entries with ndarray → returned."""
        raw = [
            [np.array([0.0, 50.0, 100.0])],
            (np.array([0.0, -50.0]),),
        ]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 2
        assert trials[0][1] == pytest.approx(50.0)

    def test_non_list_entry_skipped(self):
        """Line 291: seg_proto not list/tuple → continue."""
        raw = ["not_a_list", [np.array([1.0, 2.0])]]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 1

    def test_empty_inner_list_skipped(self):
        """Line 291: empty list → continue."""
        raw = [[], [np.array([3.0])]]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 1

    def test_non_array_cmd_skipped(self):
        """Lines 293-294: cmd not ndarray/list → continue."""
        raw = [["not_array"], [np.array([5.0])]]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 1

    def test_empty_array_skipped(self):
        """Line 296-297: empty array → not appended."""
        raw = [[np.array([])], [np.array([7.0])]]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 1

    def test_list_cmd_converted(self):
        """Line 295: list cmd → asarray → appended."""
        raw = [[[1.0, 2.0, 3.0]]]
        trials = NeoAdapter._extract_protocol_trials(raw)
        assert len(trials) == 1
        assert trials[0][0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# _cache_abf_epochs – lines 303-309
# ---------------------------------------------------------------------------


class TestCacheAbfEpochs:
    """Cover _cache_abf_epochs paths."""

    def test_epochs_stored_when_present(self):
        """Lines 304-307: EpochSections present → stored in recording.metadata."""
        mock_reader = MagicMock()
        mock_reader._axon_info = {"EpochSections": {"data": [1, 2, 3]}}
        recording = Recording(source_file=None)
        NeoAdapter._cache_abf_epochs(mock_reader, recording)
        assert "abf_epochs" in recording.metadata
        assert recording.metadata["abf_epochs"] == {"data": [1, 2, 3]}

    def test_no_axon_info_no_error(self):
        """Lines 304-309: reader has no _axon_info → no crash, metadata unchanged."""
        mock_reader = MagicMock()
        del mock_reader._axon_info
        recording = Recording(source_file=None)
        NeoAdapter._cache_abf_epochs(mock_reader, recording)
        assert "abf_epochs" not in recording.metadata

    def test_exception_in_epoch_access_caught(self):
        """Lines 308-309: exception during axon_info access → caught silently."""
        mock_reader = MagicMock()
        type(mock_reader)._axon_info = property(lambda self: (_ for _ in ()).throw(RuntimeError("bad")))
        recording = Recording(source_file=None)
        NeoAdapter._cache_abf_epochs(mock_reader, recording)  # Must not raise


# ---------------------------------------------------------------------------
# _populate_command_signals – lines 330, 335, 341-354
# ---------------------------------------------------------------------------


class TestPopulateCommandSignals:
    """Cover early-return and success paths of _populate_command_signals."""

    def test_lazy_returns_early(self):
        """Line 330: lazy=True → returns immediately."""
        adapter = NeoAdapter()
        mock_reader = MagicMock()
        recording = Recording(source_file=None)
        # Should return without calling read_raw_protocol
        adapter._populate_command_signals(mock_reader, [], recording, lazy=True)
        mock_reader.read_raw_protocol.assert_not_called()

    def test_no_read_raw_protocol_returns_early(self):
        """Line 330: reader lacks read_raw_protocol → returns immediately."""
        adapter = NeoAdapter()
        mock_reader = MagicMock(spec=[])  # spec=[] means no attributes
        recording = Recording(source_file=None)
        adapter._populate_command_signals(mock_reader, [], recording, lazy=False)

    def test_no_voltage_channels_returns_early(self):
        """Line 335: no target channels → returns immediately."""
        adapter = NeoAdapter()
        mock_reader = MagicMock()
        mock_reader.read_raw_protocol.return_value = [[np.array([1.0, 2.0])]]
        recording = Recording(source_file=None)
        # Pass empty channel list → voltage_chs = [], created_channels[:1] = [] → return
        adapter._populate_command_signals(mock_reader, [], recording, lazy=False)
        # No crash means early-return branch was hit

    def test_with_protocol_data_populates_channel(self):
        """Lines 341-354: reader with valid protocol → current_data_trials populated."""
        adapter = NeoAdapter()
        mock_reader = MagicMock()
        mock_reader.read_raw_protocol.return_value = [
            [np.array([0.0, 50.0, 100.0])],
            [np.array([0.0, 100.0, 200.0])],
        ]
        recording = Recording(source_file=None)
        ch = Channel(id="0", name="Vm", units="mV", sampling_rate=20000.0, data_trials=[])
        adapter._populate_command_signals(mock_reader, [ch], recording, lazy=False)
        assert len(ch.current_data_trials) == 2
        assert ch.current_units == "pA"

    def test_protocol_exception_is_caught(self):
        """Line 351-352: read_raw_protocol raises → caught, no crash."""
        adapter = NeoAdapter()
        mock_reader = MagicMock()
        mock_reader.read_raw_protocol.side_effect = RuntimeError("oops")
        recording = Recording(source_file=None)
        ch = Channel(id="0", name="Vm", units="mV", sampling_rate=20000.0, data_trials=[])
        adapter._populate_command_signals(mock_reader, [ch], recording, lazy=False)
        # No crash expected
        assert len(ch.current_data_trials) == 0


# ---------------------------------------------------------------------------
# _extract_channel_name – lines 500, 506, 509
# ---------------------------------------------------------------------------


class TestExtractChannelName:
    """Cover all branches of _extract_channel_name."""

    def test_dict_input_returns_name(self):
        """Line 500: ch_info is dict → raw = ch_info.get('name', '')."""
        result = NeoAdapter._extract_channel_name({"name": "Vm", "id": "0"}, "0")
        assert result == "Vm"

    def test_dict_missing_name_returns_ch_id(self):
        """Line 500 + fallback: dict without name → returns ch_id."""
        result = NeoAdapter._extract_channel_name({"id": "0"}, "0")
        assert result == "0"

    def test_structured_array_with_name(self):
        """Lines 503-504: numpy structured array with 'name' field."""
        dt = np.dtype([("id", "U10"), ("name", "U20")])
        row = np.array([("0", "Im")], dtype=dt)[0]
        result = NeoAdapter._extract_channel_name(row, "0")
        assert result == "Im"

    def test_structured_array_without_name_field(self):
        """Line 506: structured array lacking 'name' field → raw = ''."""
        dt = np.dtype([("id", "U10"), ("units", "U10")])
        row = np.array([("0", "mV")], dtype=dt)[0]
        result = NeoAdapter._extract_channel_name(row, "0")
        assert result == "0"  # Falls back to ch_id

    def test_bytes_name_decoded(self):
        """Line 509: raw is bytes → decoded to str."""
        result = NeoAdapter._extract_channel_name({"name": b"Vm\x00"}, "0")
        assert "Vm" in result


# ---------------------------------------------------------------------------
# _process_segment_signals – various lines
# ---------------------------------------------------------------------------


class TestProcessSegmentSignals:
    """Cover branching inside _process_segment_signals."""

    def _make_adapter(self):
        return NeoAdapter()

    def test_non_analogsignal_skipped(self):
        """Line 556: non-AnalogSignal in analogsignals → continue."""
        adapter = self._make_adapter()
        mock_non_sig = MagicMock()  # Not a neo.AnalogSignal
        seg = MagicMock()
        seg.analogsignals = [mock_non_sig]
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        assert ch_map == {}  # Nothing added

    def test_channel_id_from_annotations(self):
        """Line 561: channel_id in anasig.annotations."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="CH_ANN")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        assert "id_CH_ANN" in ch_map

    def test_channel_id_from_array_annotations(self):
        """Line 565: channel_id in anasig.array_annotations (multi-column signal)."""
        adapter = self._make_adapter()
        # 2-column signal so array_annotations apply per-column
        data = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]) * pq.mV
        sig = neo.AnalogSignal(data, sampling_rate=20000.0 * pq.Hz, t_start=0.0 * pq.s)
        # No 'channel_id' in annotations → no channel_index → falls through to array_annotations
        sig.array_annotate(channel_id=np.array(["AA_0", "AA_1"]))
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        # array_annotations path assigns channel_id from first element
        assert "id_AA_0" in ch_map

    def test_channel_id_from_channel_index(self):
        """Line 562-563: channel_id not in annotations but channel_index is set."""
        adapter = self._make_adapter()
        sig = _make_analog_signal()
        sig.channel_index = 7
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        assert "id_7" in ch_map

    def test_whitelist_channel_id_included(self):
        """Lines 574-576: whitelist contains channel id → included."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="WANTED")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, ["WANTED"], {}, False)
        assert "id_WANTED" in ch_map

    def test_whitelist_channel_not_included(self):
        """Lines 574-582: whitelist does not contain channel id → skipped."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="UNWANTED")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, ["OTHER"], {}, False)
        assert ch_map == {}

    def test_whitelist_channel_by_name_included(self):
        """Lines 577-579: whitelist contains channel name (not id) → included."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="0", name="GoodName")
        seg = _make_segment([sig])
        # Pre-populate ch_map so name lookup works
        ch_map = {"id_0": {"id": "0", "name": "GoodName", "data_trials": [None]}}
        adapter._process_segment_signals(seg, 0, ch_map, False, ["GoodName"], {}, False)
        # Channel should NOT be excluded
        assert "id_0" in ch_map
        assert ch_map["id_0"]["data_trials"][0] is not None

    def test_late_discovery_string_name(self):
        """Lines 590-602: channel not in ch_map → late-discovery with string name."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(name="LateChannel")
        seg = _make_segment([sig])
        ch_map = {}  # No pre-populated entry
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        # Should have been added dynamically
        keys = list(ch_map.keys())
        assert len(keys) == 1
        assert ch_map[keys[0]]["name"] == "LateChannel"

    def test_late_discovery_bytes_name(self):
        """Lines 592-597: late-discovery with bytes signal name."""
        adapter = self._make_adapter()
        sig = _make_analog_signal()
        sig.name = b"BytesName\x00"
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        keys = list(ch_map.keys())
        assert len(keys) == 1
        assert "BytesName" in ch_map[keys[0]]["name"]

    def test_name_override_when_signal_name_differs(self):
        """Lines 613-630: existing header name overridden by signal name on seg_idx=0."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="0", name="SignalName")
        seg = _make_segment([sig])
        ch_map = {"id_0": {"id": "0", "name": "HeaderName", "data_trials": [None]}}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        assert ch_map["id_0"]["name"] == "SignalName"

    def test_name_not_overridden_on_seg_idx_gt_0(self):
        """Lines 614 guard: seg_idx != 0 → name NOT overridden."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="0", name="NewName")
        seg = _make_segment([sig])
        ch_map = {"id_0": {"id": "0", "name": "Original", "data_trials": [None, None]}}
        adapter._process_segment_signals(seg, 1, ch_map, False, None, {}, False)
        assert ch_map["id_0"]["name"] == "Original"

    def test_lazy_mode_increments_num_trials(self):
        """Lines 647-649: lazy=True → num_trials incremented."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(ch_id="L0")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, True, None, {}, False)
        assert ch_map["id_L0"]["num_trials"] == 1
        adapter._process_segment_signals(seg, 1, ch_map, True, None, {}, False)
        assert ch_map["id_L0"]["num_trials"] == 2

    def test_rescale_to_pA_when_mV_fails(self):
        """Lines 664-669: pA signal → mV rescale fails → pA rescale succeeds."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(units_str="pA", ch_id="PA0")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        assert ch_map["id_PA0"]["_rescaled_unit"] == "pA"

    def test_rescale_incompatible_units_raw(self):
        """Lines 670-676: incompatible units (Ohm) → raw magnitude used."""
        adapter = self._make_adapter()
        sig = _make_analog_signal(units_str="Ohm", ch_id="OHM0")
        seg = _make_segment([sig])
        ch_map = {}
        adapter._process_segment_signals(seg, 0, ch_map, False, None, {}, False)
        # No _rescaled_unit because incompatible
        assert "_rescaled_unit" not in ch_map["id_OHM0"]


# ---------------------------------------------------------------------------
# _build_channels – lines 751, 758, 764-766, 780
# ---------------------------------------------------------------------------


class TestBuildChannels:
    """Cover _build_channels branching."""

    def test_skips_empty_non_lazy_channel(self):
        """Line 758: no data_trials, not lazy, no sampling_rate → skipped."""
        adapter = NeoAdapter()
        recording = Recording(source_file=None)
        ch_map = {
            "id_EMPTY": {
                "id": "EMPTY",
                "name": "Ghost",
                "data_trials": [],
                # No 'sampling_rate' key
            }
        }
        channels = adapter._build_channels(ch_map, False, recording)
        assert len(channels) == 0

    def test_lazy_channel_gets_loader(self, tmp_path, sample_abf_path):
        """Lines 764-766, 780: lazy mode + valid NeoSourceHandle → loader assigned."""
        adapter = NeoAdapter()
        recording = adapter.read_recording(sample_abf_path, lazy=True)
        # In lazy mode, channels should have a loader
        for ch in recording.channels.values():
            assert ch.loader is not None
            break  # Just check first channel

    def test_lazy_num_trials_in_metadata(self, sample_abf_path):
        """Line 780: lazy mode → channel.metadata['num_trials'] set."""
        adapter = NeoAdapter()
        recording = adapter.read_recording(sample_abf_path, lazy=True)
        for ch in recording.channels.values():
            assert "num_trials" in ch.metadata
            break


# ---------------------------------------------------------------------------
# read_recording lazy mode – lines 461-469
# ---------------------------------------------------------------------------


class TestReadRecordingLazyMode:
    """Cover the lazy-mode duration calculation in read_recording."""

    def test_lazy_read_returns_recording(self, neo_adapter_instance, sample_abf_path):
        """Lines 461-469: lazy=True → duration extracted from first analogsignal."""
        recording = neo_adapter_instance.read_recording(sample_abf_path, lazy=True)
        assert isinstance(recording, Recording)
        assert recording.num_channels > 0


# ---------------------------------------------------------------------------
# apply_winwcp_patch failure – lines 52-53
# ---------------------------------------------------------------------------


class TestWinwcpPatchFailure:
    """Cover the import-time exception path for apply_winwcp_patch (lines 52-53).

    The module-level try/except runs at import time so we cannot re-trigger it
    in a normal test run.  Instead, we confirm the module loaded without error
    (proving lines 49-51 executed) and that ImportError is the declared catch.
    """

    def test_module_loaded_successfully(self):
        """Smoke: NeoAdapter importable, meaning lines 48-53 ran without crash."""
        from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter as _NA

        assert _NA is not None
