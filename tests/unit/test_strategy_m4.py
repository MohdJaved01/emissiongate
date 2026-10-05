"""M4 acceptance on seed 42 (BUILD_PLAN M4 'Done when')."""

import pytest


def test_traps_produce_no_candidates(strategy) -> None:
    _, _, s = strategy
    ids = {c.resource_id for c in s.candidates}
    alt = set(s.alternatives)
    for trap in ("dr-standby", "monthend-close"):
        assert trap not in ids and trap not in alt


def test_compliance_logs_never_gets_expiration(strategy) -> None:
    _, _, s = strategy
    assert all(c.resource_id != "compliance-logs" for c in s.candidates)
    tier = s.valuations["compliance-logs:storage_tier"]
    assert tier.kg_co2e_saved_yr == pytest.approx(0.0, abs=1e-9)
    assert tier.usd_synthetic_saved_yr > 1000  # large synthetic cost saving, ~0 carbon
    assert set(s.verdicts["compliance-logs"].allowed) == {"storage_tier"}
    assert {"expiration", "deletion"} <= set(s.verdicts["compliance-logs"].forbid)


def test_orphaned_ebs_is_a_decommission_advisory(strategy) -> None:
    _, _, s = strategy
    adv = [a for a in s.advisories if a.resource_id == "orphaned-ebs"]
    assert [a.kind for a in adv] == ["decommission"]


def test_dr_standby_blocked_by_tags(strategy) -> None:
    _, _, s = strategy
    adv = next(a for a in s.advisories if a.resource_id == "dr-standby")
    assert adv.kind == "guardrail"
    assert "tag:Role=DR" in adv.blocked_by


def test_carbon_order_differs_from_cost_order(strategy) -> None:
    _, _, s = strategy
    carbon = [c.resource_id for c in sorted(s.candidates, key=lambda c: c.rank_carbon)]
    cost = [c.resource_id for c in sorted(s.candidates, key=lambda c: c.rank_cost)]
    assert carbon == ["gpu-inference", "legacy-worker", "reporting-db", "dev-api"]
    assert carbon != cost


def test_sweep_reproduces_golden_magnitudes(strategy) -> None:
    _, records, s = strategy
    assert records["gpu-inference"].kg_co2e_yr == pytest.approx(401.484, abs=5e-4)
    assert records["legacy-worker"].kg_co2e_yr == pytest.approx(393.593, abs=5e-4)
    assert records["reporting-db"].kg_co2e_yr == pytest.approx(138.794, abs=5e-4)
    assert records["compliance-logs"].kg_co2e_yr == pytest.approx(473.069, abs=5e-4)
    by_id = {c.resource_id: c for c in s.candidates}
    assert by_id["gpu-inference"].kg_co2e_saved_yr == pytest.approx(258.1, abs=0.05)
    assert by_id["legacy-worker"].kg_co2e_saved_yr == pytest.approx(218.630, abs=5e-3)
    assert by_id["reporting-db"].kg_co2e_saved_yr == pytest.approx(96.6246, abs=5e-4)


def test_every_record_has_provenance_and_ledger_event(strategy) -> None:
    _, records, _ = strategy
    for rec in records.values():
        assert rec.ledger_event_id > 0
        tiers = {p.tier for p in rec.provenance}
        assert "annual" in tiers and "vendored" in tiers


def test_monthend_is_not_a_weekly_pattern(strategy) -> None:
    _, _, s = strategy
    u = s.facts["monthend-close"].util
    assert u.cpu_p95 > 0.6
    assert u.mask_coverage == 0.0
