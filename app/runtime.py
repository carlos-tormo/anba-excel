"""Process configuration and static-asset runtime helpers."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
from typing import Iterable


DEFAULT_STATIC_ASSET_FILES = (
    "styles.css", "guest.js", "admin.js", "login.js", "news.js",
)


def static_asset_version(
    web_dir: Path,
    asset_files: Iterable[str] = DEFAULT_STATIC_ASSET_FILES,
) -> str:
    explicit = (
        os.getenv("ASSET_VERSION")
        or os.getenv("RAILWAY_GIT_COMMIT_SHA")
        or os.getenv("GIT_COMMIT_SHA")
        or os.getenv("SOURCE_VERSION")
        or ""
    ).strip()
    if explicit:
        clean = re.sub(r"[^A-Za-z0-9_.-]", "", explicit)[:24]
        if clean:
            return clean

    digest = hashlib.sha256()
    for filename in asset_files:
        path = web_dir / filename
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        digest.update(filename.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return digest.hexdigest()[:12]


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if (value.startswith("'") and value.endswith("'")) or (
            value.startswith('"') and value.endswith('"')
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)
