"""Synthetic utilisation series (data/metrics/<resource_id>.json)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def load(metrics_dir: Path, resource_id: str) -> dict | None:
    path = metrics_dir / f"{resource_id}.json"
    if not path.exists():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("synthetic") is not True:
        raise ValueError(f"{path} is not labelled synthetic")
    doc["start"] = datetime.fromisoformat(doc["start"])
    return doc
