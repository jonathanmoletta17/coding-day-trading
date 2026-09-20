from copy import deepcopy
from io import BytesIO
from urllib.error import HTTPError

import forward_paper_evidence_gate as gate

RELEASE = gate.EXPECTED_RELEASE


def fixtures(decisions=16, candidates=0, trades=0, closed=0, open_position=False):
    ready={"ready":True,"checks":{"BTCUSDT":True,"ETHUSDT":True},"coverage_gap":None,"durable_storage":True,"release_sha":RELEASE,"evidence_integrity_pass":True}
    prospective={"decision_events":decisions,"breakout_candidates":candidates,"paper_trades_total":trades,"closed_trades":closed,"open_position":open_position,
        "wins":0,"losses":closed,"win_rate":0.0 if closed else None,"expectancy_net_R":-0.1 if closed else None,"total_net_R":-0.1*closed if closed else 0.0,
        "profit_factor_net":None,"max_drawdown_R":-0.1*closed if closed else -0.0,"avg_cost_R":0.02 if closed else None,"avg_gross_R":-0.08 if closed else None,
        "realized_pnl":-1.0*closed,"equity":10000.0-closed,"daily_realized_pnl_utc":0.0}
    review={"available":False,"read_only":True,"reason":"NO_CLOSED_PROSPECTIVE_PAPER_TRADE"} if closed==0 else {
        "available":True,"read_only":True,"link_integrity_pass":True,
        "cost_scenarios":{"baseline_6bps":{"net_R":-0.1},"stress_10bps":{"net_R":-0.11},"stress_15bps":{"net_R":-0.12}},
        "links":{"signal_exists":True,"decision_exists_at_signal_close":True,"baseline_6bps_reprice_matches_stored":True}}
    audit={"strategy":"SLOW_TREND_BREAKOUT_V1","mode":"PAPER_STAGING","release_sha":RELEASE,"storage":{"backend":"sqlite","durable":True},
        "risk_controls":{"one_global_position":"database_enforced"},"cost_policy":{"paper_baseline_bps":6.0,"demo_calibration_bps":10.01},"prospective":prospective,
        "cost_sensitivity":{"baseline_6bps":{"closed_trades":closed},"stress_10bps":{"closed_trades":closed},"stress_15bps":{"closed_trades":closed}},
        "latest_closed_trade_review":review}
    costs={"release_sha":RELEASE,"scenarios":audit["cost_sensitivity"]}
    evidence_quality={"read_only":True,"integrity_pass":True,"decision_events_total":decisions,"signals_total":candidates,"paper_trades_total":trades,
        "closed_paper_trades":closed,"open_paper_trades":1 if open_position else 0,"historical_unpaired_decision_closes":[],
        "per_symbol":{"BTCUSDT":{"decision_events":decisions//2},"ETHUSDT":{"decision_events":decisions-decisions//2}}}
    evidence={"strategy":"SLOW_TREND_BREAKOUT_V1","mode":"PAPER_STAGING","release_sha":RELEASE,"evidence_quality":evidence_quality}
    return ready,audit,costs,evidence


def evaluate_fixture(*args,previous=None,**kwargs):
    ready,audit,costs,evidence=fixtures(*args,**kwargs);return gate.evaluate(ready,audit,costs,evidence,previous)


def test_initial_zero_trade_state_passes_operationally():
    out=evaluate_fixture();assert out["status"]=="PASS";assert out["economic_evidence"]["sample_state"]=="NO_CLOSED_PROSPECTIVE_TRADES";assert out["economic_evidence"]["sample_band"]=="N0"
    assert out["economic_evidence"]["evidence_quality"]["integrity_pass"] is True;assert len(out["snapshot_fingerprint_sha256"])==64
    assert out["operational_checks"]["latest_closed_trade_review_matches_sample_state"] is True;assert out["r0"]["status"]=="BLOCKED";assert out["r0"]["real_money_allowed"] is False
    assert out["mutation_performed"] is False;assert out["paper_database_mutated"] is False;assert out["exchange_private_api_used"] is False


def test_sample_bands_are_descriptive_only():
    for n,expected in ((1,"N1_9"),(9,"N1_9"),(10,"N10_29"),(29,"N10_29"),(30,"N30_49"),(49,"N30_49"),(50,"N50_PLUS")):
        out=evaluate_fixture(decisions=50+n,candidates=n,trades=n,closed=n);assert out["status"]=="PASS";assert out["economic_evidence"]["sample_band"]==expected
        assert out["economic_evidence"]["sample_band_role"]=="descriptive_only_not_an_automatic_promotion_threshold";assert out["r0"]["automatic_promotion_supported"] is False


def test_counter_regression_fails_closed():
    previous=evaluate_fixture(decisions=20,candidates=2,trades=1,closed=1);out=evaluate_fixture(decisions=19,candidates=1,trades=0,closed=0,previous=previous)
    assert out["status"]=="FAIL";assert "decision_events:20->19" in out["regression_details"];assert "breakout_candidates:2->1" in out["regression_details"]
    assert "paper_trades_total:1->0" in out["regression_details"];assert "closed_trades:1->0" in out["regression_details"];assert "PROSPECTIVE_COUNTER_REGRESSION_DETECTED" in out["r0"]["block_reasons"]


def test_release_change_does_not_compare_counters_across_release_boundary():
    previous=evaluate_fixture(decisions=20,candidates=2,trades=1,closed=1);ready,audit,costs,evidence=fixtures(decisions=1,candidates=0,trades=0,closed=0)
    audit=deepcopy(audit);ready=deepcopy(ready);costs=deepcopy(costs);evidence=deepcopy(evidence)
    for obj in (audit,ready,costs,evidence):obj["release_sha"]="different-release"
    out=gate.evaluate(ready,audit,costs,evidence,previous);assert out["operational_checks"]["decision_events_monotonic"] is True;assert out["operational_checks"]["release_pinned_across_endpoints"] is False;assert out["status"]=="FAIL"


def test_baseline_mutation_fails_gate():
    ready,audit,costs,evidence=fixtures();audit["cost_policy"]["paper_baseline_bps"]=10.01;out=gate.evaluate(ready,audit,costs,evidence)
    assert out["status"]=="FAIL";assert out["operational_checks"]["baseline_6bps_preserved"] is False;assert out["r0"]["status"]=="BLOCKED"


def test_coverage_gap_fails_gate():
    ready,audit,costs,evidence=fixtures();ready["coverage_gap"]="BTCUSDT gap";out=gate.evaluate(ready,audit,costs,evidence);assert out["status"]=="FAIL";assert out["operational_checks"]["coverage_gap_clear"] is False


def test_evidence_integrity_failure_fails_gate():
    ready,audit,costs,evidence=fixtures();evidence["evidence_quality"]["integrity_pass"]=False;ready["evidence_integrity_pass"]=False;out=gate.evaluate(ready,audit,costs,evidence)
    assert out["status"]=="FAIL";assert out["operational_checks"]["evidence_integrity_pass"] is False;assert "PAPER_EVIDENCE_INTEGRITY_NOT_CLEAN" in out["r0"]["block_reasons"]


def test_cross_endpoint_count_mismatch_fails_gate():
    ready,audit,costs,evidence=fixtures(decisions=18);evidence["evidence_quality"]["decision_events_total"]=16;out=gate.evaluate(ready,audit,costs,evidence)
    assert out["status"]=="FAIL";assert out["operational_checks"]["evidence_decision_count_matches_audit"] is False


def test_open_position_count_parity():
    out=evaluate_fixture(decisions=20,candidates=1,trades=1,closed=0,open_position=True);assert out["status"]=="PASS";assert out["operational_checks"]["evidence_open_count_matches_audit"] is True


def test_closed_trade_requires_clean_linked_review():
    ready,audit,costs,evidence=fixtures(decisions=22,candidates=1,trades=1,closed=1);audit["latest_closed_trade_review"]["link_integrity_pass"]=False
    out=gate.evaluate(ready,audit,costs,evidence);assert out["status"]=="FAIL";assert out["operational_checks"]["latest_closed_trade_review_link_integrity"] is False
    assert "LATEST_CLOSED_TRADE_REVIEW_NOT_CLEAN" in out["r0"]["block_reasons"]


def test_zero_closed_trade_requires_explicit_unavailable_review():
    ready,audit,costs,evidence=fixtures();audit["latest_closed_trade_review"]={"available":True,"read_only":True,"link_integrity_pass":True,"cost_scenarios":{}}
    out=gate.evaluate(ready,audit,costs,evidence);assert out["status"]=="FAIL";assert out["operational_checks"]["latest_closed_trade_review_matches_sample_state"] is False


def test_log_mode_full_on_first_snapshot_or_change():
    out=evaluate_fixture();assert gate.log_mode(out,None,None,1)=="FULL";assert gate.log_mode(out,"different",out["status"],1)=="FULL"


def test_log_mode_silent_for_unchanged_frequent_poll():
    out=evaluate_fixture();fp=out["snapshot_fingerprint_sha256"];assert gate.log_mode(out,fp,out["status"],1)=="NONE"


def test_log_mode_heartbeat_when_unchanged_long_enough():
    out=evaluate_fixture();fp=out["snapshot_fingerprint_sha256"];assert gate.log_mode(out,fp,out["status"],gate.LOG_HEARTBEAT_POLLS)=="HEARTBEAT"


def test_log_mode_full_on_regression():
    previous=evaluate_fixture(decisions=20,candidates=2,trades=1,closed=1);out=evaluate_fixture(decisions=19,candidates=1,trades=0,closed=0,previous=previous)
    assert gate.log_mode(out,out["snapshot_fingerprint_sha256"],out["status"],1)=="FULL"


def test_fetch_preserves_503_response_body(monkeypatch=None):
    error=HTTPError("http://paper/readyz",503,"unavailable",{},BytesIO(b'{"ready":false,"coverage_gap":"ETH gap"}'))
    original=gate.urlopen
    gate.urlopen=lambda *args,**kwargs: (_ for _ in ()).throw(error)
    try:
        try:gate.fetch("/readyz")
        except RuntimeError as exc:
            message=str(exc)
            assert "path=/readyz" in message
            assert "status=503" in message
            assert "coverage_gap" in message
        else:raise AssertionError("fetch should preserve HTTP error context")
    finally:gate.urlopen=original
