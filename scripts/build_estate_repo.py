#!/usr/bin/env python3
"""Assemble the `emissiongate-demo-estate` repository contents in a directory (no git operations).

    python scripts/build_estate_repo.py OUT_DIR [--demo-branch-file]

Writes the seed-42 Terraform, README, .gitignore and the gate workflow. With --demo-branch-file it
writes only `gpu_fleet.tf`: the demo PR (2 × g5.2xlarge, us-east-1, no schedule; BUILD_PLAN).
A human commits and pushes; this script never touches git or the network.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

from emissiongate.core import hcl
from emissiongate.core.factors import Factors
from emissiongate.estate import terraform as tfw
from emissiongate.estate.generator import generate

ROOT = Path(__file__).resolve().parents[1]
FLEET_HEADER = (
    "# synthetic: true - demo pull request: a new GPU fleet for a staging experiment, added by\n"
    "# hand with no schedule. EmissionGate's PR gate checks its carbon before merge."
)


def gpu_fleet_tf() -> str:
    blocks = tfw.asg_blocks(
        "gpu-fleet",
        "us-east-1",
        "g5.2xlarge",
        2,
        {"Environment": "staging", "Owner": "ml-platform"},
    )
    return hcl.render_file(blocks, FLEET_HEADER)


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    if "--demo-branch-file" in sys.argv:
        (out / "gpu_fleet.tf").write_text(gpu_fleet_tf(), encoding="utf-8", newline="\n")
        print(out / "gpu_fleet.tf")
        return
    with tempfile.TemporaryDirectory() as tmp:
        generate(42, Path(tmp) / "data", out, ROOT / "tofu" / "versions.tf", Factors.load())
    src = ROOT / "estate-repo"
    for rel in ("README.md", ".gitignore", ".github/workflows/emissiongate-gate.yml"):
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / rel, dest)
    print(f"estate repository contents written to {out}")


if __name__ == "__main__":
    main()
