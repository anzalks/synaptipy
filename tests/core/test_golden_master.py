"""
Golden master integration tests for the core analysis pipeline.

These tests exist strictly to detect if a future scipy, numpy, or neo update
silently alters mathematical behaviours.  They load real ABF files from the
examples/data/ directory, run the core passive-properties pipeline, and assert
that computed values match those produced by the reference implementation.

If a *deliberate* algorithm change is made, update the hardcoded constants here
after verifying the new outputs are scientifically correct.

Run only these tests:
    pytest tests/core/test_golden_master.py -v

Skip automatically when example data files are absent (CI without data).
"""

import pathlib

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_DATA_DIR = _REPO_ROOT / "examples" / "data"

_ABF_0019 = _DATA_DIR / "2023_04_11_0019.abf"  # passive properties, -20 pA at 200-300 ms
_ABF_0021 = _DATA_DIR / "2023_04_11_0021.abf"  # firing / I-V curve
_ABF_0022 = _DATA_DIR / "2023_04_11_0022.abf"  # RMP + Rin, -20 pA at 15.95-16.35 s

_MISSING_DATA = not (_ABF_0019.exists() and _ABF_0021.exists() and _ABF_0022.exists())
_SKIP_REASON = "Example ABF data files not found - skipping golden master tests"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def neo_adapter():
    """Return a NeoAdapter instance (module-scoped to avoid repeated init)."""
    from Synaptipy.infrastructure.file_readers import NeoAdapter

    return NeoAdapter()


@pytest.fixture(scope="module")
def rec_0019(neo_adapter):
    """Recording from 0019.abf - passive properties file."""
    return neo_adapter.read_recording(str(_ABF_0019))


@pytest.fixture(scope="module")
def rec_0021(neo_adapter):
    """Recording from 0021.abf - firing / I-V curve file."""
    return neo_adapter.read_recording(str(_ABF_0021))


@pytest.fixture(scope="module")
def rec_0022(neo_adapter):
    """Recording from 0022.abf - synaptic / long-protocol file."""
    return neo_adapter.read_recording(str(_ABF_0022))


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _ch0(rec):
    """Return the first channel of a Recording."""
    return list(rec.channels.values())[0]


# ---------------------------------------------------------------------------
# File 0019 - passive properties (-20 pA step at 200-300 ms)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0019:
    """Golden master values for 2023_04_11_0019.abf (passive properties)."""

    def test_recording_structure(self, rec_0019):
        """File should have 1 channel and 5 trials, 1 s each."""
        assert rec_0019.num_channels == 1
        ch = _ch0(rec_0019)
        assert ch.num_trials == 5
        t = ch.get_relative_time_vector(0)
        assert pytest.approx(t[-1], abs=1e-4) == 1.0

    def test_rmp_trial0(self, rec_0019):
        """RMP from trial 0 baseline (0-0.15 s) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 0.15))
        assert result.is_valid
        assert result.unit == "mV"
        # Reference: -65.21112060546875
        assert pytest.approx(result.value, rel=1e-5) == -65.21112060546875

    def test_rin_trial0(self, rec_0019):
        """Rin (steady-state) from trial 0 (-20 pA step) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rin

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rin(
            d,
            t,
            current_amplitude=-20.0,
            baseline_window=(0.0, 0.19),
            response_window=(0.2, 0.3),
        )
        assert result.is_valid
        # Reference steady-state Rin: 118.26362609863281 MOhm
        assert pytest.approx(result.rin_steady_state_mohm, rel=1e-5) == 118.26362609863281
        # Reference peak Rin: 122.87483215332031 MOhm
        assert pytest.approx(result.rin_peak_mohm, rel=1e-5) == 122.87483215332031

    def test_tau_trial0(self, rec_0019):
        """Membrane time constant from trial 0 should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_tau

        ch = _ch0(rec_0019)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_tau(d, t, stim_start_time=0.2, fit_duration=0.08)
        assert result is not None
        tau_ms = float(result["tau_ms"])
        assert not np.isnan(tau_ms), "Tau fit returned NaN"
        # Reference tau: 84.29428907793942 ms - allow 1% relative tolerance
        # because curve_fit is iterative and small FP differences across platforms
        # may push the result slightly outside a tighter bound.
        assert pytest.approx(tau_ms, rel=1e-2) == 84.29428907793942


# ---------------------------------------------------------------------------
# File 0022 - long protocol (RMP + Rin at 15.95-16.35 s, -20 pA)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0022:
    """Golden master values for 2023_04_11_0022.abf (long synaptic protocol)."""

    def test_recording_structure(self, rec_0022):
        """File should have 4 channels and 3 trials."""
        assert rec_0022.num_channels == 4
        ch = _ch0(rec_0022)
        assert ch.num_trials == 3

    def test_rmp_trial0(self, rec_0022):
        """RMP from trial 0, baseline window 0-15.9 s, should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0022)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 15.9))
        assert result.is_valid
        # Reference: -65.37178802490234
        assert pytest.approx(result.value, rel=1e-5) == -65.37178802490234

    def test_rin_trial0(self, rec_0022):
        """Rin from trial 0, step window 15.95-16.35 s, should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rin

        ch = _ch0(rec_0022)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rin(
            d,
            t,
            current_amplitude=-20.0,
            baseline_window=(0.0, 15.9),
            response_window=(15.95, 16.35),
        )
        assert result.is_valid
        # Reference steady-state Rin: 75.36430358886719 MOhm
        assert pytest.approx(result.rin_steady_state_mohm, rel=1e-5) == 75.36430358886719
        # Reference peak Rin: 135.9516143798828 MOhm
        assert pytest.approx(result.rin_peak_mohm, rel=1e-5) == 135.9516143798828


# ---------------------------------------------------------------------------
# File 0021 - firing / I-V curve
# ---------------------------------------------------------------------------


@pytest.mark.skipif(_MISSING_DATA, reason=_SKIP_REASON)
class TestGoldenMaster0021:
    """Golden master values for 2023_04_11_0021.abf (firing properties)."""

    def test_recording_structure(self, rec_0021):
        """File should have 1 channel and 20 trials, 0.5 s each."""
        assert rec_0021.num_channels == 1
        ch = _ch0(rec_0021)
        assert ch.num_trials == 20
        t = ch.get_relative_time_vector(0)
        assert pytest.approx(t[-1], abs=1e-4) == 0.5

    def test_rmp_baseline_trial0(self, rec_0021):
        """RMP from trial 0 baseline (0-0.1 s) should match reference."""
        from Synaptipy.core.analysis.passive_properties import calculate_rmp

        ch = _ch0(rec_0021)
        d = ch.get_data(0)
        t = ch.get_relative_time_vector(0)
        result = calculate_rmp(d, t, baseline_window=(0.0, 0.1))
        assert result.is_valid
        # Reference: -65.36598205566406
        assert pytest.approx(result.value, rel=1e-5) == -65.36598205566406

    def test_action_potential_peak_last_trial(self, rec_0021):
        """Last trial (highest current injection) should contain action potentials."""
        ch = _ch0(rec_0021)
        last_idx = ch.num_trials - 1
        d = ch.get_data(last_idx)
        # Reference max voltage: 42.6971 mV (action potential peak)
        ap_peak = float(np.max(d))
        assert pytest.approx(ap_peak, rel=1e-4) == 42.6971435546875
        # Sanity: last trial mean is depolarised relative to rest
        assert float(np.mean(d)) > -65.0, "Last trial mean should be depolarised"
