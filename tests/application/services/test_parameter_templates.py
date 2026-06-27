# -*- coding: utf-8 -*-
"""Tests for application.services.parameter_templates.ParameterTemplateManager."""

import json
from pathlib import Path

import pytest

from synaptipy.application.services.parameter_templates import ParameterTemplateManager


@pytest.fixture
def mgr(tmp_path):
    """Return a ParameterTemplateManager using a temporary directory."""
    return ParameterTemplateManager(template_dir=tmp_path)


class TestSaveAndLoad:
    def test_save_creates_json_file(self, mgr, tmp_path):
        mgr.save_template("my_template", {"threshold": -20.0})
        assert (tmp_path / "my_template.json").exists()

    def test_save_returns_path(self, mgr, tmp_path):
        p = mgr.save_template("t1", {"a": 1})
        assert isinstance(p, Path)
        assert p.name == "t1.json"

    def test_load_returns_parameters(self, mgr):
        mgr.save_template("t2", {"cutoff": 300.0, "order": 4})
        params = mgr.load_template("t2")
        assert params == {"cutoff": 300.0, "order": 4}

    def test_load_nonexistent_returns_none(self, mgr):
        result = mgr.load_template("does_not_exist")
        assert result is None

    def test_save_stores_description_and_type(self, mgr, tmp_path):
        mgr.save_template("t3", {"x": 1}, description="Test desc", analysis_type="spike")
        raw = json.loads((tmp_path / "t3.json").read_text())
        assert raw["description"] == "Test desc"
        assert raw["analysis_type"] == "spike"

    def test_save_includes_version(self, mgr, tmp_path):
        mgr.save_template("t4", {})
        raw = json.loads((tmp_path / "t4.json").read_text())
        assert raw["version"] == "1.0"


class TestListTemplates:
    def test_empty_dir_returns_empty_list(self, mgr):
        assert mgr.list_templates() == []

    def test_lists_all_templates(self, mgr):
        mgr.save_template("alpha", {})
        mgr.save_template("beta", {})
        names = [t["name"] for t in mgr.list_templates()]
        assert "alpha" in names
        assert "beta" in names

    def test_filter_by_analysis_type(self, mgr):
        mgr.save_template("s1", {}, analysis_type="spike")
        mgr.save_template("r1", {}, analysis_type="rmp")
        spikes = mgr.list_templates(analysis_type="spike")
        assert len(spikes) == 1
        assert spikes[0]["name"] == "s1"

    def test_filter_excludes_other_types(self, mgr):
        mgr.save_template("s2", {}, analysis_type="spike")
        mgr.save_template("r2", {}, analysis_type="rmp")
        rmp = mgr.list_templates(analysis_type="rmp")
        assert all(t["analysis_type"] == "rmp" for t in rmp)

    def test_list_includes_path(self, mgr):
        mgr.save_template("pathtest", {})
        result = mgr.list_templates()
        assert "path" in result[0]

    def test_corrupt_json_skipped_gracefully(self, mgr, tmp_path):
        (tmp_path / "corrupt.json").write_text("not json {{{{")
        # Should not raise; corrupt files are silently skipped
        result = mgr.list_templates()
        assert all(isinstance(t, dict) for t in result)


class TestDeleteTemplate:
    def test_delete_existing_returns_true(self, mgr, tmp_path):
        mgr.save_template("del_me", {})
        assert mgr.delete_template("del_me") is True
        assert not (tmp_path / "del_me.json").exists()

    def test_delete_nonexistent_returns_false(self, mgr):
        assert mgr.delete_template("ghost") is False

    def test_delete_removes_from_list(self, mgr):
        mgr.save_template("removable", {})
        mgr.delete_template("removable")
        names = [t["name"] for t in mgr.list_templates()]
        assert "removable" not in names


class TestGetBuiltinTemplates:
    def test_returns_list(self, mgr):
        result = mgr.get_builtin_templates()
        assert isinstance(result, list)

    def test_builtins_are_dicts(self, mgr):
        for tmpl in mgr.get_builtin_templates():
            assert isinstance(tmpl, dict)


class TestDefaultDirectory:
    def test_default_dir_is_created(self, tmp_path, monkeypatch):
        """ParameterTemplateManager uses ~/.synaptipy/templates by default."""
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        # Re-import to get fresh default path evaluation
        import importlib

        import synaptipy.application.services.parameter_templates as mod

        importlib.reload(mod)
        mgr2 = mod.ParameterTemplateManager()
        assert mgr2.template_dir.exists()
