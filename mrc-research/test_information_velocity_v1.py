from information_velocity_v1 import evaluate


def sample(closed=1, candidates=2, trades=1, first=0, last=62*60*60*1000):
    return {
        "economic_evidence": {
            "decision_events": 126,
            "breakout_candidates": candidates,
            "paper_trades_total": trades,
            "closed_trades": closed,
            "evidence_quality": {
                "observation_first_close_ms": first,
                "observation_last_close_ms": last,
            },
        }
    }


def test_one_trade_velocity_is_descriptive_and_blocked_from_promotion():
    r = evaluate(sample())
    assert r["status"] == "PASS"
    assert r["read_only"] is True
    assert r["strategy_mutated"] is False
    assert r["real_money_allowed"] is False
    assert r["automatic_promotion_supported"] is False
    assert r["confidence"] == "EXTREMELY_LOW_SAMPLE"
    assert r["observed_pace"]["closed_trades"]["per_week"] > 0
    assert r["naive_time_to_sample_at_observed_closed_trade_pace"]["time_to_30_trades_days"] > 0
    assert r["naive_time_to_sample_at_observed_closed_trade_pace"]["time_to_100_trades_days"] > 0


def test_zero_trades_does_not_invent_a_rate():
    r = evaluate(sample(closed=0, trades=0))
    assert r["observed_pace"]["closed_trades"]["per_week"] is None
    assert r["naive_time_to_sample_at_observed_closed_trade_pace"]["time_to_30_trades_days"] is None
    assert r["confidence"] == "NO_RATE_ESTIMATE"


def test_invalid_span_fails_closed():
    r = evaluate(sample(first=1000, last=999))
    assert r["status"] == "INSUFFICIENT_OBSERVATION_SPAN"
    assert r["real_money_allowed"] is False


def test_target_already_met_returns_zero_days():
    r = evaluate(sample(closed=100, trades=100))
    assert r["naive_time_to_sample_at_observed_closed_trade_pace"]["time_to_30_trades_days"] == 0.0
    assert r["naive_time_to_sample_at_observed_closed_trade_pace"]["time_to_100_trades_days"] == 0.0
