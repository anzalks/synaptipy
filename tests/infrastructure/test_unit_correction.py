import neo
import pytest
import quantities as pq

from Synaptipy.infrastructure.file_readers.neo_adapter import NeoAdapter, UnitError


class TestUnitCorrection:

    def test_unit_error_raised_for_low_fs(self):
        """Verify UnitError is raised for dangerously low sampling rates (<100Hz)."""
        adapter = NeoAdapter()
        mock_segment = neo.Segment()
        # 10Hz sampling rate (dangerous)
        mock_anasig = neo.AnalogSignal([1, 2, 3], units="mV", sampling_rate=10.0 * pq.Hz, t_start=0.0 * pq.s)
        mock_anasig.channel_index = 0
        mock_segment.analogsignals.append(mock_anasig)

        metadata_map = {}

        with pytest.raises(UnitError, match="Critical Safety"):
            adapter._process_segment_signals(mock_segment, 0, metadata_map, False, None, force_kHz_to_Hz=False)

    def test_forced_unit_correction(self):
        """Verify force_kHz_to_Hz correctly multiplies sampling rate by 1000."""
        adapter = NeoAdapter()
        mock_segment = neo.Segment()
        # 10Hz sampling rate (e.g. 10kHz read as 10Hz)
        mock_anasig = neo.AnalogSignal([1, 2, 3], units="mV", sampling_rate=10.0 * pq.Hz, t_start=0.0 * pq.s)
        mock_anasig.channel_index = 0
        mock_segment.analogsignals.append(mock_anasig)

        metadata_map = {}

        # Should not raise
        adapter._process_segment_signals(mock_segment, 0, metadata_map, False, None, force_kHz_to_Hz=True)

        # Verify correction
        key = "id_0"
        assert key in metadata_map
        assert metadata_map[key]["sampling_rate"] == 10000.0  # 10 * 1000
        assert metadata_map[key]["units"] == "Hz"
