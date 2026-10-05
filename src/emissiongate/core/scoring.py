"""Score PR drafts against the ground truth (SYNTHETIC_ESTATE §4)."""

from __future__ import annotations

from emissiongate.contracts import GroundTruthEntry, Score


def score(
    truth: list[GroundTruthEntry],
    prs: list[dict],  # {resource_id, intervention, status, files: {path: text}}
    carbon_order: list[str],
    cost_order: list[str],
) -> Score:
    """TP/FN on `act` entries; FP on anything else; trap violations listed by name."""
    delivered = [p for p in prs if p["status"] in ("drafted", "opened")]
    by_resource: dict[str, list[dict]] = {}
    for p in delivered:
        by_resource.setdefault(p["resource_id"], []).append(p)
    tp = fp = fn = 0
    violations: set[str] = set()
    for t in truth:
        mine = by_resource.get(t.resource_id, [])
        accepted = [p for p in mine if p["intervention"] in t.accepted_interventions]
        text = "\n".join(v for p in mine for v in p.get("files", {}).values())
        forbidden_hit = [f for f in t.forbidden if f in text]
        if t.expected == "act":
            tp += 1 if accepted else 0
            fn += 0 if accepted else 1
            fp += len(mine) - len(accepted)
        elif t.expected == "refuse_or_tier":
            bad = [p for p in mine if p["intervention"] not in t.accepted_interventions]
            fp += len(bad)
            if bad:
                violations.add(f"{t.resource_id}: non-tier PR on a trap")
        else:
            fp += len(mine)
            if mine and t.trap:
                violations.add(f"{t.resource_id}: PR on a trap")
        if forbidden_hit:
            violations.add(f"{t.resource_id}: forbidden {', '.join(forbidden_hit)}")
    return Score(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=tp / (tp + fp) if (tp + fp) else None,
        recall=tp / (tp + fn) if (tp + fn) else None,
        trap_violations=sorted(violations),
        carbon_rank_order=carbon_order,
        cost_rank_order=cost_order,
    )
