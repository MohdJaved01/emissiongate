"""CUR-shaped billing via DuckDB (read-only)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import duckdb

QUERY = """
SELECT
    resource_id,
    any_value(line_item_product_code)           AS product_code,
    any_value(product_region)                    AS region,
    any_value(product_instance_type)             AS instance_type,
    any_value(storage_class)                     AS storage_class,
    max(line_item_usage_amount)                  AS max_usage_amount,
    avg(line_item_usage_amount)                  AS avg_usage_amount,
    sum(line_item_usage_amount)                  AS total_usage_amount,
    sum(cost_usd_synthetic)                      AS cost_usd_synthetic,
    count(DISTINCT line_item_usage_start_date)   AS hours,
    any_value(resource_tags)                     AS resource_tags,
    bool_and(synthetic)                          AS synthetic
FROM read_parquet(?)
GROUP BY resource_id
ORDER BY resource_id
"""


@dataclass(frozen=True)
class CurSummary:
    resource_id: str
    product_code: str
    region: str
    instance_type: str | None
    storage_class: str | None
    max_usage_amount: float
    avg_usage_amount: float
    total_usage_amount: float
    cost_usd_synthetic: float
    hours: int
    tags: dict[str, str]
    synthetic: bool


def load(path: Path) -> list[CurSummary]:
    if not path.exists():
        raise FileNotFoundError(f"CUR not found at {path}; run `emissiongate estate` first")
    con = duckdb.connect(":memory:")
    try:
        rows = con.execute(QUERY, [str(path)]).fetchall()
    finally:
        con.close()
    out = []
    for r in rows:
        out.append(
            CurSummary(
                resource_id=r[0],
                product_code=r[1],
                region=r[2],
                instance_type=r[3],
                storage_class=r[4],
                max_usage_amount=float(r[5]),
                avg_usage_amount=float(r[6]),
                total_usage_amount=float(r[7]),
                cost_usd_synthetic=float(r[8]),
                hours=int(r[9]),
                tags=json.loads(r[10]),
                synthetic=bool(r[11]),
            )
        )
    return out
