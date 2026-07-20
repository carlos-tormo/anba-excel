import sqlite3
from pathlib import Path
from typing import Union

from app.db.connection import ClosingSQLiteConnection


PathLike = Union[str, Path]


def connect_test_db(path: PathLike) -> sqlite3.Connection:
    conn = sqlite3.connect(path, factory=ClosingSQLiteConnection)
    conn.row_factory = sqlite3.Row
    return conn
