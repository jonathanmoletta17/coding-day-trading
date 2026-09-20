from __future__ import annotations

import json
import math
import random
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


def _loads(raw):
    if raw in (None, ""):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return {"parse_error": True, "raw": str(raw)}


def evidence_summary(db, symbols: Iterable[str], hour_ms: int) -> dict:
    """Build a read-only integrity/coverage summary from prospective PAPER state."""
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


def _closed_trade_review(db, trade: dict, cost_scenarios: dict[str, float]) -> dict:
    """Build one read-only trade -> signal -> decision reconstruction."""
    signal_row = db._exec("SELECT * FROM signals WHERE signal_id=?", (trade.get("signal_id"),)).fetchone()
    signal = dict(signal_row) if signal_row else None
    signal_payload = _loads(signal.get("payload")) if signal else None
    signal_ms = int(signal["signal_ms"]) if signal and signal.get("signal_ms") is not None else None

    decision_row = None
    if signal_ms is not None:
        decision_row = db._exec(
            "SELECT * FROM decision_events WHERE symbol=? AND close_ms=? ORDER BY decided_at LIMIT 1",
            (trade.get("symbol"), signal_ms),
        ).fetchone()
    decision = dict(decision_row) if decision_row else None
    decision_payload = _loads(decision.pop("payload", None)) if decision else None

    side_mult = 1.0 if trade.get("side") == "LONG" else -1.0
    entry = float(trade.get("entry") or 0)
    exit_px = float(trade.get("exit") or 0)
    qty = float(trade.get("qty") or 0)
    risk = float(trade.get("risk") or 0)
    gross_pnl = (exit_px - entry) * side_mult * qty
    gross_r = gross_pnl / risk if risk else None

    scenarios = {}
    for name, raw_cost in cost_scenarios.items():
        cost = float(raw_cost)
        modeled_cost = (entry + exit_px) * qty * (cost / 2)
        net_pnl = gross_pnl - modeled_cost
        scenarios[str(name)] = {
            "roundtrip_cost_rate": cost,
            "roundtrip_cost_bps": cost * 10000.0,
            "gross_pnl": gross_pnl,
            "modeled_cost": modeled_cost,
            "net_pnl": net_pnl,
            "gross_R": gross_r,
            "cost_R": modeled_cost / risk if risk else None,
            "net_R": net_pnl / risk if risk else None,
        }

    stored_pnl = float(trade.get("pnl") or 0)
    stored_r = float(trade.get("r_net") or 0)
    baseline = scenarios.get("baseline_6bps")
    baseline_matches_stored = bool(
        baseline is not None
        and abs(float(baseline["net_pnl"]) - stored_pnl) < 1e-8
        and abs(float(baseline["net_R"]) - stored_r) < 1e-8
    )

    links = {
        "signal_exists": signal is not None,
        "decision_exists_at_signal_close": decision is not None,
        "trade_signal_id_matches_signal": bool(signal and trade.get("signal_id") == signal.get("signal_id")),
        "trade_symbol_matches_signal": bool(signal and trade.get("symbol") == signal.get("symbol")),
        "trade_side_matches_signal": bool(signal and trade.get("side") == signal.get("side")),
        "baseline_6bps_reprice_matches_stored": baseline_matches_stored,
    }

    return {
        "available": True,
        "read_only": True,
        "trade": trade,
        "signal": signal,
        "signal_payload": signal_payload,
        "decision": decision,
        "decision_payload": decision_payload,
        "links": links,
        "link_integrity_pass": all(links.values()),
        "cost_scenarios": scenarios,
        "interpretation": {
            "role": "first/latest closed trade reconstruction; descriptive and audit only",
            "parameter_retuning_authorized": False,
            "real_money_promotion_authorized": False,
        },
    }


def latest_closed_trade_review(db, cost_scenarios: dict[str, float]) -> dict:
    """Reconstruct the newest closed PAPER trade from durable linked records, read only."""
    row = db._exec(
        "SELECT * FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL "
        "ORDER BY closed_ms DESC, trade_id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return {
            "available": False,
            "read_only": True,
            "reason": "NO_CLOSED_PROSPECTIVE_PAPER_TRADE",
        }
    return _closed_trade_review(db, dict(row), cost_scenarios)


