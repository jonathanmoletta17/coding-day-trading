from pathlib import Path
from tempfile import TemporaryDirectory

from slow_evidence_v1 import evidence_summary
from slow_store_v3 import Store

HOUR = 3_600_000
STRATEGY = "SLOW_TREND_BREAKOUT_V1"


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
        # Hour 0 paired.
        for symbol in ("BTCUSDT", "ETHUSDT"):
            db.record_decision(STRATEGY, symbol, base, "2026-09-17T00:00:00+00:00", ctx(), None)
        # Hour 1 BTC only, and hour 2 paired. Hour 1 becomes a historical unpaired close.
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


def run_all():
    tests = [
        test_empty_is_valid_read_only,
        test_contiguous_paired_decisions_have_full_coverage,
        test_historical_gap_and_unpaired_close_fail_integrity,
        test_latest_unpaired_close_is_reported_but_not_historical_failure,
        test_trade_without_signal_is_detected,
    ]
    for fn in tests:
        fn()
    print(f"SLOW_EVIDENCE_TEST=PASS cases={len(tests)} read_only=true")


if __name__ == "__main__":
    run_all()
