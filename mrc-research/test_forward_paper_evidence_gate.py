from copy import deepcopy

import forward_paper_evidence_gate as gate

RELEASE = gate.EXPECTED_RELEASE


def fixtures(decisions=16, candidates=0, trades=0, closed=0):
    ready = {
        "ready": True,
        "checks": {"BTCUSDT": True, "ETHUSDT": True},
        "coverage_gap": None,
        "durable_storage": True,
        "release_sha": RELEASE,
    }
    prospective = {
        "decision_events": decisions,
        "breakout_candidates": candidates,
        "paper_trades_total": trades,
        "closed_trades": closed,
        "open_position": False,
        "wins": 0,
        "losses": closed,
        "win_rate": 0.0 if closed else None,
        "expectancy_net_R": -0.1 if closed else None,
        "total_net_R": -0.1 * closed if closed else 0.0,
        "profit_factor_net": None,
        "max_drawdown_R": -0.1 * closed if closed else -0.0,
        "avg_cost_R": 0.02 if closed else None,
        "avg_gross_R": -0.08 if closed else None,
        "realized_pnl": -1.0 * closed,
        "equity": 10000.0 - closed,
        "daily_realized_pnl_utc": 0.0,
    }
    audit = {
        "strategy": "SLOW_TREND_BREAKOUT_V1",
        "mode": "PAPER_STAGING",
        "release_sha": RELEASE,
        "storage": {"backend": "sqlite", "durable": True},
        "risk_controls": {"one_global_position": "database_enforced"},
        "cost_policy": {"paper_baseline_bps": 6.0, "demo_calibration_bps": 10.01},
        "prospective": prospective,
        "cost_sensitivity": {
            "baseline_6bps": {"closed_trades": closed},
            "stress_10bps": {"closed_trades": closed},
            "stress_15bps": {"closed_trades": closed},
        },
    }
    costs = {
        "release_sha": RELEASE,
        "scenarios": audit["cost_sensitivity"],
    }
    return ready, audit, costs


def test_initial_zero_trade_state_passes_operationally():
    ready, audit, costs = fixtures()
    out = gate.evaluate(ready, audit, costs)
    assert out["status"] == "PASS"
    assert out["economic_evidence"]["sample_state"] == "NO_CLOSED_PROSPECTIVE_TRADES"
    assert out["economic_evidence"]["sample_band"] == "N0"
    assert out["r0"]["status"] == "BLOCKED"
    assert out["r0"]["real_money_allowed"] is False
    assert out["mutation_performed"] is False
    assert out["paper_database_mutated"] is False
    assert out["exchange_private_api_used"] is False


def test_sample_bands_are_descriptive_only():
    for n, expected in ((1, "N1_9"), (9, "N1_9"), (10, "N10_29"), (29, "N10_29"), (30, "N30_49"), (49, "N30_49"), (50, "N50_PLUS")):
        ready, audit, costs = fixtures(decisions=50 + n, candidates=n, trades=n, closed=n)
        out = gate.evaluate(ready, audit, costs)
        assert out["status"] == "PASS"
        assert out["economic_evidence"]["sample_band"] == expected
        assert out["economic_evidence"]["sample_band_role"] == "descriptive_only_not_an_automatic_promotion_threshold"
        assert out["r0"]["automatic_promotion_supported"] is False


def test_counter_regression_fails_closed():
    ready, audit, costs = fixtures(decisions=20, candidates=2, trades=1, closed=1)
    previous = gate.evaluate(ready, audit, costs)
    ready2, audit2, costs2 = fixtures(decisions=19, candidates=1, trades=0, closed=0)
    out = gate.evaluate(ready2, audit2, costs2, previous)
    assert out["status"] == "FAIL"
    assert "decision_events:20->19" in out["regression_details"]
    assert "breakout_candidates:2->1" in out["regression_details"]
    assert "paper_trades_total:1->0" in out["regression_details"]
    assert "closed_trades:1->0" in out["regression_details"]
    assert "PROSPECTIVE_COUNTER_REGRESSION_DETECTED" in out["r0"]["block_reasons"]


def test_release_change_does_not_compare_counters_across_release_boundary():
    ready, audit, costs = fixtures(decisions=20, candidates=2, trades=1, closed=1)
    previous = gate.evaluate(ready, audit, costs)
    ready2, audit2, costs2 = fixtures(decisions=1, candidates=0, trades=0, closed=0)
    audit2 = deepcopy(audit2)
    ready2 = deepcopy(ready2)
    costs2 = deepcopy(costs2)
    audit2["release_sha"] = "different-release"
    ready2["release_sha"] = "different-release"
    costs2["release_sha"] = "different-release"
    out = gate.evaluate(ready2, audit2, costs2, previous)
    assert out["operational_checks"]["decision_events_monotonic"] is True
    assert out["operational_checks"]["release_pinned"] is False
    assert out["status"] == "FAIL"


def test_baseline_mutation_fails_gate():
    ready, audit, costs = fixtures()
    audit["cost_policy"]["paper_baseline_bps"] = 10.01
    out = gate.evaluate(ready, audit, costs)
    assert out["status"] == "FAIL"
    assert out["operational_checks"]["baseline_6bps_preserved"] is False
    assert out["r0"]["status"] == "BLOCKED"


def test_coverage_gap_fails_gate():
    ready, audit, costs = fixtures()
    ready["coverage_gap"] = "BTCUSDT gap"
    out = gate.evaluate(ready, audit, costs)
    assert out["status"] == "FAIL"
    assert out["operational_checks"]["coverage_gap_clear"] is False
