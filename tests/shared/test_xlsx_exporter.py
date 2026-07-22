"""Tests for the dependency-free tabular Excel writer."""

import zipfile

import numpy as np
import pandas as pd

from synaptipy.shared.xlsx_exporter import write_dataframe_to_xlsx


def test_write_dataframe_to_xlsx_preserves_scalar_types_and_literal_text(tmp_path):
    """The generated workbook uses numeric, boolean, and literal text cells."""
    output_path = tmp_path / "results.xlsx"
    dataframe = pd.DataFrame({"count": [np.int64(2)], "accepted": [True], "note": ["=literal"]})

    write_dataframe_to_xlsx(dataframe, output_path, sheet_name="Batch/Results")

    with zipfile.ZipFile(output_path) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8")
        worksheet = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert 'name="Batch_Results"' in workbook
    assert '<c r="A2"><v>2</v></c>' in worksheet
    assert '<c r="B2" t="b"><v>1</v></c>' in worksheet
    assert '<c r="C2" t="inlineStr"><is><t xml:space="preserve">=literal</t></is></c>' in worksheet
