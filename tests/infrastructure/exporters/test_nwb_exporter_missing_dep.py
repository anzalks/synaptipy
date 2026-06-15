import importlib
import sys

import pytest


def test_nwb_exporter_missing_pynwb_fallback():
    """
    Test that the fallback sentinel classes are properly defined and raise
    ImportError when pynwb is not installed.
    """
    from Synaptipy.infrastructure.exporters import nwb_exporter

    # Save original state
    original_pynwb = sys.modules.get("pynwb")

    try:
        # Hide pynwb to force ImportError
        sys.modules["pynwb"] = None

        # Reload the module to trigger the except ImportError block
        importlib.reload(nwb_exporter)

        assert not nwb_exporter.PYNWB_AVAILABLE

        # Test all sentinel classes
        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.NWBHDF5IO()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.NWBFile()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.PatchClampSeries()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.CurrentClampSeries()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.VoltageClampSeries()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.CurrentClampStimulusSeries()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.VoltageClampStimulusSeries()

        with pytest.raises(ImportError, match="pynwb is required"):
            nwb_exporter.IntracellularElectrode()

    finally:
        # Restore sys.modules
        if original_pynwb is not None:
            sys.modules["pynwb"] = original_pynwb
        else:
            sys.modules.pop("pynwb", None)

        # Reload again to restore normal state for subsequent tests
        importlib.reload(nwb_exporter)
