from __future__ import annotations

import json
import math

HOUR_MS = 60 * 60 * 1000
DAYS_PER_MONTH = 365.2425 / 12.0


def _finite(value):
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _pace(count: int, observed_days: float):
    if count <= 0 or observed_days <= 0:
        return {"per_day": None, "per_week": None, "per_month": None}
    per_day = count / observed_days
    return {
        "per_day": per_day,
        "per_week": per_day * 7.0,
        "per_month": per_day * DAYS_PER_MONTH,
    }


def _days_to_target(current: int, target: int, per_day: float | None):
    if current >= target:
        return 0.0
    if per_day is None or per_day <= 0:
        return None
    return (target - current) / per_day


def evaluate(gate_result: dict) -> dict:
    """Descriptive information-velocity report from a read-only forward-gate snapshot.

    This is deliberately not a forecast model and never changes strategy state.
    """
    economic = gate_result.get("economic_evidence") or {}
    quality = economic.get("evidence_quality") or {}
    first_ms = quality.get("observation_first_close_ms")
    last_ms = quality.get("observation_last_close_ms")

    observed_hours = None
    observed_days = None
    if first_ms is not None and last_ms is not None and int(last_ms) >= int(first_ms):
        observed_hours = ((int(last_ms) - int(first_ms)) / HOUR_MS) + 1.0
        observed_days = observed_hours / 24.0

    decisions = int(economic.get("decision_events") or 0)
    candidates = int(economic.get("breakout_candidates") or 0)
    trades = int(economic.get("paper_trades_total") or 0)
    closed = int(economic.get("closed_trades") or 0)

    trade_pace = _pace(closed, observed_days or 0.0)
    candidate_pace = _pace(candidates, observed_days or 0.0)
    decision_pace = _pace(decisions, observed_days or 0.0)

    confidence = "NO_RATE_ESTIMATE"
    if closed == 1:
        confidence = "EXTREMELY_LOW_SAMPLE"
    elif 2 <= closed < 10:
        confidence = "VERY_LOW_SAMPLE"
    elif 10 <= closed < 30:
        confidence = "LOW_SAMPLE"
    elif 30 <= closed < 100:
        confidence = "DEVELOPING_SAMPLE"
    elif closed >= 100:
        confidence = "MATURE_COUNT_NOT_STATISTICAL_PROOF"

    per_day = _finite(trade_pace.get("per_day"))
    result = {
        "status": "PASS" if observed_days and observed_days > 0 else "INSUFFICIENT_OBSERVATION_SPAN",
        "version": "INFORMATION_VELOCITY_V1",
        "read_only": True,
        "strategy_mutated": False,
        "real_money_allowed": False,
        "automatic_promotion_supported": False,
        "observation": {
            "first_close_ms": first_ms,
            "last_close_ms": last_ms,
            "observed_hours_inclusive": observed_hours,
            "observed_days_inclusive": observed_days,
        },
        "counts": {
            "decision_events": decisions,
            "breakout_candidates": candidates,
            "paper_trades_total": trades,
            "closed_trades": closed,
        },
        "observed_pace": {
            "closed_trades": trade_pace,
            "breakout_candidates": candidate_pace,
            "decision_events": decision_pace,
        },
        "naive_time_to_sample_at_observed_closed_trade_pace": {
            "time_to_30_trades_days": _days_to_target(closed, 30, per_day),
            "time_to_100_trades_days": _days_to_target(closed, 100, per_day),
        },
        "confidence": confidence,
        "interpretation": {
            "role": "descriptive_information_velocity_only",
            "not_a_forecast": True,
            "do_not_retune_for_sparsity": True,
            "rate_is_path_dependent": True,
            "sample_gate_reference": "PAPER_SCIENTIFIC_GATE_V1 requires 100 closed trades plus independent quality/economic conditions",
        },
    }
    return result


def main() -> None:
    import forward_paper_evidence_gate as gate

    snapshot = gate.refresh_once()
    report = evaluate(snapshot)
    print("FORWARD_PAPER_INFORMATION_VELOCITY=" + json.dumps(report, separators=(",", ":"), ensure_ascii=False))
    if report.get("status") != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
