"""Synthetic estate generator (SYNTHETIC_ESTATE). Same seed -> byte-identical outputs.

Nothing here is real. Every output carries `synthetic: true`. Synthetic prices exist only in this
module (AGENTS.md invariant 5) and are labelled synthetic wherever they appear.

Telemetry is generated so that each pattern's mean is exact (seeded noise is de-meaned per pattern
class); the sweep's figures then reproduce the METHODOLOGY golden values on seed 42.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pyarrow as pa
import pyarrow.parquet as pq

from emissiongate.contracts import GroundTruthEntry
from emissiongate.core import energy
from emissiongate.core.factors import Factors
from emissiongate.core.regions import region_time_zone
from emissiongate.estate import terraform as tfw

WINDOW_END = datetime(2026, 10, 1, tzinfo=UTC)
WINDOW_DAYS = 35
HOURS = WINDOW_DAYS * 24
WINDOW_START = WINDOW_END - timedelta(days=WINDOW_DAYS)

# Synthetic list prices (USD). Shaped like public on-demand prices; not quotes. Labelled synthetic.
PRICES_USD_PER_HOUR_SYNTHETIC: dict[str, float] = {
    "g5.xlarge": 1.006,
    "g5.2xlarge": 1.212,
    "g6.xlarge": 0.805,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m7g.large": 0.0816,
    "m7g.xlarge": 0.1632,
    "m7g.2xlarge": 0.3264,
    "c5.2xlarge": 0.34,
    "c5.4xlarge": 0.68,
    "r5.xlarge": 0.252,
    "r5.2xlarge": 0.504,
    "r5.4xlarge": 1.008,
    "t3.medium": 0.0416,
    "db.r5.xlarge": 0.50,
    "db.r5.2xlarge": 1.00,
    "db.r5.4xlarge": 2.00,
}
PRICES_USD_PER_GB_MONTH_SYNTHETIC: dict[str, float] = {
    "gp3": 0.08,
    "STANDARD": 0.023,
    "STANDARD_IA": 0.0125,
    "GLACIER_IR": 0.004,
    "DEEP_ARCHIVE": 0.00099,
}
HOURS_PER_MONTH = 730.0


@dataclass(frozen=True)
class Spec:
    resource_id: str
    kind: str  # ec2_asg | rds | ebs | s3
    region: str
    tags: dict[str, str]
    instance_type: str | None = None
    count: int = 1
    pattern: str = "steady"
    params: dict = field(default_factory=dict)
    storage_gb: float | None = None
    storage_class: str | None = None


SPECS: list[Spec] = [
    Spec(
        "gpu-inference",
        "ec2_asg",
        "us-east-1",
        {"Environment": "staging", "Owner": "ml-platform"},
        "g5.2xlarge",
        4,
        "requests_window",
        {"cpu": 0.05, "gpu": 0.04, "start": 8, "end": 20},
    ),
    Spec(
        "dev-api",
        "ec2_asg",
        "eu-west-2",
        {"Environment": "dev", "Owner": "web"},
        "m5.large",
        12,
        "weekday_hours",
        {"active": 0.30, "idle": 0.02, "start": 9, "end": 19},
    ),
    Spec(
        "legacy-worker",
        "ec2_asg",
        "eu-west-1",
        {"Environment": "prod", "Owner": "data"},
        "m5.2xlarge",
        6,
        "steady",
        {"cpu": 0.60, "amp": 0.05},
    ),
    Spec(
        "reporting-db",
        "rds",
        "us-east-1",
        {"Environment": "prod", "Owner": "finance"},
        "db.r5.4xlarge",
        1,
        "steady",
        {"cpu": 0.05, "amp": 0.0333},
    ),
    Spec(
        "nightly-etl",
        "ec2_asg",
        "eu-west-2",
        {"Environment": "prod", "Owner": "data"},
        "c5.2xlarge",
        4,
        "scheduled_daily",
        {"cpu": 0.80, "start": 2, "end": 4},
    ),
    Spec(
        "orphaned-ebs",
        "ebs",
        "us-east-1",
        {"Environment": "dev", "Owner": "unknown"},
        count=8,
        pattern="storage",
        params={"attached": False, "unattached_days": 60},
        storage_gb=500,
        storage_class="gp3",
    ),
    Spec(
        "prod-api",
        "ec2_asg",
        "eu-west-1",
        {"Environment": "prod", "Owner": "web"},
        "m7g.xlarge",
        4,
        "steady",
        {"cpu": 0.55, "amp": 0.10},
    ),
    Spec(
        "dr-standby",
        "ec2_asg",
        "us-west-2",
        {"Role": "DR", "Environment": "prod"},
        "m5.2xlarge",
        2,
        "steady",
        {"cpu": 0.02, "amp": 0.004},
    ),
    Spec(
        "monthend-close",
        "ec2_asg",
        "eu-west-1",
        {"Environment": "prod", "Owner": "finance"},
        "c5.4xlarge",
        3,
        "monthend",
        {"low": 0.03, "high": 0.90, "days": 3},
    ),
    Spec(
        "compliance-logs",
        "s3",
        "eu-west-2",
        {"Retention": "Regulatory", "Owner": "security", "Environment": "prod"},
        pattern="storage",
        params={"lifecycle": False},
        storage_gb=40 * 1024,
        storage_class="STANDARD",
    ),
]

GROUND_TRUTH: list[GroundTruthEntry] = [
    GroundTruthEntry(
        resource_id="gpu-inference",
        expected="act",
        accepted_interventions=["schedule", "rightsize"],
        trap=False,
        note="idle staging GPU fleet; requests only 08-20 weekdays",
    ),
    GroundTruthEntry(
        resource_id="dev-api",
        expected="act",
        accepted_interventions=["schedule"],
        trap=False,
        note="always-on dev API, busy only in office hours",
    ),
    GroundTruthEntry(
        resource_id="legacy-worker",
        expected="act",
        accepted_interventions=["graviton"],
        trap=False,
        note="steady x86 workers with an arm64 equivalent",
    ),
    GroundTruthEntry(
        resource_id="reporting-db",
        expected="act",
        accepted_interventions=["rightsize"],
        trap=False,
        note="oversized database, CPU avg 5% / p95 8%",
    ),
    GroundTruthEntry(
        resource_id="nightly-etl",
        expected="act",
        accepted_interventions=["time_shift"],
        trap=False,
        note="deferrable nightly batch in eu-west-2",
    ),
    GroundTruthEntry(
        resource_id="orphaned-ebs",
        expected="advisory",
        trap=False,
        note="unattached volumes: decommission is a human decision",
    ),
    GroundTruthEntry(
        resource_id="prod-api",
        expected="refuse",
        trap=False,
        note="already Graviton and well utilised",
    ),
    GroundTruthEntry(
        resource_id="dr-standby",
        expected="refuse",
        trap=True,
        note="DR standby looks idle; protected by Role=DR",
    ),
    GroundTruthEntry(
        resource_id="monthend-close",
        expected="refuse",
        trap=True,
        note="idle 27 days a month, busy at month end; not a weekly pattern",
    ),
    GroundTruthEntry(
        resource_id="compliance-logs",
        expected="refuse_or_tier",
        accepted_interventions=["storage_tier"],
        forbidden=["expiration", "deletion"],
        trap=True,
        note="regulatory retention: tiering allowed, expiry never",
    ),
]


# ---- telemetry ----------------------------------------------------------------------------------


def hours_utc() -> list[datetime]:
    return [WINDOW_START + timedelta(hours=h) for h in range(HOURS)]


def _demeaned(rng: random.Random, n: int, amp: float) -> list[float]:
    noise = [rng.uniform(-amp, amp) for _ in range(n)]
    if not noise:
        return []
    mean = sum(noise) / n
    return [x - mean for x in noise]


def _fill(rng: random.Random, idx: list[int], target: float, amp: float, out: list) -> None:
    for i, x in zip(idx, _demeaned(rng, len(idx), amp), strict=True):
        out[i] = target + x


def telemetry(spec: Spec, rng: random.Random) -> dict:
    times = hours_utc()
    n = len(times)
    p = spec.params
    running: list[int] = [spec.count] * n
    cpu: list[float | None] = [None] * n
    gpu: list[float | None] | None = None
    requests: list[int] | None = None
    if spec.kind in ("ebs", "s3"):
        return {"running": None, "cpu": None, "gpu": None, "requests": None, "meta": dict(p)}
    tz = ZoneInfo(region_time_zone(spec.region))
    local = [t.astimezone(tz) for t in times]
    if spec.pattern == "steady":
        _fill(rng, list(range(n)), p["cpu"], p["amp"], cpu)
    elif spec.pattern == "requests_window":
        _fill(rng, list(range(n)), p["cpu"], p["cpu"] * 0.2, cpu)
        gpu = [None] * n
        _fill(rng, list(range(n)), p["gpu"], p["gpu"] * 0.2, gpu)
        requests = [
            rng.randint(40, 160) if lt.weekday() < 5 and p["start"] <= lt.hour < p["end"] else 0
            for lt in local
        ]
    elif spec.pattern == "weekday_hours":
        active = [
            i for i, lt in enumerate(local) if lt.weekday() < 5 and p["start"] <= lt.hour < p["end"]
        ]
        active_set = set(active)
        idle = [i for i in range(n) if i not in active_set]
        _fill(rng, active, p["active"], p["active"] * 0.2, cpu)
        _fill(rng, idle, p["idle"], p["idle"] * 0.2, cpu)
    elif spec.pattern == "scheduled_daily":
        up = [i for i, lt in enumerate(local) if p["start"] <= lt.hour < p["end"]]
        up_set = set(up)
        running = [spec.count if i in up_set else 0 for i in range(n)]
        _fill(rng, up, p["cpu"], 0.05, cpu)
    elif spec.pattern == "monthend":

        def is_monthend(lt: datetime) -> bool:
            nxt = (lt + timedelta(days=p["days"])).month
            return nxt != lt.month

        high = [i for i, lt in enumerate(local) if is_monthend(lt)]
        high_set = set(high)
        low = [i for i in range(n) if i not in high_set]
        _fill(rng, high, p["high"], 0.05, cpu)
        _fill(rng, low, p["low"], p["low"] * 0.2, cpu)
    else:
        raise ValueError(f"unknown pattern {spec.pattern}")
    return {"running": running, "cpu": cpu, "gpu": gpu, "requests": requests, "meta": {}}


# ---- outputs ------------------------------------------------------------------------------------


def _dump(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, indent=1) + "\n"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cur_rows(spec: Spec, tel: dict) -> list[dict]:
    rows = []
    tags = json.dumps(spec.tags, sort_keys=True)
    for h, t in enumerate(hours_utc()):
        if spec.kind in ("ec2_asg", "rds"):
            amount = float(tel["running"][h])
            assert spec.instance_type
            price = PRICES_USD_PER_HOUR_SYNTHETIC[spec.instance_type]
            product = "AmazonRDS" if spec.kind == "rds" else "AmazonEC2"
            usage_type = (
                f"{'InstanceUsage' if spec.kind == 'rds' else 'BoxUsage'}:{spec.instance_type}"
            )
            cost = amount * price
            itype = spec.instance_type
        else:
            assert spec.storage_gb and spec.storage_class
            amount = spec.storage_gb * spec.count  # GB-hours in this hour
            price = PRICES_USD_PER_GB_MONTH_SYNTHETIC[spec.storage_class]
            product = "AmazonS3" if spec.kind == "s3" else "AmazonEC2"
            usage_type = (
                f"TimedStorage-ByteHrs:{spec.storage_class}"
                if spec.kind == "s3"
                else f"EBS:VolumeUsage.{spec.storage_class}"
            )
            cost = amount * price / HOURS_PER_MONTH
            itype = None
        rows.append(
            {
                "line_item_usage_start_date": t,
                "line_item_resource_id": f"eg-synthetic/{spec.resource_id}",
                "resource_id": spec.resource_id,
                "line_item_product_code": product,
                "product_region": spec.region,
                "product_instance_type": itype,
                "line_item_usage_type": usage_type,
                "line_item_usage_amount": amount,
                "cost_usd_synthetic": cost,
                "resource_tags": tags,
                "storage_class": spec.storage_class,
                "synthetic": True,
            }
        )
    return rows


CUR_SCHEMA = pa.schema(
    [
        ("line_item_usage_start_date", pa.timestamp("us", tz="UTC")),
        ("line_item_resource_id", pa.string()),
        ("resource_id", pa.string()),
        ("line_item_product_code", pa.string()),
        ("product_region", pa.string()),
        ("product_instance_type", pa.string()),
        ("line_item_usage_type", pa.string()),
        ("line_item_usage_amount", pa.float64()),
        ("cost_usd_synthetic", pa.float64()),
        ("resource_tags", pa.string()),
        ("storage_class", pa.string()),
        ("synthetic", pa.bool_()),
    ],
    metadata={"synthetic": "true", "generator": "emissiongate estate"},
)


def _monthly_kwh(spec: Spec, tel: dict, factors: Factors) -> dict[str, float]:
    out: dict[str, float] = {}
    for h, t in enumerate(hours_utc()):
        month = t.strftime("%Y-%m")
        if spec.kind in ("ebs", "s3"):
            assert spec.storage_gb and spec.storage_class
            tb = spec.storage_gb * spec.count / 1024
            kwh = energy.storage(factors, tb, spec.storage_class, hours=1).kwh
        else:
            assert spec.instance_type
            r = tel["running"][h]
            if r == 0:
                continue
            u_gpu = tel["gpu"][h] if tel["gpu"] else 0.0
            kwh = energy.compute(factors, spec.instance_type, tel["cpu"][h], u_gpu, 1, r).kwh
        out[month] = out.get(month, 0.0) + kwh
    return out


def _ccft_csv(
    specs: list[Spec], tels: dict[str, dict], factors: Factors, rng: random.Random
) -> str:
    """CCFT-shaped monthly totals with a seeded bias: exercises reconciliation, not a real check."""
    totals: dict[tuple[str, str], float] = {}
    for spec in specs:
        g = factors.region_g_per_kwh(spec.region).value
        for month, kwh in _monthly_kwh(spec, tels[spec.resource_id], factors).items():
            key = (month, spec.region)
            totals[key] = totals.get(key, 0.0) + energy.kg_co2e(kwh, g)
    lines = ["month,region,kg_co2e,synthetic"]
    for month, region in sorted(totals):
        bias = 1.0 + rng.uniform(-0.08, 0.12)
        lines.append(f"{month},{region},{totals[(month, region)] * bias:.6f},true")
    return "\n".join(lines) + "\n"


def write_terraform(out: Path, versions_tf: Path) -> list[Path]:
    if out.exists():
        for child in out.iterdir():
            if child.name.startswith(".terraform") or child.suffix in (".tf",):
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {
        "versions.tf": versions_tf.read_text(encoding="utf-8"),
        "providers.tf": tfw.providers_tf(sorted({s.region for s in SPECS})),
        "variables.tf": tfw.variables_tf(),
    }
    for spec in SPECS:
        name = tfw.tf_name(spec.resource_id)
        if spec.kind == "ec2_asg":
            assert spec.instance_type
            arch = "arm64" if spec.instance_type.startswith("m7g") else "x86_64"
            if spec.pattern == "scheduled_daily":
                p = spec.params
                tz = region_time_zone(spec.region)
                blocks = tfw.asg_blocks(
                    spec.resource_id,
                    spec.region,
                    spec.instance_type,
                    spec.count,
                    spec.tags,
                    arch,
                    desired=0,
                )
                blocks.append(
                    tfw.schedule_block(
                        spec.resource_id, "up", spec.region, f"0 {p['start']} * * *", tz, spec.count
                    )
                )
                blocks.append(
                    tfw.schedule_block(
                        spec.resource_id, "down", spec.region, f"0 {p['end']} * * *", tz, 0
                    )
                )
            else:
                blocks = tfw.asg_blocks(
                    spec.resource_id, spec.region, spec.instance_type, spec.count, spec.tags, arch
                )
        elif spec.kind == "rds":
            assert spec.instance_type
            blocks = [tfw.rds_block(spec.resource_id, spec.region, spec.instance_type, spec.tags)]
        elif spec.kind == "ebs":
            assert spec.storage_gb and spec.storage_class
            blocks = [
                tfw.ebs_block(
                    spec.resource_id,
                    spec.region,
                    spec.count,
                    int(spec.storage_gb),
                    spec.storage_class,
                    spec.tags,
                )
            ]
        else:
            blocks = [tfw.s3_block(spec.resource_id, spec.region, spec.tags)]
        files[f"{name}.tf"] = tfw.file_text(blocks)
    written = []
    for rel, text in sorted(files.items()):
        path = out / rel
        path.write_text(text, encoding="utf-8", newline="\n")
        written.append(path)
    return written


def generate(
    seed: int,
    data_dir: Path,
    terraform_dir: Path | None,
    versions_tf: Path,
    factors: Factors,
    telemetry_only: bool = False,
) -> dict:
    rng = random.Random(seed)
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "metrics").mkdir(exist_ok=True)
    (data_dir / "cur").mkdir(exist_ok=True)
    (data_dir / "ccft").mkdir(exist_ok=True)
    tels: dict[str, dict] = {}
    rows: list[dict] = []
    outputs: list[tuple[str, Path]] = []
    for spec in SPECS:
        tel = telemetry(spec, rng)
        tels[spec.resource_id] = tel
        doc = {
            "synthetic": True,
            "resource_id": spec.resource_id,
            "start": WINDOW_START.isoformat(),
            "interval_hours": 1,
            "hours": HOURS,
            **tel,
        }
        path = data_dir / "metrics" / f"{spec.resource_id}.json"
        path.write_text(_dump(doc), encoding="utf-8", newline="\n")
        outputs.append((f"metrics/{spec.resource_id}.json", path))
        rows.extend(_cur_rows(spec, tel))
    table = pa.Table.from_pylist(rows, schema=CUR_SCHEMA)
    cur_path = data_dir / "cur" / "usage.parquet"
    pq.write_table(table, cur_path, compression="zstd", write_statistics=False)
    outputs.append(("cur/usage.parquet", cur_path))
    prices = {
        "synthetic": True,
        "note": "Synthetic list prices generated for the demo estate. Not quotes, not real costs.",
        "instance_usd_per_hour_synthetic": PRICES_USD_PER_HOUR_SYNTHETIC,
        "storage_usd_per_gb_month_synthetic": PRICES_USD_PER_GB_MONTH_SYNTHETIC,
        "hours_per_month": HOURS_PER_MONTH,
    }
    path = data_dir / "prices_synthetic.json"
    path.write_text(_dump(prices), encoding="utf-8", newline="\n")
    outputs.append(("prices_synthetic.json", path))
    path = data_dir / "ccft" / "monthly.csv"
    path.write_text(_ccft_csv(SPECS, tels, factors, rng), encoding="utf-8", newline="\n")
    outputs.append(("ccft/monthly.csv", path))
    gt = {"synthetic": True, "seed": seed, "entries": [e.model_dump() for e in GROUND_TRUTH]}
    path = data_dir / "ground_truth.json"
    path.write_text(_dump(gt), encoding="utf-8", newline="\n")
    outputs.append(("ground_truth.json", path))
    if terraform_dir is not None and not telemetry_only:
        for tf in write_terraform(terraform_dir, versions_tf):
            outputs.append((f"estate/{tf.name}", tf))
    manifest = {
        "synthetic": True,
        "seed": seed,
        "window_start": WINDOW_START.isoformat(),
        "window_end": WINDOW_END.isoformat(),
        "files": {rel: _sha256(p) for rel, p in sorted(outputs)},
    }
    (data_dir / "manifest.json").write_text(_dump(manifest), encoding="utf-8", newline="\n")
    return manifest