def closed_trade_reviews(db, cost_scenarios: dict[str, float], limit: int = 200) -> dict:
    """Reconstruct every retained closed PAPER trade without mutating the corpus."""
    bounded_limit = max(1, min(1000, int(limit)))
    rows = db._exec(
        "SELECT * FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL "
        "ORDER BY closed_ms ASC, trade_id ASC LIMIT ?",
        (bounded_limit,),
    ).fetchall()
    items = [_closed_trade_review(db, dict(row), cost_scenarios) for row in rows]
    return {
        "read_only": True,
        "limit": bounded_limit,
        "count": len(items),
        "all_link_integrity_pass": all(item.get("link_integrity_pass") is True for item in items),
        "items": items,
        "interpretation": {
            "role": "complete closed-trade lineage for audit and scientific review",
            "parameter_retuning_authorized": False,
            "real_money_promotion_authorized": False,
        },
    }


def _moving_block_bootstrap_lower(rs: list[float], repetitions: int = 5000) -> dict:
    """Deterministic circular moving-block bootstrap for serially ordered R returns."""
    n = len(rs)
    if not n:
        return {"available": False, "reason": "NO_CLOSED_TRADES"}
    block = 1 if n == 1 else max(2, int(round(math.sqrt(n))))
    rng = random.Random(73190421 + n)
    means = []
    for _ in range(max(1000, int(repetitions))):
        sample = []
        while len(sample) < n:
            start = rng.randrange(n)
            sample.extend(rs[(start + offset) % n] for offset in range(block))
        means.append(sum(sample[:n]) / n)
    means.sort()
    lower_index = max(0, int(math.floor(0.025 * (len(means) - 1))))
    upper_index = min(len(means) - 1, int(math.ceil(0.975 * (len(means) - 1))))
    return {
        "available": True,
        "method": "deterministic_circular_moving_block_percentile",
        "confidence": 0.95,
        "repetitions": len(means),
        "block_length": block,
        "mean_R": sum(rs) / n,
        "lower_95_R": means[lower_index],
        "upper_95_R": means[upper_index],
    }


def scientific_readiness(db, symbols: Iterable[str], hour_ms: int) -> dict:
    """Evaluate the precommitted PAPER evidence floor; never promote automatically."""
    syms = tuple(symbols)
    quality = evidence_summary(db, syms, hour_ms)
    rows = [
        dict(row)
        for row in db._exec(
            "SELECT * FROM trades WHERE outcome!='OPEN' AND closed_ms IS NOT NULL "
            "ORDER BY closed_ms ASC, trade_id ASC"
        ).fetchall()
    ]
    rs = [float(row.get("r_net") or 0.0) for row in rows]
    wins = [value for value in rs if value > 0]
    losses = [value for value in rs if value < 0]
    gross_profit = sum(wins)
    gross_loss = -sum(losses)
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    cumulative = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in rs:
        cumulative += value
        peak = max(peak, cumulative)
        max_drawdown = max(max_drawdown, peak - cumulative)

    first_close = quality.get("observation_first_close_ms")
    last_close = quality.get("observation_last_close_ms")
    observed_days = (
        (int(last_close) - int(first_close)) / 86_400_000.0
        if first_close is not None and last_close is not None
        else 0.0
    )
    by_symbol = {}
    for symbol in syms:
        symbol_rs = [float(row.get("r_net") or 0.0) for row in rows if row.get("symbol") == symbol]
        by_symbol[symbol] = {
            "closed_trades": len(symbol_rs),
            "expectancy_net_R": sum(symbol_rs) / len(symbol_rs) if symbol_rs else None,
        }

    bootstrap = _moving_block_bootstrap_lower(rs)
    pf_ok = bool(gross_profit > 0 and (gross_loss == 0 or float(profit_factor or 0) >= 1.10))
    checks = {
        "closed_trades_gte_100": len(rows) >= 100,
        "decision_events_gte_200": int(quality.get("decision_events_total") or 0) >= 200,
        "observed_days_gte_30": observed_days >= 30.0,
        "expectancy_net_R_positive": bool(rs and (sum(rs) / len(rs)) > 0),
        "bootstrap_lower_95_R_gte_0": bool(bootstrap.get("available") and float(bootstrap.get("lower_95_R") or 0) >= 0),
        "profit_factor_gte_1_10": pf_ok,
        "max_drawdown_lte_10R": max_drawdown <= 10.0,
        "btc_closed_trades_gte_30": by_symbol.get("BTCUSDT", {}).get("closed_trades", 0) >= 30,
        "eth_closed_trades_gte_30": by_symbol.get("ETHUSDT", {}).get("closed_trades", 0) >= 30,
        "btc_expectancy_positive": bool((by_symbol.get("BTCUSDT", {}).get("expectancy_net_R") or 0) > 0),
        "eth_expectancy_positive": bool((by_symbol.get("ETHUSDT", {}).get("expectancy_net_R") or 0) > 0),
        "corpus_integrity_pass": quality.get("integrity_pass") is True,
    }
    evidence_floor_met = all(checks.values())
    return {
        "read_only": True,
        "gate_version": "PAPER_SCIENTIFIC_GATE_V1",
        "precommitted": True,
        "automatic_promotion_supported": False,
        "real_money_allowed": False,
        "status": "ELIGIBLE_FOR_HUMAN_REVIEW" if evidence_floor_met else "INSUFFICIENT_EVIDENCE",
        "evidence_floor_met": evidence_floor_met,
        "checks": checks,
        "metrics": {
            "closed_trades": len(rows),
            "decision_events": int(quality.get("decision_events_total") or 0),
            "observed_days": observed_days,
            "expectancy_net_R": sum(rs) / len(rs) if rs else None,
            "profit_factor_net": profit_factor,
            "max_drawdown_R_abs": max_drawdown,
            "per_symbol": by_symbol,
            "bootstrap": bootstrap,
        },
        "interpretation": {
            "role": "minimum evidence floor for a future human research review",
            "not_a_live_gate": True,
            "parameter_retuning_authorized": False,
            "real_money_promotion_authorized": False,
        },
    }


