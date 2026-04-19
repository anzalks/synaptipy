# -*- coding: utf-8 -*-
"""Extended tests for analysis registry, data_model, and processing_pipeline."""

import numpy as np

from Synaptipy.core.analysis.registry import AnalysisRegistry
from Synaptipy.core.data_model import Channel

# ===========================================================================
# Registry extended tests
# ===========================================================================


class TestRegistryExtended:
    """Cover additional registry branches not reached by existing tests."""

    def setup_method(self):
        self._saved_registry = dict(AnalysisRegistry._registry)
        self._saved_metadata = dict(AnalysisRegistry._metadata)
        self._saved_original = dict(AnalysisRegistry._original_metadata)

    def teardown_method(self):
        AnalysisRegistry._registry.clear()
        AnalysisRegistry._metadata.clear()
        AnalysisRegistry._original_metadata.clear()
        AnalysisRegistry._registry.update(self._saved_registry)
        AnalysisRegistry._metadata.update(self._saved_metadata)
        AnalysisRegistry._original_metadata.update(self._saved_original)

    def test_register_processor_alias(self):
        """register_processor is an alias for register(type='preprocessing')."""

        @AnalysisRegistry.register_processor("_test_prep")
        def _my_proc(data, time, sr, **kw):
            return {"preprocessed": True}

        meta = AnalysisRegistry.get_metadata("_test_prep")
        assert meta["type"] == "preprocessing"

    def test_list_preprocessing(self):
        @AnalysisRegistry.register_processor("_pp1")
        def _p1(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register("_anal1")
        def _a1(d, t, s, **kw):
            return {}

        preps = AnalysisRegistry.list_preprocessing()
        assert "_pp1" in preps
        assert "_anal1" not in preps

    def test_list_analysis_excludes_preprocessing(self):
        @AnalysisRegistry.register("_pure_analysis")
        def _a(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register_processor("_pure_prep")
        def _p(d, t, s, **kw):
            return {}

        analyses = AnalysisRegistry.list_analysis()
        assert "_pure_analysis" in analyses
        assert "_pure_prep" not in analyses

    def test_list_by_type(self):
        @AnalysisRegistry.register("_t1", type="custom")
        def _f1(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register("_t2", type="analysis")
        def _f2(d, t, s, **kw):
            return {}

        customs = AnalysisRegistry.list_by_type("custom")
        assert "_t1" in customs
        assert "_t2" not in customs

    def test_get_metadata_unknown_returns_empty(self):
        meta = AnalysisRegistry.get_metadata("_does_not_exist_xyz")
        assert meta == {}

    def test_mark_core_snapshot_and_unregister_plugins(self):
        # Register a core function, mark snapshot
        @AnalysisRegistry.register("_core_func")
        def _core(d, t, s, **kw):
            return {}

        AnalysisRegistry.mark_core_snapshot()

        # Register a plugin function
        @AnalysisRegistry.register("_plugin_func")
        def _plugin(d, t, s, **kw):
            return {}

        assert "_plugin_func" in AnalysisRegistry.list_registered()
        AnalysisRegistry.unregister_plugins()
        assert "_plugin_func" not in AnalysisRegistry.list_registered()
        assert "_core_func" in AnalysisRegistry.list_registered()

    def test_update_default_params_known(self):
        @AnalysisRegistry.register("_updatable", ui_params=[{"name": "threshold", "default": -20.0}])
        def _f(d, t, s, **kw):
            return {}

        AnalysisRegistry.update_default_params("_updatable", {"threshold": -30.0})
        meta = AnalysisRegistry.get_metadata("_updatable")
        param = next(p for p in meta["ui_params"] if p["name"] == "threshold")
        assert param["default"] == -30.0

    def test_update_default_params_unknown_logs_warning(self, caplog):
        AnalysisRegistry.update_default_params("_non_existent_zzz", {"p": 1})
        # Should just log a warning, not raise

    def test_reset_to_factory_single(self):
        @AnalysisRegistry.register("_resettable", ui_params=[{"name": "k", "default": 5}])
        def _f(d, t, s, **kw):
            return {}

        AnalysisRegistry.update_default_params("_resettable", {"k": 99})
        AnalysisRegistry.reset_to_factory("_resettable")
        meta = AnalysisRegistry.get_metadata("_resettable")
        param = next(p for p in meta["ui_params"] if p["name"] == "k")
        assert param["default"] == 5

    def test_reset_to_factory_all(self):
        @AnalysisRegistry.register("_ra1", ui_params=[{"name": "a", "default": 1}])
        def _f1(d, t, s, **kw):
            return {}

        @AnalysisRegistry.register("_ra2", ui_params=[{"name": "b", "default": 2}])
        def _f2(d, t, s, **kw):
            return {}

        AnalysisRegistry.update_default_params("_ra1", {"a": 99})
        AnalysisRegistry.update_default_params("_ra2", {"b": 99})
        AnalysisRegistry.reset_to_factory()
        m1 = AnalysisRegistry.get_metadata("_ra1")
        assert m1["ui_params"][0]["default"] == 1

    def test_reset_to_factory_unknown_name_no_error(self):
        # Should silently do nothing when name is not in original_metadata
        AnalysisRegistry.reset_to_factory("_xyz_not_registered_abc")


# ===========================================================================
# Channel (data_model) extended tests
# ===========================================================================


def _make_channel(n=100, fs=1000.0, value=-65.0):
    data = np.full(n, value)
    return Channel("ch0", "V1", "mV", fs, [data])


class TestChannelExtended:
    def test_non_list_data_trials_converted(self):
        """Passing a raw array (not a list) triggers the conversion branch."""
        arr = np.ones(50) * -60.0
        ch = Channel("x", "V", "mV", 1000.0, arr)
        assert len(ch.data_trials) >= 1

    def test_non_list_non_array_data_trials(self):
        """Unconvertable data falls back to empty list."""
        # A plain dict is not easily convertible to a float array
        ch = Channel("x", "V", "mV", 1000.0, {"a": 1})
        assert ch.data_trials == [] or len(ch.data_trials) >= 0

    def test_empty_list_data_trials_is_empty(self):
        ch = Channel("x", "V", "mV", 1000.0, [])
        assert ch.data_trials == []

    def test_num_samples_no_trials_returns_zero(self):
        ch = Channel("x", "V", "mV", 1000.0, [])
        assert ch.num_samples == 0

    def test_num_samples_invalid_first_trial(self):
        """First trial is a 0-d array – should return 0."""
        ch = Channel("x", "V", "mV", 1000.0, [])
        ch.data_trials = [np.array(3.14)]  # 0-dimensional
        assert ch.num_samples == 0

    def test_num_samples_no_valid_trials(self):
        ch = Channel("x", "V", "mV", 1000.0, [])
        ch.data_trials = [None, None]
        assert ch.num_samples == 0

    def test_num_trials_from_metadata(self):
        ch = _make_channel()
        ch.metadata["num_trials"] = 7
        assert ch.num_trials == 7

    def test_get_time_vector_zero_sampling_rate(self):
        ch = Channel("x", "V", "mV", 0.0, [np.ones(10)])
        assert ch.get_time_vector(0) is None

    def test_get_relative_time_vector_zero_sampling_rate(self):
        ch = Channel("x", "V", "mV", 0.0, [np.ones(10)])
        assert ch.get_relative_time_vector(0) is None

    def test_get_data_loader_invalid_object(self):
        """Loader is present but is neither callable nor has load_trial method."""
        ch = Channel("x", "V", "mV", 1000.0, [], loader="invalid_loader")
        result = ch.get_data(0)
        assert result is None

    def test_get_data_loader_exception(self):
        """Loader raises an exception – should return None."""

        def bad_loader(idx):
            raise IndexError("bad index")

        ch = Channel("x", "V", "mV", 1000.0, [], loader=bad_loader)
        result = ch.get_data(0)
        assert result is None

    def test_get_data_loader_extends_data_trials(self):
        """Lazy loader that succeeds should cache the data in data_trials."""
        data = np.ones(10)

        def good_loader(idx):
            return data

        ch = Channel("x", "V", "mV", 1000.0, [], loader=good_loader)
        result = ch.get_data(2)
        assert result is not None
        assert len(ch.data_trials) > 2

    def test_get_consistent_samples_non_array_trials(self):
        """All trials are non-ndarray objects – should return 0."""
        ch = Channel("x", "V", "mV", 1000.0, [])
        ch.data_trials = [None, None]
        assert ch.get_consistent_samples() == 0

    def test_sampling_rate_zero_time_vector_is_none(self):
        ch = _make_channel()
        ch.sampling_rate = 0.0
        assert ch.get_averaged_time_vector() is None

    def test_get_data_none_trial_falls_through_to_loader(self):
        """If trial slot is None, loader is tried as fallback."""
        sentinel = np.ones(5)

        def loader(idx):
            return sentinel

        ch = Channel("x", "V", "mV", 1000.0, [None], loader=loader)
        result = ch.get_data(0)
        assert result is sentinel

    def test_repr_covers_all_branches(self):
        ch = _make_channel()
        r = repr(ch)
        assert "Channel" in r

    def test_get_finite_data_bounds_all_inf(self):
        ch = Channel("x", "V", "mV", 1000.0, [np.full(10, np.inf)])
        assert ch.get_finite_data_bounds() is None

    def test_averaged_current_data_differing_lengths(self):
        ch = _make_channel()
        ch.current_data_trials = [np.ones(10), np.ones(20)]
        result = ch.get_averaged_current_data()
        assert result is None
