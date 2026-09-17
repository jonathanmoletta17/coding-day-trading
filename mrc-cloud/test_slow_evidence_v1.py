import json
from pathlib import Path
from tempfile import TemporaryDirectory

from slow_evidence_v1 import evidence_summary, latest_closed_trade_review
from slow_store_v3 import Store

HOUR = 3_600_000
STRATEGY = "SLOW_TREND_BREAKOUT_V1"
COSTS = {"baseline_6bps": 0.0006, "stress_10bps": 0.0010, "stress_15bps": 0.0015}


def ctx(state="WAIT_BREAKOUT", trend="DOWN", breakout="NONE"):
    return {
        "state": state,
        "trend": trend,
        "breakout": breakout,
        "price": 100.0,
        "ema20_4h": 99.0,
        "ema50_4h": 101.0,
        "don_hi": 105.0,
        "don_lo": 95.0,
        "atr": 2.0,
    }


def counts(db):
    return (
        db.decision_count(),
        db.signal_count(),
        db.trade_count(),
        db.get("sentinel"),
    )


def test_empty_is_valid_read_only():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        db.set("sentinel", "unchanged")
        before = counts(db)
        out = evidence_summary(db, ("BTCUSDT", "ETHUSDT"), HOUR)
        after = counts(db)
        assert before == after
        assert out["read_only"] is True
        assert out["decision_events_total"] == 0
        assert out["integrity_pass"] is True
        assert out["per_symbol"]["BTCUSDT"]["coverage_ratio_within_observed_span"] is None
        db.close_conn()


def test_contiguous_paired_decisions_have_full_coverage():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        base = 1_800_000_000_000
        for i in range(4):
            close_ms = base + i * HOUR
            for symbol in ("BTCUSDT", "ETHUSDT"):
                db.record_decision(STRATEGY, symbol, close_ms, "2026-09-17T00:00:00+00:00", ctx(), None)
        before = counts(db)
        out = evidence_summary(db, ("BTCUSDT", "ETHUSDT"), HOUR)
        after = counts(db)
        assert before == after
        assert out["decision_events_total"] == 8
        assert out["distinct_decision_closes"] == 4
        assert out["historical_unpaired_decision_closes"] == []
        assert out["integrity_pass"] is True
        for symbol in ("BTCUSDT", "ETHUSDT"):
            s = out["per_symbol"][symbol]
            assert s["decision_events"] == 4
            assert s["missing_hourly_slots_within_observed_span"] == 0
            assert s["coverage_ratio_within_observed_span"] == 1.0
        db.close_conn()


def test_historical_gap_and_unpaired_close_fail_integrity():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        base = 1_800_000_000_000
        for symbol in ("BTCUSDT", "ETHUSDT"):
            db.record_decision(STRATEGY, symbol, base, "2026-09-17T00:00:00+00:00", ctx(), None)
        db.record_decision(STRATEGY, "BTCUSDT", base + HOUR, "2026-09-17T01:00:00+00:00", ctx(), None)
        for symbol in ("BTCUSDT", "ETHUSDT"):
            db.record_decision(STRATEGY, symbol, base + 2 * HOUR, "2026-09-17T02:00:00+00:00", ctx(), None)
        out = evidence_summary(db, ("BTCUSDT", "ETHUSDT"), HOUR)
        assert base + HOUR in out["historical_unpaired_decision_closes"]
        assert out["per_symbol"]["ETHUSDT"]["missing_hourly_slots_within_observed_span"] == 1
        assert out["integrity_checks"]["no_historical_unpaired_decision_closes"] is False
        assert out["integrity_checks"]["no_internal_hourly_gaps_per_symbol"] is False
        assert out["integrity_pass"] is False
        db.close_conn()


def test_latest_unpaired_close_is_reported_but_not_historical_failure():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        base = 1_800_000_000_000
        for symbol in ("BTCUSDT", "ETHUSDT"):
            db.record_decision(STRATEGY, symbol, base, "2026-09-17T00:00:00+00:00", ctx(), None)
        db.record_decision(STRATEGY, "BTCUSDT", base + HOUR, "2026-09-17T01:00:00+00:00", ctx(), None)
        out = evidence_summary(db, ("BTCUSDT", "ETHUSDT"), HOUR)
        assert out["latest_unpaired_decision_closes"] == [base + HOUR]
        assert out["historical_unpaired_decision_closes"] == []
        assert out["integrity_checks"]["no_historical_unpaired_decision_closes"] is True
        db.close_conn()


