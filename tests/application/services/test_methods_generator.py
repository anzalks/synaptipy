# -*- coding: utf-8 -*-
"""Tests for application.services.methods_generator.MethodsGenerator."""

from synaptipy.application.services.methods_generator import MethodsGenerator


class TestMethodsGeneratorParagraph:
    """Tests for generate_methods_paragraph."""

    def setup_method(self):
        self.gen = MethodsGenerator()

    def test_returns_string(self):
        result = self.gen.generate_methods_paragraph([])
        assert isinstance(result, str)

    def test_contains_synaptipy(self):
        result = self.gen.generate_methods_paragraph([])
        assert "Synaptipy" in result

    def test_contains_python_version(self):
        import platform

        result = self.gen.generate_methods_paragraph([])
        assert platform.python_version() in result

    def test_file_format_included(self):
        result = self.gen.generate_methods_paragraph([], file_format="Axon ABF")
        assert "Axon ABF" in result

    def test_file_format_omitted_when_empty(self):
        result = self.gen.generate_methods_paragraph([])
        assert "Recordings were acquired" not in result

    def test_n_cells_and_recordings_included(self):
        result = self.gen.generate_methods_paragraph([], n_cells=5, n_recordings=20)
        assert "20 recordings" in result
        assert "5 cells" in result

    def test_n_cells_omitted_when_zero(self):
        result = self.gen.generate_methods_paragraph([])
        assert "A total of" not in result

    def test_analysis_params_included(self):
        analyses = [{"name": "Spike Detection", "parameters": {"threshold": -20, "min_width_ms": 0.5}}]
        result = self.gen.generate_methods_paragraph(analyses)
        assert "Spike Detection" in result
        assert "threshold" in result

    def test_analysis_without_params_skipped(self):
        analyses = [{"name": "Spike Detection", "parameters": {}}]
        result = self.gen.generate_methods_paragraph(analyses)
        # No param_str appended when params is empty
        assert "Spike Detection was performed with parameters" not in result

    def test_date_appears_in_output(self):
        from datetime import datetime

        result = self.gen.generate_methods_paragraph([])
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result

    def test_nwb_reference_in_output(self):
        result = self.gen.generate_methods_paragraph([])
        assert "NWB" in result


class TestMethodsGeneratorCitation:
    """Tests for generate_software_citation."""

    def setup_method(self):
        self.gen = MethodsGenerator()

    def test_returns_string(self):
        assert isinstance(self.gen.generate_software_citation(), str)

    def test_contains_github_url(self):
        citation = self.gen.generate_software_citation()
        assert "github.com/anzalks/synaptipy" in citation

    def test_contains_author(self):
        citation = self.gen.generate_software_citation()
        assert "Shahul" in citation

    def test_contains_version(self):
        import synaptipy

        version = getattr(synaptipy, "__version__", "unknown")
        assert version in self.gen.generate_software_citation()


class TestMethodsGeneratorSummary:
    """Tests for generate_analysis_summary."""

    def setup_method(self):
        self.gen = MethodsGenerator()

    def test_returns_string(self):
        assert isinstance(self.gen.generate_analysis_summary([]), str)

    def test_contains_software_row(self):
        result = self.gen.generate_analysis_summary([])
        assert "Synaptipy" in result

    def test_contains_platform_row(self):
        import platform

        result = self.gen.generate_analysis_summary([])
        assert platform.system() in result

    def test_analysis_row_included(self):
        analyses = [{"name": "RMP", "parameters": {"window_ms": 50}}]
        result = self.gen.generate_analysis_summary(analyses)
        assert "RMP" in result
        assert "window_ms" in result

    def test_empty_analyses_no_data_rows(self):
        result = self.gen.generate_analysis_summary([])
        # Header row present but no data rows beyond header
        assert "| Analysis | Parameters |" in result

    def test_analysis_without_name_uses_unknown(self):
        analyses = [{"parameters": {"x": 1}}]
        result = self.gen.generate_analysis_summary(analyses)
        assert "unknown" in result
