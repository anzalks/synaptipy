from Synaptipy.application.controllers.analysis_formatter import generate_methods_text
from Synaptipy.core.results import SpikeTrainResult


def test_generate_methods_text_spike_detection():
    """Verify generated text contains key parameters."""
    params = {"threshold": -20.0, "refractory_period": 0.002, "dvdt_threshold": 10.0}
    result = SpikeTrainResult(value=0, unit="Hz", spike_times=[], mean_frequency=0.0, parameters=params)

    text = generate_methods_text(result)

    assert "voltage threshold crossing algorithm" in text
    assert "-20.0 mV" in text
    assert "2.00 ms" in text  # 0.002s converted to ms
    assert "dV/dt onset threshold of 10.0 V/s" in text