def test_trade_without_signal_is_detected():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        db._exec(
            "INSERT INTO trades(trade_id,signal_id,symbol,side,entry,stop,target,qty,risk,opened_ms,last_check_ms,outcome,pnl,r_net) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("orphan", "missing-signal", "BTCUSDT", "LONG", 100.0, 99.0, 102.0, 1.0, 1.0, 1, 1, "OPEN", 0.0, 0.0),
        )
        db._commit()
        out = evidence_summary(db, ("BTCUSDT", "ETHUSDT"), HOUR)
        assert out["trades_missing_signal"] == 1
        assert out["integrity_checks"]["all_trades_reference_existing_signals"] is False
        assert out["integrity_pass"] is False
        db.close_conn()


def test_latest_closed_trade_review_reports_unavailable_without_closed_trade():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        before = counts(db)
        out = latest_closed_trade_review(db, COSTS)
        after = counts(db)
        assert before == after
        assert out == {
            "available": False,
            "read_only": True,
            "reason": "NO_CLOSED_PROSPECTIVE_PAPER_TRADE",
        }
        db.close_conn()


def test_latest_closed_trade_review_links_signal_decision_and_reprices_costs():
    with TemporaryDirectory() as td:
        db = Store(str(Path(td) / "evidence.sqlite3"))
        signal_ms = 1_800_000_000_000
        signal_id = "sig123"
        signal_payload = {
            "symbol": "BTCUSDT", "signal_id": signal_id, "side": "LONG", "decision": "LONG",
            "signal_ms": signal_ms, "entry": 100.0, "stop": 98.5, "target": 103.0,
            "atr": 1.0, "risk_usdt": 25.0, "qty": 2.0,
        }
        db._exec(
            "INSERT INTO signals(signal_id,symbol,side,decision,signal_ms,payload,created_at) VALUES(?,?,?,?,?,?,?)",
            (signal_id, "BTCUSDT", "LONG", "LONG", signal_ms, json.dumps(signal_payload), "2026-09-17T00:00:01+00:00"),
        )
        decision_ctx = ctx(state="EXECUTABLE", trend="UP", breakout="LONG")
        db.record_decision(STRATEGY, "BTCUSDT", signal_ms, "2026-09-17T00:00:01+00:00", decision_ctx, None, action_override="PAPER_OPEN")
        entry, exit_px, qty, risk = 100.0, 103.0, 2.0, 25.0
        gross = (exit_px - entry) * qty
        baseline_cost = (entry + exit_px) * qty * (0.0006 / 2)
        baseline_pnl = gross - baseline_cost
        baseline_r = baseline_pnl / risk
        db._exec(
            "INSERT INTO trades(trade_id,signal_id,symbol,side,entry,stop,target,qty,risk,opened_ms,last_check_ms,closed_ms,exit,outcome,pnl,r_net) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("slow_sig123", signal_id, "BTCUSDT", "LONG", entry, 98.5, 103.0, qty, risk,
             signal_ms + 1000, signal_ms + 2 * HOUR, signal_ms + 2 * HOUR, exit_px, "TARGET", baseline_pnl, baseline_r),
        )
        db._commit()
        before = counts(db)
        out = latest_closed_trade_review(db, COSTS)
        after = counts(db)
        assert before == after
        assert out["available"] is True
        assert out["read_only"] is True
        assert out["trade"]["trade_id"] == "slow_sig123"
        assert out["signal"]["signal_id"] == signal_id
        assert out["signal_payload"]["entry"] == 100.0
        assert out["decision"]["close_ms"] == signal_ms
        assert out["link_integrity_pass"] is True
        assert out["links"]["baseline_6bps_reprice_matches_stored"] is True
        assert out["cost_scenarios"]["baseline_6bps"]["net_R"] == baseline_r
        assert out["cost_scenarios"]["stress_15bps"]["net_R"] < baseline_r
        assert out["interpretation"]["parameter_retuning_authorized"] is False
        assert out["interpretation"]["real_money_promotion_authorized"] is False
        db.close_conn()


def run_all():
    tests = [
        test_empty_is_valid_read_only,
        test_contiguous_paired_decisions_have_full_coverage,
        test_historical_gap_and_unpaired_close_fail_integrity,
        test_latest_unpaired_close_is_reported_but_not_historical_failure,
        test_trade_without_signal_is_detected,
        test_latest_closed_trade_review_reports_unavailable_without_closed_trade,
        test_latest_closed_trade_review_links_signal_decision_and_reprices_costs,
    ]
    for fn in tests:
        fn()
    print(f"SLOW_EVIDENCE_TEST=PASS cases={len(tests)} read_only=true linked_trade_review=true")


if __name__ == "__main__":
    run_all()
