"""
@category: tool
@impact: low
@description: CLI runner para processamento DSL
"""

import argparse
import dataclasses
import json
import os
import sys
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Deque, Dict, Iterable, Iterator, List, Optional, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.microstructure.dsl_v01 import DSLParserV01, PatternEngineV01
from src.microstructure.context_core import classify_context_core
from src.microstructure.models import BaseEvent, parse_decimal
from src.microstructure.replay import ReplayEngineV01


def _read_json_events(path: str) -> List[BaseEvent]:
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    if raw.startswith("["):
        arr = json.loads(raw)
        if not isinstance(arr, list):
            raise ValueError("events JSON must be an array or JSONL")
        return [BaseEvent.from_json(x) for x in arr]
    out: List[BaseEvent] = []
    for ln in raw.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        out.append(BaseEvent.from_json(json.loads(ln)))
    return out


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _read_params(path: str) -> Dict[str, Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        obj = json.load(f)
    if not isinstance(obj, dict):
        raise ValueError("params JSON must be an object: {pattern_name: {param: value}}")
    return obj  # type: ignore[return-value]


def _parse_tick_sizes(spec: str) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    parts = [p.strip() for p in spec.split(",") if p.strip()]
    for p in parts:
        if "=" not in p:
            raise ValueError("tick-sizes must be instrument=tick_size,...")
        inst, v = p.split("=", 1)
        out[inst.strip()] = parse_decimal(v.strip(), "tick_size")
    return out


def _load_env_file(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith("#") or "=" not in ln:
                continue
            k, v = ln.split("=", 1)
            k = k.strip()
            if k and k not in os.environ:
                os.environ[k] = v.strip()


def _iter_orderbook_snapshots(symbol: str) -> Iterator[Tuple[int, List[List[object]], List[List[object]]]]:
    import psycopg2

    _load_env_file(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    conn = psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )
    cur = conn.cursor(name="ob_stream_cursor")
    cur.itersize = 5000
    cur.execute(
        "SELECT time, bids, asks FROM orderbook_snapshots WHERE symbol=%s ORDER BY time ASC",
        (symbol,),
    )
    try:
        for time_ts, bids, asks in cur:
            if isinstance(time_ts, datetime):
                if time_ts.tzinfo is None:
                    time_ts = time_ts.replace(tzinfo=timezone.utc)
                ts_ms = int(time_ts.timestamp() * 1000)
            else:
                raise ValueError("Unexpected time type from DB")
            yield ts_ms, bids, asks
    finally:
        try:
            cur.close()
        finally:
            conn.close()


def _best_prices(bids: List[List[object]], asks: List[List[object]]) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    if not bids or not asks:
        raise ValueError("Empty bids/asks snapshot")
    bid_price, bid_size = max(bids, key=lambda x: x[0])
    ask_price, ask_size = min(asks, key=lambda x: x[0])
    return Decimal(str(bid_price)), Decimal(str(bid_size)), Decimal(str(ask_price)), Decimal(str(ask_size))


def _infer_tick_size_from_snapshot(bids: List[List[object]], asks: List[List[object]]) -> Decimal:
    prices = [Decimal(str(p)) for p, _ in bids] + [Decimal(str(p)) for p, _ in asks]
    uniq = sorted(set(prices))
    best = None
    for i in range(1, len(uniq)):
        d = uniq[i] - uniq[i - 1]
        if d <= 0:
            continue
        if best is None or d < best:
            best = d
    if best is None:
        raise ValueError("Could not infer tick_size from snapshot prices")
    return best


def _db_base_events_touch(symbol: str, venue: str = "BINANCE", source: str = "depth") -> Iterator[BaseEvent]:
    prev_bid_p: Optional[Decimal] = None
    prev_bid_s: Optional[Decimal] = None
    prev_ask_p: Optional[Decimal] = None
    prev_ask_s: Optional[Decimal] = None

    seq = 0
    for ts_ms, bids, asks in _iter_orderbook_snapshots(symbol):
        seq += 1
        bid_p, bid_s, ask_p, ask_s = _best_prices(bids, asks)

        if prev_bid_p is None:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:SNAP",
                    "event_type": "BOOK_SNAPSHOT",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "bids": [[str(p), str(s)] for p, s in bids],
                    "asks": [[str(p), str(s)] for p, s in asks],
                    "depth_limit": len(bids) if len(bids) == len(asks) else max(len(bids), len(asks)),
                }
            )
            prev_bid_p, prev_bid_s, prev_ask_p, prev_ask_s = bid_p, bid_s, ask_p, ask_s
            continue

        emitted = False
        if prev_bid_p != bid_p:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:BID:CLR",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "BID",
                    "price": str(prev_bid_p),
                    "new_size": "0",
                }
            )
            emitted = True
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:BID:SET",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "BID",
                    "price": str(bid_p),
                    "new_size": str(bid_s),
                }
            )
            emitted = True
        elif prev_bid_s != bid_s:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:BID:UPD",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "BID",
                    "price": str(bid_p),
                    "new_size": str(bid_s),
                }
            )
            emitted = True

        if prev_ask_p != ask_p:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:ASK:CLR",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "ASK",
                    "price": str(prev_ask_p),
                    "new_size": "0",
                }
            )
            emitted = True
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:ASK:SET",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "ASK",
                    "price": str(ask_p),
                    "new_size": str(ask_s),
                }
            )
            emitted = True
        elif prev_ask_s != ask_s:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:ASK:UPD",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "ASK",
                    "price": str(ask_p),
                    "new_size": str(ask_s),
                }
            )
            emitted = True
        if not emitted:
            yield BaseEvent.from_json(
                {
                    "event_id": f"{symbol}:{seq}:BID:NOOP",
                    "event_type": "LEVEL_SET",
                    "instrument_id": symbol,
                    "venue": venue,
                    "source": source,
                    "ts_recv": ts_ms,
                    "ts_event": ts_ms,
                    "source_seq": seq,
                    "side": "BID",
                    "price": str(prev_bid_p),
                    "new_size": str(prev_bid_s),
                }
            )

        prev_bid_p, prev_bid_s, prev_ask_p, prev_ask_s = bid_p, bid_s, ask_p, ask_s


