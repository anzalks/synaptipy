"""Dependency-free XLSX writing for tabular application exports."""

import math
import re
import zipfile
from datetime import date, datetime
from numbers import Number
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

_INVALID_XML_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def write_dataframe_to_xlsx(dataframe: Any, output_path: str | Path, sheet_name: str = "Results") -> None:
    """Write a dataframe-like object as a standards-compliant XLSX workbook.

    The application deliberately keeps this compact writer dependency-free so
    the advertised Excel export works in the pinned desktop environment. Cells
    are emitted as numbers, booleans, or literal inline text, which also avoids
    treating user-provided strings as Excel formulas.
    """
    output = Path(output_path)
    headers = [str(column) for column in dataframe.columns]
    rows = dataframe.itertuples(index=False, name=None)
    worksheet_xml = _worksheet_xml(headers, rows)
    safe_sheet_name = escape(_normalise_sheet_name(sheet_name), {'"': "&quot;"})

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("xl/workbook.xml", _WORKBOOK.format(sheet_name=safe_sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", _WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", worksheet_xml)


def _worksheet_xml(headers: list[str], rows: Any) -> str:
    """Return worksheet XML for headers followed by iterable row values."""
    xml_rows = [_row_xml(1, headers)]
    for row_number, row in enumerate(rows, start=2):
        xml_rows.append(_row_xml(row_number, row))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        "</worksheet>"
    )


def _row_xml(row_number: int, values: Any) -> str:
    """Serialise one Excel row using inline strings for literal text cells."""
    cells = [
        _cell_xml(f"{_column_name(column_index)}{row_number}", value)
        for column_index, value in enumerate(values, start=1)
    ]
    return f'<row r="{row_number}">{"".join(cells)}</row>'


def _cell_xml(reference: str, value: Any) -> str:
    """Serialise a single cell while preserving data as safely as possible."""
    value = _normalise_value(value)
    if value is None:
        return f'<c r="{reference}"/>'
    if isinstance(value, bool):
        return f'<c r="{reference}" t="b"><v>{int(value)}</v></c>'
    if isinstance(value, Number):
        return f'<c r="{reference}"><v>{value}</v></c>'

    text = escape(_INVALID_XML_CHARS.sub("", str(value)))
    return f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _normalise_value(value: Any) -> Any:
    """Convert NumPy and date-like values to XML-safe scalar representations."""
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except ValueError:
            pass
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def _column_name(index: int) -> str:
    """Return an A1-style Excel column name for a one-based index."""
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _normalise_sheet_name(sheet_name: str) -> str:
    """Apply Excel's sheet-name constraints without rejecting an export."""
    return re.sub(r"[\\/*?:\[\]]", "_", sheet_name)[:31] or "Results"


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml"
    ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>"""

_ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
    Target="xl/workbook.xml"/>
</Relationships>"""

_WORKBOOK = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/></sheets>
</workbook>"""

_WORKBOOK_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1"
    Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
    Target="worksheets/sheet1.xml"/>
</Relationships>"""
