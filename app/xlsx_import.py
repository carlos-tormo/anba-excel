#!/usr/bin/env python3
import argparse
import datetime as dt
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
import zipfile
from typing import Dict, List, Optional, Tuple

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

TEAM_CODES = [
    "ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DET", "IND", "MIA", "MIL",
    "NYK", "ORL", "PHI", "TOR", "WAS", "DAL", "DEN", "GSW", "HOU", "LAC",
    "LAL", "MEM", "MIN", "NOP", "OKC", "PHX", "POR", "SAC", "SAS", "UTA",
]

SEASONS = [2025, 2026, 2027, 2028, 2029, 2030]


def col_to_num(col: str) -> int:
    value = 0
    for ch in col:
        value = value * 26 + (ord(ch) - 64)
    return value


def parse_ref(ref: str) -> Tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"Invalid cell ref: {ref}")
    return m.group(1), int(m.group(2))


def to_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." not in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def parse_salary_and_option(value: Optional[str]) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    if value is None:
        return None, None, None
    text = str(value).strip()
    if not text:
        return None, None, None
    m = re.search(r"\((TO|PO|QO|GAP)\)\s*$", text, re.IGNORECASE)
    option = m.group(1).upper() if m else None
    clean_text = text[:m.start()].strip() if m else text
    return clean_text, to_float(clean_text), option