def _state_key(stability: str, liquidity: str, activity: str) -> str:
    return f"{stability}|{liquidity}|{activity}"


def _nested_matrix(stats: Dict[str, Dict[str, object]], field: str) -> Dict[str, Dict[str, Dict[str, object]]]:
    out: Dict[str, Dict[str, Dict[str, object]]] = {}
    for k, v in stats.items():
        stability, liquidity, activity = k.split("|", 2)
        out.setdefault(stability, {}).setdefault(liquidity, {})[activity] = v[field]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="", help="Path to base events JSON (array or JSONL)")
    ap.add_argument("--dsl", default="", help="Path to DSL v0.1 text")
    ap.add_argument("--params", default="", help="Path to JSON parameter bindings")
    ap.add_argument("--tick-sizes", default="", help="instrument_id=tick_size,...")
    ap.add_argument("--enabled-patterns", default="", help="Comma-separated pattern names (default: all)")
    ap.add_argument("--profile", default="trader", help="iniciante|beginner|trader")
    ap.add_argument("--db-symbol", default="", help="Se definido, lê orderbook_snapshots do PostgreSQL")
    args = ap.parse_args()

    if args.db_symbol.strip():
        symbol = args.db_symbol.strip().lower()
        first_ts_ms: Optional[int] = None
        last_ts_ms: Optional[int] = None
        inferred_tick: Optional[Decimal] = None

        snap_iter_for_tick = _iter_orderbook_snapshots(symbol)
        ts_ms, bids, asks = next(snap_iter_for_tick)
        inferred_tick = _infer_tick_size_from_snapshot(bids, asks)
        first_ts_ms = ts_ms

        base_events = _db_base_events_touch(symbol)
        engine = ReplayEngineV01(tick_size_by_instrument={symbol: inferred_tick})

        lookback_ms = 1000
        window: Deque[Tuple[int, bool, bool]] = deque()
        liq_count = 0
        spread_expand_count = 0

        prev_mid: Optional[Decimal] = None
        prev_state: Optional[Tuple[str, str, str, bool]] = None
        cur_seq: Optional[int] = None
        last_post_state = None

        stats_all: Dict[str, Dict[str, object]] = {}
        stats_allowed: Dict[str, Dict[str, object]] = {}

        def _ensure_stat(stats: Dict[str, Dict[str, object]], key: str) -> Dict[str, object]:
            if key not in stats:
                stats[key] = {"n": 0, "sum": Decimal("0"), "equity": Decimal("1"), "peak": Decimal("1"), "mdd": Decimal("0")}
            return stats[key]

        def _apply_return(stats: Dict[str, Dict[str, object]], key: str, r: Decimal) -> None:
            s = _ensure_stat(stats, key)
            s["n"] = int(s["n"]) + 1
            s["sum"] = (s["sum"]) + r  # type: ignore[operator]
            equity = (s["equity"]) * (Decimal("1") + r)  # type: ignore[operator]
            s["equity"] = equity
            peak = s["peak"]  # type: ignore[assignment]
            if equity > peak:
                peak = equity
                s["peak"] = peak
            dd = (equity - peak) / peak
            if dd < (s["mdd"]):  # type: ignore[operator]
                s["mdd"] = dd

        def _mid_from_post_state(post_state) -> Optional[Decimal]:
            try:
                bid = post_state.touch_price("BID")
                ask = post_state.touch_price("ASK")
            except Exception:
                return None
            if bid is None or ask is None:
                return None
            return (bid + ask) / Decimal("2")

        def _finalize_step() -> None:
            nonlocal prev_mid, prev_state
            if last_post_state is None or prev_state is None:
                return
            mid = _mid_from_post_state(last_post_state)
            if mid is None:
                return
            if prev_mid is not None:
                r_long = (mid - prev_mid) / prev_mid
                stability, liquidity, activity, do_not_operate = prev_state
                k = _state_key(stability, liquidity, activity)
                _apply_return(stats_all, k, r_long)
                if not do_not_operate:
                    _apply_return(stats_allowed, k, r_long)
            prev_mid = mid

        for rec in engine.iter_records_ordered(base_events):
            ts = rec.effective_ts()
            if first_ts_ms is None:
                first_ts_ms = ts
            last_ts_ms = ts
            if rec.envelope.source_seq is None:
                continue
            if cur_seq is None:
                cur_seq = int(rec.envelope.source_seq)
            elif int(rec.envelope.source_seq) != cur_seq:
                _finalize_step()
                cur_seq = int(rec.envelope.source_seq)

            is_liq = rec.envelope.event_type in ("LIQUIDITY_ADD", "LIQUIDITY_REMOVE")
            is_spread_expand = False
            if rec.envelope.event_type == "LEVEL_SET":
                pre = rec.pre_state
                post = rec.post_state
                if post.spread_ticks is not None and pre.spread_ticks is not None and post.spread_ticks >= pre.spread_ticks + 1:
                    is_spread_expand = True

            window.append((ts, is_liq, is_spread_expand))
            if is_liq:
                liq_count += 1
            if is_spread_expand:
                spread_expand_count += 1

            window_start = ts - lookback_ms
            while window and window[0][0] < window_start:
                old_ts, old_liq, old_spread = window.popleft()
                if old_liq:
                    liq_count -= 1
                if old_spread:
                    spread_expand_count -= 1
            last_post_state = rec.post_state
            stability = "UNSTABLE" if spread_expand_count > 0 else "STABLE"
            liquidity = "PRESENT" if liq_count > 0 else "ABSENT"
            activity = "EXPANDED" if len(window) >= 20 else "COMPRESSED"
            do_not_operate = False
            if stability == "UNSTABLE":
                do_not_operate = True
            if liquidity == "ABSENT" and stability != "STABLE":
                do_not_operate = True
            prev_state = (stability, liquidity, activity, do_not_operate)

        _finalize_step()

        if first_ts_ms is None or last_ts_ms is None:
            raise ValueError("No snapshots read from DB")

        def _finalize(stats: Dict[str, Dict[str, object]]) -> Dict[str, Dict[str, object]]:
            out_stats: Dict[str, Dict[str, object]] = {}
            for k, v in stats.items():
                n = int(v["n"])
                mean = (v["sum"] / n) if n > 0 else Decimal("0")  # type: ignore[operator]
                out_stats[k] = {
                    "n": n,
                    "mean_return": str(mean),
                    "max_drawdown": str(v["mdd"]),
                }
            return out_stats

        out_all = _finalize(stats_all)
        out_allowed = _finalize(stats_allowed)

        out = {
            "dataset": {
                "source": "postgresql.orderbook_snapshots",
                "symbol": symbol,
                "start_ts_ms": first_ts_ms,
                "end_ts_ms": last_ts_ms,
                "tick_size_inferred": str(inferred_tick),
            },
            "context_v01": {
                "lookback_ms": 1000,
                "decision_logic": [
                    "IF stability == UNSTABLE THEN do_not_operate = true",
                    "IF liquidity == ABSENT AND stability != STABLE THEN do_not_operate = true",
                ],
            },
            "matrices": {
                "all": {
                    "mean_return": _nested_matrix(out_all, "mean_return"),
                    "max_drawdown": _nested_matrix(out_all, "max_drawdown"),
                    "frequency": _nested_matrix(out_all, "n"),
                },
                "allowed_only": {
                    "mean_return": _nested_matrix(out_allowed, "mean_return"),
                    "max_drawdown": _nested_matrix(out_allowed, "max_drawdown"),
                    "frequency": _nested_matrix(out_allowed, "n"),
                },
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    if not (args.events and args.dsl and args.params and args.tick_sizes):
        raise SystemExit("Either --db-symbol or (--events --dsl --params --tick-sizes) must be provided")

    base_events = _read_json_events(args.events)
    dsl_text = _read_text(args.dsl)
    params = _read_params(args.params)
    tick_sizes = _parse_tick_sizes(args.tick_sizes)

    patterns = DSLParserV01().parse(dsl_text)
    replay_result = ReplayEngineV01(tick_size_by_instrument=tick_sizes).replay(base_events)
    records = replay_result.records
    derived_events = replay_result.derived_events

    enabled = [p.strip() for p in args.enabled_patterns.split(",") if p.strip()] or None
    occ = PatternEngineV01(patterns).run(records, pattern_params=params, enabled_patterns=enabled)
    context = classify_context_core(records, occ, lookback_ms=1000, profile=args.profile)

    profile_norm = str(args.profile).strip().lower()
    if profile_norm in ("iniciante", "beginner"):
        include_occurrences = False
    elif profile_norm == "trader":
        include_occurrences = True
    else:
        include_occurrences = True

    out = {
        "derived_events": [
            {**dataclasses.asdict(d.envelope), "parent_event_id": d.parent_event_id, **d.payload} for d in derived_events
        ],
        "pattern_occurrences": (
            [
                {
                    "pattern": o.pattern,
                    "stream_key": list(o.stream_key),
                    "start_ts": o.start_ts,
                    "end_ts": o.end_ts,
                    "emit": o.emit,
                    "evidence_event_ids": o.evidence_event_ids,
                }
                for o in occ
            ]
            if include_occurrences
            else []
        ),
        "context": context,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
