from __future__ import annotations

from collections import Counter
from typing import Iterable


def _int(row, key: str, default: int = 0) -> int:
    if not row or row[key] is None:
        return default
    return int(row[key])


def _scalar(db, sql: str, params: tuple = (), key: str = "n") -> int:
    row = db._exec(sql, params).fetchone()
    return _int(row, key, 0)


def _group_counts(db, field: str, where: str = "", params: tuple = ()) -> dict[str, int]:
    allowed = {"symbol", "state", "trend", "breakout", "action", "side", "outcome"}
    if field not in allowed:
        raise ValueError("UNSUPPORTED_GROUP_FIELD")
    sql = f"SELECT {field} AS k, COUNT(*) AS n FROM decision_events"
    if where:
        sql += " WHERE " + where
    sql += f" GROUP BY {field} ORDER BY {field}"
    rows = db._exec(sql, params).fetchall()
    return {str(r["k"] if r["k"] is not None else "NULL"): int(r["n"]) for r in rows}


def _trade_group_counts(db, field: str) -> dict[str, int]:
    allowed = {"symbol", "side", "outcome"}
    if field not in allowed:
        raise ValueError("UNSUPPORTED_TRADE_GROUP_FIELD")
    rows = db._exec(f"SELECT {field} AS k, COUNT(*) AS n FROM trades GROUP BY {field} ORDER BY {field}").fetchall()
    return {str(r["k"] if r["k"] is not None else "NULL"): int(r["n"]) for r in rows}


def evidence_summary(db, symbols: Iterable[str], hour_ms: int) -> dict:
    """Build a read-only integrity/coverage summary from prospective PAPER state.

    This function deliberately issues SELECT statements only. It is designed to be
    safe to call from observability endpoints without mutating strategy state.
    """
    syms = tuple(symbols)
    if not syms:
        raise ValueError("SYMBOLS_REQUIRED")
    if int(hour_ms) <= 0:
        raise ValueError("HOUR_MS_INVALID")

    per_symbol = {}
    firsts = []
    lasts = []
    for symbol in syms:
        row = db._exec(
            "SELECT COUNT(*) AS n, MIN(close_ms) AS first_ms, MAX(close_ms) AS last_ms "
            "FROM decision_events WHERE symbol=?",
            (symbol,),
        ).fetchone()
        count = _int(row, "n")
        first_ms = int(row["first_ms"]) if row and row["first_ms"] is not None else None
        last_ms = int(row["last_ms"]) if row and row["last_ms"] is not None else None
        expected_slots = 0
        missing_slots = 0
        coverage_ratio = None
        if count and first_ms is not None and last_ms is not None:
            expected_slots = ((last_ms - first_ms) // int(hour_ms)) + 1
            missing_slots = max(0, expected_slots - count)
            coverage_ratio = count / expected_slots if expected_slots else None
            firsts.append(first_ms)
            lasts.append(last_ms)
        per_symbol[symbol] = {
            "decision_events": count,
            "first_close_ms": first_ms,
            "last_close_ms": last_ms,
            "expected_hourly_slots_within_observed_span": expected_slots,
            "missing_hourly_slots_within_observed_span": missing_slots,
            "coverage_ratio_within_observed_span": coverage_ratio,
            "action_counts": _group_counts(db, "action", "symbol=?", (symbol,)),
            "state_counts": _group_counts(db, "state", "symbol=?", (symbol,)),
            "trend_counts": _group_counts(db, "trend", "symbol=?", (symbol,)),
            "breakout_counts": _group_counts(db, "breakout", "symbol=?", (symbol,)),
        }

    total_decisions = _scalar(db, "SELECT COUNT(*) AS n FROM decision_events")
    distinct_closes = _scalar(db, "SELECT COUNT(DISTINCT close_ms) AS n FROM decision_events")
    latest_close = max(lasts) if lasts else None

    unpaired_rows = db._exec(
        "SELECT close_ms, COUNT(DISTINCT symbol) AS n FROM decision_events "
        "GROUP BY close_ms HAVING COUNT(DISTINCT symbol)<>? ORDER BY close_ms",
        (len(syms),),
    ).fetchall()
    unpaired = [int(r["close_ms"]) for r in unpaired_rows]
    historical_unpaired = [x for x in unpaired if latest_close is None or x < latest_close]
    latest_unpaired = [x for x in unpaired if latest_close is not None and x == latest_close]

    actual_symbols = {
        str(r["symbol"])
        for r in db._exec("SELECT DISTINCT symbol FROM decision_events WHERE symbol IS NOT NULL").fetchall()
    }
    unknown_symbols = sorted(actual_symbols.difference(syms))

    trades_missing_signal = _scalar(
        db,
        "SELECT COUNT(*) AS n FROM trades t LEFT JOIN signals s ON s.signal_id=t.signal_id "
        "WHERE t.signal_id IS NOT NULL AND s.signal_id IS NULL",
    )
    signals_total = _scalar(db, "SELECT COUNT(*) AS n FROM signals")
    trades_total = _scalar(db, "SELECT COUNT(*) AS n FROM trades")
    closed_total = _scalar(db, "SELECT COUNT(*) AS n FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL")
    open_total = _scalar(db, "SELECT COUNT(*) AS n FROM trades WHERE outcome='OPEN'")
    signals_without_trade = _scalar(
        db,
        "SELECT COUNT(*) AS n FROM signals s LEFT JOIN trades t ON t.signal_id=s.signal_id WHERE t.signal_id IS NULL",
    )

    counts = [per_symbol[s]["decision_events"] for s in syms]
    balanced = (max(counts) - min(counts) <= 1) if counts else True
    zero_internal_gaps = all(per_symbol[s]["missing_hourly_slots_within_observed_span"] == 0 for s in syms)

    integrity_checks = {
        "known_symbols_only": not unknown_symbols,
        "decision_counts_balanced_within_one": balanced,
        "no_historical_unpaired_decision_closes": not historical_unpaired,
        "no_internal_hourly_gaps_per_symbol": zero_internal_gaps,
        "at_most_one_open_paper_trade": open_total <= 1,
        "all_trades_reference_existing_signals": trades_missing_signal == 0,
    }

    return {
        "read_only": True,
        "symbols_expected": list(syms),
        "unknown_symbols": unknown_symbols,
        "decision_events_total": total_decisions,
        "distinct_decision_closes": distinct_closes,
        "observation_first_close_ms": min(firsts) if firsts else None,
        "observation_last_close_ms": latest_close,
        "per_symbol": per_symbol,
        "unpaired_decision_closes": unpaired,
        "historical_unpaired_decision_closes": historical_unpaired,
        "latest_unpaired_decision_closes": latest_unpaired,
        "signals_total": signals_total,
        "paper_trades_total": trades_total,
        "closed_paper_trades": closed_total,
        "open_paper_trades": open_total,
        "signals_without_trade": signals_without_trade,
        "trades_missing_signal": trades_missing_signal,
        "trade_outcome_counts": _trade_group_counts(db, "outcome"),
        "trade_symbol_counts": _trade_group_counts(db, "symbol"),
        "integrity_checks": integrity_checks,
        "integrity_pass": all(integrity_checks.values()),
        "interpretation": {
            "signals_without_trade": "informational_not_error; slot/reentry/risk gates may legitimately block a candidate",
            "latest_unpaired_decision_closes": "may be transient while the current hourly pair is being written; historical unpaired closes are the fail condition",
            "coverage_ratio": "measures continuity only between each symbol's first and last observed decision close; it does not claim coverage before collection began",
        },
    }