def signal_reviews(db, limit: int = 100) -> dict:
    """Return durable signal -> decision -> trade links without mutating PAPER state."""
    bounded_limit = max(1, min(1000, int(limit)))
    rows = db._exec(
        "SELECT * FROM signals ORDER BY signal_ms ASC, signal_id ASC LIMIT ?",
        (bounded_limit,),
    ).fetchall()
    items = []
    for raw_signal in rows:
        signal = dict(raw_signal)
        payload = _loads(signal.get("payload"))
        signal_ms = int(signal["signal_ms"]) if signal.get("signal_ms") is not None else None
        decision_row = None
        if signal_ms is not None:
            decision_row = db._exec(
                "SELECT * FROM decision_events WHERE symbol=? AND close_ms=? ORDER BY decided_at LIMIT 1",
                (signal.get("symbol"), signal_ms),
            ).fetchone()
        decision = dict(decision_row) if decision_row else None
        decision_payload = _loads(decision.pop("payload", None)) if decision else None
        trade_row = db._exec(
            "SELECT * FROM trades WHERE signal_id=? ORDER BY opened_ms,trade_id LIMIT 1",
            (signal.get("signal_id"),),
        ).fetchone()
        trade = dict(trade_row) if trade_row else None
        links = {
            "decision_exists_at_signal_close": decision is not None,
            "signal_payload_id_matches": bool(payload and payload.get("signal_id") == signal.get("signal_id")),
            "signal_payload_symbol_matches": bool(payload and payload.get("symbol") == signal.get("symbol")),
            "trade_signal_id_matches": bool(not trade or trade.get("signal_id") == signal.get("signal_id")),
        }
        disposition = "TRADED" if trade else (
            (decision or {}).get("state")
            or (decision or {}).get("action")
            or signal.get("decision")
            or "UNCLASSIFIED"
        )
        items.append({
            "signal": signal,
            "signal_payload": payload,
            "decision": decision,
            "decision_payload": decision_payload,
            "trade": trade,
            "disposition": disposition,
            "links": links,
            "link_integrity_pass": all(links.values()),
        })
    return {
        "read_only": True,
        "limit": bounded_limit,
        "count": len(items),
        "items": items,
        "interpretation": {
            "role": "descriptive signal lineage and blocked-candidate analysis only",
            "parameter_retuning_authorized": False,
            "real_money_promotion_authorized": False,
        },
    }
