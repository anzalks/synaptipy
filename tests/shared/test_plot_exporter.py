"""Integration tests for raster and vector plot exports."""

import numpy as np
import pytest

from synaptipy.shared.plot_exporter import PlotExporter


@pytest.fixture
def plot_widget(qapp):
    """Provide a real plot with labels so exporters exercise text handling."""
    import pyqtgraph as pg

    widget = pg.PlotWidget()
    widget.resize(640, 480)
    widget.setTitle("Export audit")
    widget.setLabel("bottom", "Time (s)")
    widget.setLabel("left", "Voltage (mV)")
    widget.plot(np.array([0.0, 1.0, 2.0]), np.array([-65.0, -60.0, -65.0]), name="Average")
    yield widget
    widget.close()


@pytest.mark.parametrize("file_format", ["png", "jpg", "svg", "pdf"])
def test_plot_exporter_writes_every_supported_format(plot_widget, tmp_path, file_format):
    """Each format advertised by the export dialog produces a non-empty file."""
    output_path = tmp_path / f"plot.{file_format}"

    success = PlotExporter(recording=None, plot_canvas_widget=plot_widget).export(str(output_path), file_format, 300)

    assert success is True
    assert output_path.is_file()
    assert output_path.stat().st_size > 0


def test_svg_export_keeps_labels_as_text_elements(plot_widget, tmp_path):
    """SVG labels remain editable vector text instead of a raster screenshot."""
    output_path = tmp_path / "plot.svg"

    PlotExporter(recording=None, plot_canvas_widget=plot_widget).export(str(output_path), "svg", 300)

    svg = output_path.read_text(encoding="utf-8")
    assert "<text" in svg
    assert "Time (s)" in svg
    assert "Voltage (mV)" in svg
    assert "<image" not in svg


def test_pdf_export_embeds_editable_truetype_text(plot_widget, tmp_path):
    """PDF labels use TrueType fonts, not Type 3 glyph outlines."""
    output_path = tmp_path / "plot.pdf"

    PlotExporter(recording=None, plot_canvas_widget=plot_widget).export(str(output_path), "pdf", 300)

    pdf = output_path.read_bytes()
    assert b"/Type3" not in pdf
    assert b"/FontFile2" in pdf
