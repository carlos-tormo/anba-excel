"""Safe XLSX/CSV generation and upload parsing infrastructure."""

from __future__ import annotations

import base64
import csv
from datetime import UTC, datetime
import io
import math
import re
from typing import Any, Dict, List
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import escape as xml_escape

try:
    from ..domain._values import parse_int
except ImportError:  # pragma: no cover
    from domain._values import parse_int

SPREADSHEET_MAX_BYTES = 5_000_000
SPREADSHEET_MAX_BASE64_CHARS = ((SPREADSHEET_MAX_BYTES + 2) // 3) * 4 + 16
XLSX_MAX_ARCHIVE_ENTRIES = 256
XLSX_MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
XLSX_MAX_ENTRY_BYTES = 32 * 1024 * 1024
XLSX_MAX_COMPRESSION_RATIO = 200

def _xlsx_clean_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return "".join(ch if ch in "\t\n\r" or ord(ch) >= 32 else " " for ch in text)


def _xlsx_attr(value: Any) -> str:
    return xml_escape(_xlsx_clean_text(value), {'"': "&quot;", "'": "&apos;"})


def _xlsx_col_name(index: int) -> str:
    name = ""
    value = int(index)
    while value:
        value, remainder = divmod(value - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _xlsx_cell_ref(row_index: int, col_index: int) -> str:
    return f"{_xlsx_col_name(col_index)}{row_index}"


def _xlsx_cell(row_index: int, col_index: int, value: Any) -> str:
    ref = _xlsx_cell_ref(row_index, col_index)
    if isinstance(value, bool):
        value = "Sí" if value else "No"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isfinite(numeric):
            rendered = str(int(numeric)) if numeric.is_integer() else repr(numeric)
            return f'<c r="{ref}"><v>{rendered}</v></c>'
    text = xml_escape(_xlsx_clean_text(value))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'


def _xlsx_sheet_xml(rows: List[List[Any]]) -> str:
    sheet_rows: List[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(_xlsx_cell(row_index, col_index, value) for col_index, value in enumerate(row, start=1))
        sheet_rows.append(f'<row r="{row_index}">{cells}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheetData>{''.join(sheet_rows)}</sheetData>"
        "</worksheet>"
    )


def _xlsx_sheet_name(name: str, used_names: set[str]) -> str:
    clean = re.sub(r"[\[\]:*?/\\]", " ", str(name or "Sheet")).strip() or "Sheet"
    clean = clean[:31]
    candidate = clean
    suffix = 1
    while candidate in used_names:
        suffix_text = f" {suffix}"
        candidate = f"{clean[:31 - len(suffix_text)]}{suffix_text}"
        suffix += 1
    used_names.add(candidate)
    return candidate


def _xlsx_workbook_bytes(sheets: List[Dict[str, Any]]) -> bytes:
    used_names: set[str] = set()
    normalized_sheets = [
        {
            "name": _xlsx_sheet_name(str(sheet.get("name") or f"Sheet {idx}"), used_names),
            "rows": sheet.get("rows") or [],
        }
        for idx, sheet in enumerate(sheets, start=1)
    ]
    worksheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for idx, _ in enumerate(normalized_sheets, start=1)
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{worksheet_overrides}"
        "</Types>"
    )
    workbook_sheets = "".join(
        f'<sheet name="{_xlsx_attr(sheet["name"])}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, sheet in enumerate(normalized_sheets, start=1)
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{workbook_sheets}</sheets>"
        "</workbook>"
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(
            f'<Relationship Id="rId{idx}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
            for idx, _ in enumerate(normalized_sheets, start=1)
        )
        + "</Relationships>"
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )
    created = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>ANBA2K</dc:creator>"
        "<cp:lastModifiedBy>ANBA2K</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )
    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>ANBA2K</Application>"
        "</Properties>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("docProps/core.xml", core)
        archive.writestr("docProps/app.xml", app)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        for idx, sheet in enumerate(normalized_sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{idx}.xml", _xlsx_sheet_xml(sheet["rows"]))
    return output.getvalue()


def _xlsx_col_index_from_ref(cell_ref: str) -> int:
    letters = re.sub(r"[^A-Za-z]", "", str(cell_ref or ""))
    value = 0
    for char in letters.upper():
        value = value * 26 + (ord(char) - ord("A") + 1)
    return max(1, value)


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    try:
        raw = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    strings: List[str] = []
    for item in root.iter():
        if item.tag.rsplit("}", 1)[-1] != "si":
            continue
        parts: List[str] = []
        for child in item.iter():
            if child.tag.rsplit("}", 1)[-1] == "t" and child.text:
                parts.append(child.text)
        strings.append("".join(parts))
    return strings


def _xlsx_cell_text(cell: ET.Element, shared_strings: List[str]) -> str:
    cell_type = str(cell.attrib.get("t") or "")
    if cell_type == "inlineStr":
        parts: List[str] = []
        for child in cell.iter():
            if child.tag.rsplit("}", 1)[-1] == "t" and child.text:
                parts.append(child.text)
        return "".join(parts).strip()
    value_text = ""
    for child in cell:
        if child.tag.rsplit("}", 1)[-1] == "v":
            value_text = child.text or ""
            break
    if cell_type == "s":
        index = parse_int(value_text)
        if index is not None and 0 <= index < len(shared_strings):
            return str(shared_strings[index]).strip()
        return ""
    return str(value_text or "").strip()


def _xlsx_first_sheet_rows(file_bytes: bytes) -> List[List[str]]:
    with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as archive:
        entries = archive.infolist()
        if len(entries) > XLSX_MAX_ARCHIVE_ENTRIES:
            raise ValueError("xlsx_archive_too_large")
        total_uncompressed = 0
        for entry in entries:
            if entry.is_dir():
                continue
            if entry.file_size > XLSX_MAX_ENTRY_BYTES:
                raise ValueError("xlsx_archive_too_large")
            total_uncompressed += entry.file_size
            if total_uncompressed > XLSX_MAX_UNCOMPRESSED_BYTES:
                raise ValueError("xlsx_archive_too_large")
            if entry.file_size > 0:
                compressed_size = max(1, entry.compress_size)
                if entry.file_size / compressed_size > XLSX_MAX_COMPRESSION_RATIO:
                    raise ValueError("xlsx_suspicious_compression")
        shared_strings = _xlsx_shared_strings(archive)
        try:
            sheet_bytes = archive.read("xl/worksheets/sheet1.xml")
        except KeyError as err:
            raise ValueError("xlsx_first_sheet_missing") from err
        root = ET.fromstring(sheet_bytes)
        rows: List[List[str]] = []
        for row in root.iter():
            if row.tag.rsplit("}", 1)[-1] != "row":
                continue
            values: Dict[int, str] = {}
            max_col = 0
            for cell in row:
                if cell.tag.rsplit("}", 1)[-1] != "c":
                    continue
                col_idx = _xlsx_col_index_from_ref(str(cell.attrib.get("r") or ""))
                max_col = max(max_col, col_idx)
                values[col_idx] = _xlsx_cell_text(cell, shared_strings)
            if max_col <= 0:
                rows.append([])
            else:
                rows.append([values.get(col_idx, "") for col_idx in range(1, max_col + 1)])
        return rows


def _spreadsheet_rows_from_payload(
    file_name: str = "",
    file_data_base64: str = "",
    csv_text: str = "",
) -> List[List[str]]:
    if csv_text:
        text = str(csv_text)
        if len(text.encode("utf-8")) > SPREADSHEET_MAX_BYTES:
            raise ValueError("file_too_large")
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [[str(cell or "").strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]

    raw_name = str(file_name or "").strip().lower()
    raw_data = str(file_data_base64 or "").strip()
    if not raw_data:
        raise ValueError("file_required")
    if "," in raw_data and raw_data.lower().startswith("data:"):
        raw_data = raw_data.split(",", 1)[1]
    if len(raw_data) > SPREADSHEET_MAX_BASE64_CHARS:
        raise ValueError("file_too_large")
    try:
        data = base64.b64decode(raw_data, validate=True)
    except (ValueError, TypeError) as err:
        raise ValueError("invalid_file_data") from err
    if len(data) > SPREADSHEET_MAX_BYTES:
        raise ValueError("file_too_large")
    if raw_name.endswith(".xlsx") or data[:2] == b"PK":
        return _xlsx_first_sheet_rows(data)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[str(cell or "").strip() for cell in row] for row in csv.reader(io.StringIO(text), dialect)]


spreadsheet_rows_from_payload = _spreadsheet_rows_from_payload
xlsx_workbook_bytes = _xlsx_workbook_bytes