class XlsxReader:
    def __init__(self, xlsx_path: str):
        self.xlsx_path = xlsx_path
        self.zf = zipfile.ZipFile(xlsx_path)
        self.shared_strings = self._load_shared_strings()
        self.sheet_targets = self._load_sheet_targets()

    def _load_shared_strings(self) -> List[str]:
        name = "xl/sharedStrings.xml"
        if name not in self.zf.namelist():
            return []
        root = ET.fromstring(self.zf.read(name))
        out: List[str] = []
        for si in root.findall(f"{{{NS_MAIN}}}si"):
            text = "".join(t.text or "" for t in si.iter(f"{{{NS_MAIN}}}t"))
            out.append(text)
        return out

    def _load_sheet_targets(self) -> Dict[str, str]:
        wb = ET.fromstring(self.zf.read("xl/workbook.xml"))
        rels = ET.fromstring(self.zf.read("xl/_rels/workbook.xml.rels"))
        rel_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels.findall(f"{{{NS_PKG_REL}}}Relationship")
        }
        targets: Dict[str, str] = {}
        for sheet in wb.findall(f"{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
            name = sheet.attrib["name"]
            rid = sheet.attrib[f"{{{NS_REL}}}id"]
            target = rel_map[rid]
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            targets[name] = target
        return targets

    def read_cells(self, sheet_name: str) -> Dict[str, str]:
        target = self.sheet_targets.get(sheet_name)
        if not target:
            raise KeyError(f"Sheet not found: {sheet_name}")
        root = ET.fromstring(self.zf.read(target))
        cells: Dict[str, str] = {}
        for c in root.findall(f".//{{{NS_MAIN}}}sheetData/{{{NS_MAIN}}}row/{{{NS_MAIN}}}c"):
            ref = c.attrib.get("r")
            if not ref:
                continue
            t = c.attrib.get("t")
            v = c.find(f"{{{NS_MAIN}}}v")
            if t == "inlineStr":
                text_el = c.find(f"{{{NS_MAIN}}}is/{{{NS_MAIN}}}t")
                if text_el is not None and text_el.text is not None:
                    cells[ref] = text_el.text
                continue
            if v is None or v.text is None:
                continue
            raw = v.text
            if t == "s":
                idx = int(raw)
                cells[ref] = self.shared_strings[idx] if idx < len(self.shared_strings) else raw
            else:
                cells[ref] = raw
        return cells


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        DROP TABLE IF EXISTS assets;
        DROP TABLE IF EXISTS players;
        DROP TABLE IF EXISTS teams;

        CREATE TABLE teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            gm TEXT,
            cash_note TEXT,
            salary_cap REAL NOT NULL,
            luxury_cap REAL NOT NULL,
            first_apron REAL NOT NULL,
            second_apron REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            row_order INTEGER NOT NULL,
            bird_rights TEXT,
            rating TEXT,
            name TEXT NOT NULL,
            position TEXT,
            years_left REAL,
            salary_2025_text TEXT,
            salary_2025_num REAL,
            salary_2026_text TEXT,
            salary_2026_num REAL,
            salary_2027_text TEXT,
            salary_2027_num REAL,
            salary_2028_text TEXT,
            salary_2028_num REAL,
            option_2028 TEXT,
            salary_2029_text TEXT,
            salary_2029_num REAL,
            option_2029 TEXT,
            salary_2030_text TEXT,
            salary_2030_num REAL,
            option_2030 TEXT,
            option_2025 TEXT,
            option_2026 TEXT,
            option_2027 TEXT,
            notes TEXT,
            is_two_way INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
            row_order INTEGER NOT NULL,
            asset_type TEXT NOT NULL,
            year INTEGER,
            label TEXT NOT NULL,
            detail TEXT,
            amount_text TEXT,
            amount_num REAL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def parse_team_header(header: str) -> Tuple[str, Optional[str]]:
    if "- GM:" in header:
        left, right = header.split("- GM:", 1)
        return left.strip(), right.strip() or None
    return header.strip(), None


def upsert_team(conn: sqlite3.Connection, code: str, cells: Dict[str, str]) -> int:
    now = now_iso()
    header = cells.get("A1", code)
    name, gm = parse_team_header(header)

    salary_cap = to_float(cells.get("F60")) or 154_647_000.0
    luxury_cap = to_float(cells.get("F61")) or 187_896_105.0
    first_apron = to_float(cells.get("F62")) or 195_946_000.0
    second_apron = to_float(cells.get("F63")) or 207_825_000.0

    cash_note = cells.get("P3")

    cur = conn.execute(
        """
        INSERT INTO teams (
            code, name, gm, cash_note, salary_cap, luxury_cap, first_apron, second_apron, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (code, name, gm, cash_note, salary_cap, luxury_cap, first_apron, second_apron, now, now),
    )
    return int(cur.lastrowid)


def insert_players(conn: sqlite3.Connection, team_id: int, cells: Dict[str, str]) -> None:
    now = now_iso()

    for row in range(4, 27):
        name = (cells.get(f"D{row}") or "").strip()
        if not name:
            continue

        bird = (cells.get(f"B{row}") or "").strip() or None
        rating = cells.get(f"C{row}")
        pos = (cells.get(f"M{row}") or "").strip() or None
        years_left = to_float(cells.get(f"L{row}"))
        note = cells.get(f"F{row}") if row == 27 else None

        raw_salary_texts = {season: cells.get(f"{chr(70 + idx)}{row}") for idx, season in enumerate(SEASONS)}
        salary_texts = {}
        salary_nums = {}
        salary_opts = {}
        for season in SEASONS:
            t, n, o = parse_salary_and_option(raw_salary_texts[season])
            salary_texts[season] = t
            salary_nums[season] = n
            salary_opts[season] = o

        conn.execute(
            """
            INSERT INTO players (
                team_id, row_order, bird_rights, rating, name, position, years_left,
                salary_2025_text, salary_2025_num,
                salary_2026_text, salary_2026_num,
                salary_2027_text, salary_2027_num,
                salary_2028_text, salary_2028_num,
                salary_2029_text, salary_2029_num,
                salary_2030_text, salary_2030_num,
                option_2025, option_2026, option_2027, option_2028, option_2029, option_2030,
                notes, is_two_way, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                team_id,
                row,
                bird,
                rating,
                name,
                pos,
                years_left,
                salary_texts[2025],
                salary_nums[2025],
                salary_texts[2026],
                salary_nums[2026],
                salary_texts[2027],
                salary_nums[2027],
                salary_texts[2028],
                salary_nums[2028],
                salary_texts[2029],
                salary_nums[2029],
                salary_texts[2030],
                salary_nums[2030],
                salary_opts[2025],
                salary_opts[2026],
                salary_opts[2027],
                salary_opts[2028],
                salary_opts[2029],
                salary_opts[2030],
                note,
                1 if (bird or "").upper() == "TW" else 0,
                now,
                now,
            ),
        )


def insert_dead_cap(conn: sqlite3.Connection, team_id: int, cells: Dict[str, str]) -> None:
    now = now_iso()
    for row in range(29, 33):
        label = (cells.get(f"D{row}") or "").strip()
        amount_text = cells.get(f"F{row}")
        if not label and not amount_text:
            continue
        conn.execute(
            """
            INSERT INTO assets (team_id, row_order, asset_type, year, label, detail, amount_text, amount_num, created_at, updated_at)
            VALUES (?, ?, 'dead_cap', NULL, ?, NULL, ?, ?, ?, ?)
            """,
            (team_id, row, label or f"Dead Cap {row}", amount_text, to_float(amount_text), now, now),
        )


def insert_exceptions(conn: sqlite3.Connection, team_id: int, cells: Dict[str, str]) -> None:
    now = now_iso()
    for row in range(34, 40):
        label = (cells.get(f"D{row}") or "").strip()
        amount_text = cells.get(f"F{row}")
        detail = cells.get(f"I{row}")
        if not label:
            continue
        conn.execute(
            """
            INSERT INTO assets (team_id, row_order, asset_type, year, label, detail, amount_text, amount_num, created_at, updated_at)
            VALUES (?, ?, 'exception', NULL, ?, ?, ?, ?, ?, ?)
            """,
            (team_id, row, label, detail, amount_text, to_float(amount_text), now, now),
        )


def insert_picks(conn: sqlite3.Connection, team_id: int, cells: Dict[str, str]) -> None:
    now = now_iso()
    for row in range(11, 31):
        year = to_float(cells.get(f"N{row}"))
        label = (cells.get(f"O{row}") or "").strip()
        detail = (cells.get(f"P{row}") or "").strip()
        if not year and not label and not detail:
            continue
        merged_label = label or detail or f"Pick {row}"
        extra = detail if label and detail else None
        conn.execute(
            """
            INSERT INTO assets (team_id, row_order, asset_type, year, label, detail, amount_text, amount_num, created_at, updated_at)
            VALUES (?, ?, 'draft_pick', ?, ?, ?, NULL, NULL, ?, ?)
            """,
            (team_id, row, int(year) if year else None, merged_label, extra, now, now),
        )


def import_workbook(xlsx_path: str, db_path: str) -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    create_schema(conn)

    reader = XlsxReader(xlsx_path)
    missing = [c for c in TEAM_CODES if c not in reader.sheet_targets]
    if missing:
        raise RuntimeError(f"Missing team tabs in workbook: {', '.join(missing)}")

    for code in TEAM_CODES:
        cells = reader.read_cells(code)
        team_id = upsert_team(conn, code, cells)
        insert_players(conn, team_id, cells)
        insert_dead_cap(conn, team_id, cells)
        insert_exceptions(conn, team_id, cells)
        insert_picks(conn, team_id, cells)

    conn.commit()
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Import ANBA roster workbook into SQLite")
    parser.add_argument("--xlsx", required=True, help="Path to workbook")
    parser.add_argument("--db", required=True, help="Path to SQLite DB")
    args = parser.parse_args()

    import_workbook(args.xlsx, args.db)
    print(f"Imported workbook into {args.db}")


if __name__ == "__main__":
    main()
