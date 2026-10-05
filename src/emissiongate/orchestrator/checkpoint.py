"""checkpoint.json, written before every state transition (atomic replace)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path


def write(run_dir: Path, state: str, data: dict | None = None) -> Path:
    path = run_dir / "checkpoint.json"
    tmp = path.with_suffix(".json.tmp")
    doc = {"state": state, "written_at": datetime.now(UTC).isoformat(), **(data or {})}
    tmp.write_text(json.dumps(doc, indent=1, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read(run_dir: Path) -> dict | None:
    path = run_dir / "checkpoint.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
