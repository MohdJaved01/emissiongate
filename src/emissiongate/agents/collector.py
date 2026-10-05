"""Collector: CUR + metrics + Terraform -> ResourceFacts (Resource + Utilisation); read-only."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from emissiongate.agents.context import RunContext
from emissiongate.contracts import Resource, ResourceKind
from emissiongate.core import hcl
from emissiongate.core.interventions import ResourceFacts
from emissiongate.core.utilisation import summarise
from emissiongate.tools import cur, metrics

log = logging.getLogger(__name__)
HOURS_PER_YEAR = 8760.0
GB_PER_TB = 1000.0  # decimal, as in METHODOLOGY G4 (500 GB = 0.5 TB)
TF_KINDS: dict[str, ResourceKind] = {
    "aws_autoscaling_group": "ec2_asg",
    "aws_db_instance": "rds",
    "aws_ebs_volume": "ebs",
    "aws_s3_bucket": "s3",
    "aws_instance": "ec2",
}


@dataclass(frozen=True)
class TfRef:
    file: str
    address: str
    kind: ResourceKind
    schedules: dict


def scan_terraform(estate_dir: Path) -> dict[str, TfRef]:
    refs: dict[str, TfRef] = {}
    for path in sorted(estate_dir.glob("*.tf")):
        text = path.read_text(encoding="utf-8")
        schedules: dict[str, dict] = {}
        for labels in hcl.block_names(text, "resource", "aws_autoscaling_schedule"):
            group = hcl.get_attribute(text, "resource", labels, "autoscaling_group_name") or ""
            asg = group.split(".")[1] if group.count(".") >= 2 else ""
            rec = (hcl.get_attribute(text, "resource", labels, "recurrence") or "").strip('"')
            tz = (hcl.get_attribute(text, "resource", labels, "time_zone") or "").strip('"')
            size = int(hcl.get_attribute(text, "resource", labels, "desired_capacity") or "0")
            entry = schedules.setdefault(asg, {"time_zone": tz})
            entry["up" if size > 0 else "down"] = rec
        for tf_type, kind in TF_KINDS.items():
            for labels in hcl.block_names(text, "resource", tf_type):
                name = labels[1]
                refs[name.replace("_", "-")] = TfRef(
                    file=path.name,
                    address=f"{tf_type}.{name}",
                    kind=kind,
                    schedules=schedules.get(name, {}),
                )
    return refs


def collect(ctx: RunContext) -> tuple[list[ResourceFacts], list[tuple[str, str]]]:
    """Return facts for every resource in scope, plus (resource_id, reason) for skipped ones."""
    th = ctx.policy.thresholds
    cur_path = ctx.data_dir / "cur" / "usage.parquet"
    rows = cur.load(cur_path)
    ctx.ledger.append(
        state=ctx.state,
        kind="tool_call",
        agent="collector",
        tool="cur.load",
        detail={"rows_grouped": len(rows), "path": cur_path.name},
    )
    refs = scan_terraform(ctx.estate_dir)
    ctx.ledger.append(
        state=ctx.state,
        kind="tool_call",
        agent="collector",
        tool="hcl.scan",
        detail={"resources": len(refs)},
    )
    facts: list[ResourceFacts] = []
    skipped: list[tuple[str, str]] = []
    for row in rows:
        ref = refs.get(row.resource_id)
        if not row.synthetic:
            raise ValueError(f"{row.resource_id}: CUR row not labelled synthetic")
        if ref is None:
            skipped.append((row.resource_id, "no Terraform resource found"))
            continue
        tel = metrics.load(ctx.data_dir / "metrics", row.resource_id)
        if tel is None:
            skipped.append((row.resource_id, "no metrics series"))
            ctx.ledger.append(
                state=ctx.state,
                kind="tool_call",
                agent="collector",
                tool="metrics.load",
                detail={"resource_id": row.resource_id, "found": False},
            )
            continue
        is_storage = ref.kind in ("ebs", "s3")
        meta = dict(tel.get("meta") or {})
        meta["schedules"] = ref.schedules
        resource = Resource(
            resource_id=row.resource_id,
            kind=ref.kind,
            region=row.region,
            instance_type=None if is_storage else row.instance_type,
            count=1 if is_storage else int(row.max_usage_amount),
            storage_tb=row.avg_usage_amount / GB_PER_TB if is_storage else None,
            storage_class=row.storage_class if is_storage else None,
            attached=meta.get("attached") if ref.kind == "ebs" else None,
            tags=row.tags,
            tf_file=ref.file,
            tf_address=ref.address,
        )
        util = summarise(
            row.resource_id,
            tel["start"],
            tel.get("running"),
            tel.get("cpu"),
            tel.get("gpu"),
            tel.get("requests"),
            th["lookback_days"],
            th["min_datapoints"],
            th["idle_cpu_p95"],
        )
        hours_yr = None if is_storage else row.total_usage_amount / row.hours * HOURS_PER_YEAR
        facts.append(
            ResourceFacts(
                resource=resource,
                util=util,
                instance_hours_yr=hours_yr,
                cost_usd_synthetic_yr=row.cost_usd_synthetic / row.hours * HOURS_PER_YEAR,
                meta=meta,
            )
        )
        ctx.ledger.append(
            state=ctx.state,
            kind="tool_call",
            agent="collector",
            tool="metrics.load",
            detail={
                "resource_id": row.resource_id,
                "datapoints": util.datapoints,
                "sufficient": util.sufficient,
            },
        )
    return facts, skipped
