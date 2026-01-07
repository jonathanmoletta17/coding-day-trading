"""
@category: tool
@impact: low
@description: CLI runner para processamento DSL
"""

import argparse
import csv
import dataclasses
import json
import os
import sys
import hashlib
import time
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, Iterator, List, Optional, Tuple

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.microstructure.dsl_v01 import DSLParserV01, PatternEngineV01
from src.microstructure.context_core import classify_context_core
from src.microstructure.models import BaseEvent, parse_decimal
from src.microstructure.replay import ReplayEngineV01


def _sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _write_json_out(path: str, obj: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, default=str))
        f.write("\n")


def _base_event_to_json(ev: BaseEvent) -> Dict[str, Any]:
    env = ev.envelope
    out: Dict[str, Any] = {
        "event_id": env.event_id,
        "event_type": env.event_type,
        "instrument_id": env.instrument_id,
        "venue": env.venue,
        "source": env.source,
        "ts_recv": env.ts_recv,
        "ts_event": env.ts_event,
        "source_seq": env.source_seq,
    }
    out.update(ev.payload)
    return out


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


def _iter_jsonl_events(path: str) -> Iterator[BaseEvent]:
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            yield BaseEvent.from_json(json.loads(ln))


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


def _db_connect():
    import psycopg2

    _load_env_file(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    return psycopg2.connect(
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
    )


def _db_list_symbols(limit: int = 50) -> List[str]:
    conn = _db_connect()
    cur = conn.cursor()
    try:
        cur.execute("SELECT DISTINCT symbol FROM orderbook_snapshots ORDER BY symbol ASC LIMIT %s", (limit,))
        return [r[0] for r in cur.fetchall()]
    finally:
        try:
            cur.close()
        finally:
            conn.close()


def _db_symbol_time_bounds_ms(symbol: str) -> Tuple[int, int]:
    conn = _db_connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT MIN(time), MAX(time) FROM orderbook_snapshots WHERE symbol=%s",
            (symbol,),
        )
        row = cur.fetchone()
        if row is None or row[0] is None or row[1] is None:
            raise ValueError(f"No rows for symbol={symbol}")
        t0, t1 = row
        if not isinstance(t0, datetime) or not isinstance(t1, datetime):
            raise ValueError("Unexpected time type from DB")
        if t0.tzinfo is None:
            t0 = t0.replace(tzinfo=timezone.utc)
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=timezone.utc)
        return int(t0.timestamp() * 1000), int(t1.timestamp() * 1000)
    finally:
        try:
            cur.close()
        finally:
            conn.close()


def _iter_orderbook_snapshots(symbol: str) -> Iterator[Tuple[int, List[List[object]], List[List[object]]]]:
    conn = _db_connect()
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


def _iter_orderbook_snapshots_range(
    symbol: str, start_ts_ms: Optional[int], end_ts_ms: Optional[int]
) -> Iterator[Tuple[int, List[List[object]], List[List[object]]]]:
    conn = _db_connect()
    cur = conn.cursor(name="ob_stream_cursor_range")
    cur.itersize = 5000
    if start_ts_ms is None and end_ts_ms is None:
        sql = "SELECT time, bids, asks FROM orderbook_snapshots WHERE symbol=%s ORDER BY time ASC"
        params = (symbol,)
    elif start_ts_ms is not None and end_ts_ms is None:
        sql = "SELECT time, bids, asks FROM orderbook_snapshots WHERE symbol=%s AND time >= to_timestamp(%s/1000.0) ORDER BY time ASC"
        params = (symbol, start_ts_ms)
    elif start_ts_ms is None and end_ts_ms is not None:
        sql = "SELECT time, bids, asks FROM orderbook_snapshots WHERE symbol=%s AND time <= to_timestamp(%s/1000.0) ORDER BY time ASC"
        params = (symbol, end_ts_ms)
    else:
        sql = "SELECT time, bids, asks FROM orderbook_snapshots WHERE symbol=%s AND time >= to_timestamp(%s/1000.0) AND time <= to_timestamp(%s/1000.0) ORDER BY time ASC"
        params = (symbol, start_ts_ms, end_ts_ms)
    cur.execute(sql, params)
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


def _db_base_events_snapshots(symbol: str, venue: str = "BINANCE", source: str = "depth") -> Iterator[BaseEvent]:
    seq = 0
    for ts_ms, bids, asks in _iter_orderbook_snapshots(symbol):
        seq += 1
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


def _db_base_events_snapshots_range(
    symbol: str,
    start_ts_ms: Optional[int],
    end_ts_ms: Optional[int],
    venue: str = "BINANCE",
    source: str = "depth",
) -> Iterator[BaseEvent]:
    seq = 0
    for ts_ms, bids, asks in _iter_orderbook_snapshots_range(symbol, start_ts_ms, end_ts_ms):
        seq += 1
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


def _state_key(stability: str, liquidity: str, activity: str) -> str:
    return f"{stability}|{liquidity}|{activity}"


def _nested_matrix(stats: Dict[str, Dict[str, object]], field: str) -> Dict[str, Dict[str, Dict[str, object]]]:
    out: Dict[str, Dict[str, Dict[str, object]]] = {}
    for k, v in stats.items():
        stability, liquidity, activity = k.split("|", 2)
        out.setdefault(stability, {}).setdefault(liquidity, {})[activity] = v[field]
    return out


@dataclasses.dataclass
class _WindowAgg:
    symbol: str
    window_start_ms: int
    window_end_ms: int
    event_counts: Dict[str, int]
    n_obs: int
    n_mid: int
    spread_sum: Decimal
    spread_count: int
    mid_first: Optional[Decimal]
    mid_last: Optional[Decimal]
    returns_sum: Decimal
    returns_n: int
    equity: Decimal
    peak: Decimal
    max_drawdown: Decimal
    spread_expansion_count: int
    liquidity_present_count: int
    liquidity_vacuum_count: int
    crossed_book_count: int
    critical: List[Dict[str, Any]]

    def mean_return(self) -> Decimal:
        if self.returns_n <= 0:
            return Decimal("0")
        return self.returns_sum / self.returns_n

    def avg_spread(self) -> Optional[Decimal]:
        if self.spread_count <= 0:
            return None
        return self.spread_sum / self.spread_count


class _TopOfBook:
    def __init__(self) -> None:
        import heapq

        self._heapq = heapq
        self.bids: Dict[Decimal, Decimal] = {}
        self.asks: Dict[Decimal, Decimal] = {}
        self._bid_heap: List[Decimal] = []
        self._ask_heap: List[Decimal] = []

    def apply_snapshot(self, bids: List[List[object]], asks: List[List[object]]) -> None:
        self.bids.clear()
        self.asks.clear()
        self._bid_heap.clear()
        self._ask_heap.clear()
        for p, s in bids:
            dp = Decimal(str(p))
            ds = Decimal(str(s))
            if ds <= 0:
                continue
            self.bids[dp] = ds
            self._heapq.heappush(self._bid_heap, -dp)
        for p, s in asks:
            dp = Decimal(str(p))
            ds = Decimal(str(s))
            if ds <= 0:
                continue
            self.asks[dp] = ds
            self._heapq.heappush(self._ask_heap, dp)

    def apply_level_set(self, side: str, price: Decimal, new_size: Decimal) -> None:
        side_u = side.upper()
        if side_u == "BID":
            if new_size <= 0:
                self.bids.pop(price, None)
                return
            self.bids[price] = new_size
            self._heapq.heappush(self._bid_heap, -price)
            return
        if side_u == "ASK":
            if new_size <= 0:
                self.asks.pop(price, None)
                return
            self.asks[price] = new_size
            self._heapq.heappush(self._ask_heap, price)
            return
        raise ValueError(f"Unsupported side: {side}")

    def best_bid(self) -> Optional[Tuple[Decimal, Decimal]]:
        while self._bid_heap:
            p = -self._bid_heap[0]
            s = self.bids.get(p)
            if s is None or s <= 0:
                self._heapq.heappop(self._bid_heap)
                continue
            return p, s
        return None

    def best_ask(self) -> Optional[Tuple[Decimal, Decimal]]:
        while self._ask_heap:
            p = self._ask_heap[0]
            s = self.asks.get(p)
            if s is None or s <= 0:
                self._heapq.heappop(self._ask_heap)
                continue
            return p, s
        return None


def _hour_bucket_start_ms(ts_ms: int) -> int:
    dt = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
    dt0 = dt.replace(minute=0, second=0, microsecond=0)
    return int(dt0.timestamp() * 1000)


def _process_replay_events(
    events: Iterable[BaseEvent],
    *,
    csv_out_path: Optional[str] = None,
) -> Dict[str, Any]:
    @dataclasses.dataclass
    class _StreamState:
        tob: _TopOfBook
        prev_mid: Optional[Decimal]
        prev_spread: Optional[Decimal]
        prev_window_start_ms: Optional[int]
        batch_key: Optional[int]
        batch_ts: Optional[int]
        batch_event_ids: List[str]
        batch_last_event_type: Optional[str]

    windows: Dict[Tuple[str, int], _WindowAgg] = {}
    csv_rows: List[Dict[str, Any]] = []

    global_prev_ts: Optional[int] = None
    first_ts: Optional[int] = None
    last_ts: Optional[int] = None

    streams: Dict[Tuple[str, str, str], _StreamState] = {}

    def _get_agg(symbol: str, ts_ms: int) -> _WindowAgg:
        w0 = _hour_bucket_start_ms(ts_ms)
        key = (symbol, w0)
        agg = windows.get(key)
        if agg is None:
            agg = _WindowAgg(
                symbol=symbol,
                window_start_ms=w0,
                window_end_ms=w0 + 3600_000,
                event_counts={},
                n_obs=0,
                n_mid=0,
                spread_sum=Decimal("0"),
                spread_count=0,
                mid_first=None,
                mid_last=None,
                returns_sum=Decimal("0"),
                returns_n=0,
                equity=Decimal("1"),
                peak=Decimal("1"),
                max_drawdown=Decimal("0"),
                spread_expansion_count=0,
                liquidity_present_count=0,
                liquidity_vacuum_count=0,
                crossed_book_count=0,
                critical=[],
            )
            windows[key] = agg
        return agg

    def _observe(stream_key: Tuple[str, str, str], symbol: str, st: _StreamState) -> None:
        if st.batch_ts is None:
            return
        ts = st.batch_ts
        w0 = _hour_bucket_start_ms(ts)
        if st.prev_window_start_ms != w0:
            st.prev_window_start_ms = w0
            st.prev_mid = None
            st.prev_spread = None
        agg = _get_agg(symbol, ts)

        bb = st.tob.best_bid()
        ba = st.tob.best_ask()
        if bb is None or ba is None:
            agg.liquidity_vacuum_count += 1
            agg.critical.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type,
                    "event_ids": list(st.batch_event_ids),
                    "kind": "liquidity_vacuum",
                }
            )
            csv_rows.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type or "",
                    "mid": "",
                    "spread": "",
                    "event_id": st.batch_event_ids[-1] if st.batch_event_ids else "",
                    "critical_kind": "liquidity_vacuum",
                }
            )
            st.prev_mid = None
            st.prev_spread = None
            return

        best_bid, _ = bb
        best_ask, _ = ba
        if best_ask <= best_bid:
            agg.crossed_book_count += 1
            agg.critical.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type,
                    "event_ids": list(st.batch_event_ids),
                    "kind": "crossed_book",
                    "best_bid": str(best_bid),
                    "best_ask": str(best_ask),
                }
            )
            csv_rows.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type or "",
                    "mid": "",
                    "spread": "",
                    "event_id": st.batch_event_ids[-1] if st.batch_event_ids else "",
                    "critical_kind": "crossed_book",
                }
            )
            st.prev_mid = None
            st.prev_spread = None
            return

        agg.n_mid += 1
        mid = (best_bid + best_ask) / Decimal("2")
        spread = best_ask - best_bid

        agg.liquidity_present_count += 1
        agg.spread_sum += spread
        agg.spread_count += 1
        if agg.mid_first is None:
            agg.mid_first = mid
        agg.mid_last = mid

        if st.prev_spread is not None and spread > st.prev_spread:
            agg.spread_expansion_count += 1
            agg.critical.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type,
                    "event_ids": list(st.batch_event_ids),
                    "kind": "spread_expansion",
                    "spread_prev": str(st.prev_spread),
                    "spread_now": str(spread),
                }
            )
            csv_rows.append(
                {
                    "timestamp_ms": ts,
                    "event_type": st.batch_last_event_type or "",
                    "mid": str(mid),
                    "spread": str(spread),
                    "event_id": st.batch_event_ids[-1] if st.batch_event_ids else "",
                    "critical_kind": "spread_expansion",
                }
            )
        st.prev_spread = spread

        if st.prev_mid is not None and st.prev_mid != 0:
            r = (mid - st.prev_mid) / st.prev_mid
            agg.returns_sum += r
            agg.returns_n += 1
            agg.equity = agg.equity * (Decimal("1") + r)
            if agg.equity > agg.peak:
                agg.peak = agg.equity
            dd = (agg.equity - agg.peak) / agg.peak
            if dd < agg.max_drawdown:
                agg.max_drawdown = dd
        st.prev_mid = mid

    for ev in events:
        env = ev.envelope
        ts = env.effective_ts()
        if global_prev_ts is not None and ts < global_prev_ts:
            raise ValueError(f"Events not ordered by timestamp: {ts} < {global_prev_ts} (event_id={env.event_id})")
        global_prev_ts = ts
        if first_ts is None:
            first_ts = ts
        last_ts = ts

        symbol = env.instrument_id
        agg_for_counts = _get_agg(symbol, ts)
        agg_for_counts.n_obs += 1
        agg_for_counts.event_counts[env.event_type] = agg_for_counts.event_counts.get(env.event_type, 0) + 1

        sk = (env.venue, env.instrument_id, env.source)
        st = streams.get(sk)
        if st is None:
            st = _StreamState(
                tob=_TopOfBook(),
                prev_mid=None,
                prev_spread=None,
                prev_window_start_ms=None,
                batch_key=None,
                batch_ts=None,
                batch_event_ids=[],
                batch_last_event_type=None,
            )
            streams[sk] = st

        batch_key = int(env.source_seq) if env.source_seq is not None else ts
        if st.batch_key is None:
            st.batch_key = batch_key
            st.batch_ts = ts
        elif batch_key != st.batch_key:
            _observe(sk, symbol, st)
            st.batch_key = batch_key
            st.batch_ts = ts
            st.batch_event_ids = []
            st.batch_last_event_type = None

        st.batch_event_ids.append(env.event_id)
        st.batch_last_event_type = env.event_type
        st.batch_ts = ts

        if env.event_type == "BOOK_SNAPSHOT":
            if "bids" not in ev.payload or "asks" not in ev.payload:
                raise ValueError(f"BOOK_SNAPSHOT missing bids/asks (event_id={env.event_id})")
            bids = ev.payload["bids"]
            asks = ev.payload["asks"]
            if not isinstance(bids, list) or not isinstance(asks, list):
                raise ValueError(f"BOOK_SNAPSHOT bids/asks not list (event_id={env.event_id})")
            st.tob.apply_snapshot(bids=bids, asks=asks)
        elif env.event_type == "LEVEL_SET":
            side = str(ev.payload["side"])
            price = Decimal(str(ev.payload["price"]))
            new_size = Decimal(str(ev.payload["new_size"]))
            st.tob.apply_level_set(side=side, price=price, new_size=new_size)

    for sk, st in streams.items():
        _observe(sk, sk[1], st)

    if csv_out_path is not None:
        with open(csv_out_path, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=["timestamp_ms", "event_type", "mid", "spread", "event_id", "critical_kind"],
            )
            w.writeheader()
            for row in csv_rows:
                w.writerow(row)

    if first_ts is None or last_ts is None:
        raise ValueError("No events to process")

    stats_all: Dict[str, Dict[str, object]] = {}

    def _ensure_stat(key: str) -> Dict[str, object]:
        if key not in stats_all:
            stats_all[key] = {"n": 0, "sum": Decimal("0"), "mdd": Decimal("0")}
        return stats_all[key]

    for agg in windows.values():
        stability = "UNSTABLE" if agg.spread_expansion_count > 0 else "STABLE"
        liquidity = "PRESENT" if agg.liquidity_present_count > 0 else "ABSENT"
        activity = "EXPANDED" if agg.n_obs >= 2 else "COMPRESSED"

        k = _state_key(stability, liquidity, activity)
        s = _ensure_stat(k)
        s["n"] = int(s["n"]) + agg.returns_n
        s["sum"] = (s["sum"]) + agg.returns_sum  # type: ignore[operator]
        if agg.max_drawdown < (s["mdd"]):  # type: ignore[operator]
            s["mdd"] = agg.max_drawdown

    out_windows = []
    for (symbol, w0), agg in sorted(windows.items(), key=lambda x: (x[0][0], x[0][1])):
        stability = "UNSTABLE" if agg.spread_expansion_count > 0 else "STABLE"
        liquidity = "PRESENT" if agg.liquidity_present_count > 0 else "ABSENT"
        activity = "EXPANDED" if agg.n_obs >= 2 else "COMPRESSED"
        do_not_operate = stability == "UNSTABLE" or (liquidity == "ABSENT" and stability != "STABLE")

        out_windows.append(
            {
                "symbol": symbol,
                "window_start_ms": agg.window_start_ms,
                "window_end_ms": agg.window_end_ms,
                "context": {
                    "stability": stability,
                    "liquidity": liquidity,
                    "activity": activity,
                    "do_not_operate": bool(do_not_operate),
                },
                "counts": dict(sorted(agg.event_counts.items())),
                "metrics": {
                    "mid_first": str(agg.mid_first) if agg.mid_first is not None else None,
                    "mid_last": str(agg.mid_last) if agg.mid_last is not None else None,
                    "avg_spread": str(agg.avg_spread()) if agg.avg_spread() is not None else None,
                    "mean_return": str(agg.mean_return()),
                    "returns_n": agg.returns_n,
                    "cumulative_return": str(agg.equity - Decimal("1")),
                    "max_drawdown": str(agg.max_drawdown),
                    "spread_expansion_count": agg.spread_expansion_count,
                    "liquidity_vacuum_count": agg.liquidity_vacuum_count,
                    "crossed_book_count": agg.crossed_book_count,
                },
                "critical": agg.critical,
            }
        )

    out_stats: Dict[str, Dict[str, object]] = {}
    for k, v in stats_all.items():
        n = int(v["n"])
        mean = (v["sum"] / n) if n > 0 else Decimal("0")  # type: ignore[operator]
        out_stats[k] = {
            "n": n,
            "mean_return": str(mean),
            "max_drawdown": str(v["mdd"]),
        }

    out = {
        "dataset": {
            "source": "replay_json",
            "start_ts_ms": first_ts,
            "end_ts_ms": last_ts,
            "windowing": "utc_hour",
            "activity_rule": "EXPANDED if events_in_window >= 2, else COMPRESSED",
            "stability_rule": "UNSTABLE if any spread increased within window (resets at window boundary)",
            "returns_rule": "returns computed only when both mids are within the same window",
            "frequency_definition": "matrices.all.frequency counts returns_n (not event count)",
        },
        "windows": out_windows,
        "matrices": {
            "all": {
                "mean_return": _nested_matrix(out_stats, "mean_return"),
                "max_drawdown": _nested_matrix(out_stats, "max_drawdown"),
                "frequency": _nested_matrix(out_stats, "n"),
            }
        },
        "output_sha256": None,
    }
    b = json.dumps(out, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    out["output_sha256"] = _sha256_bytes(b)
    return out


def _validate_replay_and_metrics(
    *,
    replay_path: str,
    metrics_path: Optional[str],
    csv_path: Optional[str],
    stream_jsonl: bool,
) -> Dict[str, Any]:
    def _iter() -> Iterable[BaseEvent]:
        if stream_jsonl:
            return _iter_jsonl_events(replay_path)
        return _read_json_events(replay_path)

    computed = _process_replay_events(_iter(), csv_out_path=None)
    computed["dataset"]["input_file_path"] = os.path.abspath(replay_path)
    computed["dataset"]["input_file_sha256"] = _sha256_file(replay_path)

    windows = computed.get("windows", [])
    if not isinstance(windows, list) or not windows:
        raise ValueError("Saída sem janelas")

    checks: List[Dict[str, Any]] = []

    def _ok(name: str, ok: bool, details: Optional[Dict[str, Any]] = None) -> None:
        out: Dict[str, Any] = {"check": name, "ok": bool(ok)}
        if details:
            out.update(details)
        checks.append(out)

    _ok("input_sha256_present", bool(computed["dataset"].get("input_file_sha256")))
    _ok("output_sha256_present", bool(computed.get("output_sha256")))

    bad_returns = 0
    bad_spread = 0
    stable_with_expansion = 0
    n_windows = len(windows)
    total_events = 0
    total_mid_obs = 0
    total_returns = 0
    total_crit = 0

    for w in windows:
        total_events += int(sum(w["counts"].values()))
        m = w["metrics"]
        n_mid = int(w["counts"].get("BOOK_SNAPSHOT", 0)) + int(w["counts"].get("LEVEL_SET", 0))
        total_mid_obs += n_mid
        total_returns += int(m["returns_n"])
        total_crit += len(w.get("critical", []))
        if int(m["returns_n"]) > max(0, n_mid - 1):
            bad_returns += 1
        sp = m.get("avg_spread")
        if sp is not None and Decimal(sp) < 0:
            bad_spread += 1
        if w["context"]["stability"] == "STABLE":
            if any(c.get("kind") == "spread_expansion" for c in w.get("critical", [])):
                stable_with_expansion += 1

    _ok("returns_n_leq_mid_obs_minus_1_per_window", bad_returns == 0, {"bad_windows": bad_returns, "n_windows": n_windows})
    _ok("avg_spread_non_negative", bad_spread == 0, {"bad_windows": bad_spread, "n_windows": n_windows})
    _ok("stable_has_no_spread_expansion", stable_with_expansion == 0, {"bad_windows": stable_with_expansion, "n_windows": n_windows})

    if csv_path:
        with open(csv_path, "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        crit_index = {}
        for w in windows:
            for c in w.get("critical", []):
                ts = int(c["timestamp_ms"])
                kind = str(c.get("kind", ""))
                ev_ids = c.get("event_ids", [])
                last_id = ev_ids[-1] if isinstance(ev_ids, list) and ev_ids else ""
                crit_index[(ts, kind, last_id)] = True
        missing = 0
        for r in rows:
            ts = int(r["timestamp_ms"])
            kind = str(r["critical_kind"])
            eid = str(r["event_id"])
            if not crit_index.get((ts, kind, eid), False):
                missing += 1
        _ok("csv_rows_match_critical_index", missing == 0, {"csv_rows": len(rows), "missing_rows": missing})

    if metrics_path:
        expected = json.loads(open(metrics_path, "r", encoding="utf-8").read())
        _ok("metrics_file_output_sha256_matches", expected.get("output_sha256") == computed.get("output_sha256"))
        _ok("metrics_file_core_equal_to_recompute", (expected.get("windows") == computed.get("windows")) and (expected.get("matrices") == computed.get("matrices")))
        exp_ds = expected.get("dataset", {}) if isinstance(expected.get("dataset", {}), dict) else {}
        cmp_ds = computed.get("dataset", {}) if isinstance(computed.get("dataset", {}), dict) else {}
        md_ok = True
        if "replay_file_sha256" in exp_ds:
            md_ok = md_ok and (str(exp_ds.get("replay_file_sha256")) == str(cmp_ds.get("input_file_sha256")))
        if "replay_file_path" in exp_ds:
            md_ok = md_ok and (os.path.abspath(str(exp_ds.get("replay_file_path"))) == os.path.abspath(str(cmp_ds.get("input_file_path"))))
        _ok("metrics_file_metadata_consistent_with_replay", bool(md_ok))

    summary = {
        "replay_path": os.path.abspath(replay_path),
        "replay_sha256": computed["dataset"]["input_file_sha256"],
        "metrics_output_sha256": computed["output_sha256"],
        "windows": n_windows,
        "events_total": total_events,
        "mid_obs_total": total_mid_obs,
        "returns_total": total_returns,
        "critical_total": total_crit,
        "checks": checks,
    }
    return summary


def _profile_call(fn, *args, **kwargs) -> Tuple[Dict[str, Any], Any]:
    import cProfile
    import pstats
    import io
    import tracemalloc
    import resource

    tracemalloc.start()
    prof = cProfile.Profile()
    t0 = time.perf_counter()
    cpu0 = time.process_time()
    rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try:
        prof.enable()
        result = fn(*args, **kwargs)
        prof.disable()
    finally:
        cpu1 = time.process_time()
        t1 = time.perf_counter()
        rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        current, peak = tracemalloc.get_traced_memory()
        snap = tracemalloc.take_snapshot()
        tracemalloc.stop()

    s = io.StringIO()
    ps = pstats.Stats(prof, stream=s).strip_dirs().sort_stats("cumtime")
    ps.print_stats(40)
    top_stats = s.getvalue()

    top_alloc = snap.statistics("lineno")[:20]
    alloc = [{"trace": str(st.traceback), "size": st.size, "count": st.count} for st in top_alloc]

    meta = {
        "wall_s": t1 - t0,
        "cpu_s": cpu1 - cpu0,
        "maxrss_kb_before": rss0,
        "maxrss_kb_after": rss1,
        "tracemalloc_current_bytes": current,
        "tracemalloc_peak_bytes": peak,
        "cprofile_top": top_stats,
        "tracemalloc_top": alloc,
    }
    return meta, result


def _split_csv_symbols(s: str) -> List[str]:
    return [p.strip().lower() for p in s.split(",") if p.strip()]


def _workflow_fail_fast(
    *,
    symbols: List[str],
    start_ts_ms: Optional[int],
    end_ts_ms: Optional[int],
    out_dir: str,
) -> Dict[str, Any]:
    os.makedirs(out_dir, exist_ok=True)
    steps: List[Dict[str, Any]] = []

    def _run(cmd: List[str]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        p = subprocess.run(cmd, cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")), capture_output=True, text=True)
        dt = time.perf_counter() - t0
        return {"cmd": cmd, "returncode": p.returncode, "wall_s": dt, "stdout": p.stdout[-2000:], "stderr": p.stderr[-2000:]}

    steps.append(_run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_*.py", "-v"]))
    if steps[-1]["returncode"] != 0:
        return {"ok": False, "steps": steps}

    for sym in symbols:
        replay_path = os.path.join(out_dir, f"context_v01_report_{sym}.json")
        metrics_path = os.path.join(out_dir, f"context_v01_metrics_{sym}.json")
        csv_path = os.path.join(out_dir, f"context_v01_audit_{sym}.csv")
        acceptance_path = os.path.join(out_dir, f"context_v01_acceptance_{sym}.json")

        sym_start = start_ts_ms
        sym_end = end_ts_ms
        if sym_start is None or sym_end is None:
            _min_ms, _max_ms = _db_symbol_time_bounds_ms(sym)
            sym_end = _max_ms
            sym_start = _max_ms - 3600_000

        cmd_metrics = [
            sys.executable,
            os.path.join("tools", "runners", "run_dsl_v01.py"),
            "--db-symbol",
            sym,
            "--replay-out",
            replay_path,
            "--csv-out",
            csv_path,
            "--out",
            metrics_path,
        ]
        if sym_start is not None:
            cmd_metrics += ["--db-start-ts-ms", str(sym_start)]
        if sym_end is not None:
            cmd_metrics += ["--db-end-ts-ms", str(sym_end)]
        steps.append(_run(cmd_metrics))
        if steps[-1]["returncode"] != 0:
            return {"ok": False, "steps": steps}

        cmd_validate = [
            sys.executable,
            os.path.join("tools", "runners", "run_dsl_v01.py"),
            "--validate",
            "--replay-json",
            replay_path,
            "--metrics-json",
            metrics_path,
            "--csv-in",
            csv_path,
            "--out",
            acceptance_path,
        ]
        steps.append(_run(cmd_validate))
        if steps[-1]["returncode"] != 0:
            return {"ok": False, "steps": steps}

    return {"ok": True, "steps": steps}


def _write_jsonl(path: str, lines: List[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for ln in lines:
            f.write(ln)
            f.write("\n")


def _synth_snapshot_event(
    *,
    event_id: str,
    ts_ms: int,
    instrument_id: str = "btcusdt",
    venue: str = "SYNTH",
    source: str = "depth",
    source_seq: int = 1,
    bid_p: str = "100",
    bid_s: str = "10",
    ask_p: str = "101",
    ask_s: str = "10",
) -> str:
    obj = {
        "event_id": event_id,
        "event_type": "BOOK_SNAPSHOT",
        "instrument_id": instrument_id,
        "venue": venue,
        "source": source,
        "ts_recv": ts_ms,
        "ts_event": ts_ms,
        "source_seq": source_seq,
        "bids": [[bid_p, bid_s]],
        "asks": [[ask_p, ask_s]],
        "depth_limit": 1,
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _generate_synthetic(case: str, out_path: str) -> Dict[str, Any]:
    case_norm = case.strip().lower()
    out_path_abs = os.path.abspath(out_path)
    base_ts = 1700000000000
    lines: List[str] = []
    expected_ok = True

    if case_norm == "minimal_1":
        lines.append(_synth_snapshot_event(event_id="s1", ts_ms=base_ts, bid_p="100", ask_p="101"))
    elif case_norm == "gap_large":
        lines.append(_synth_snapshot_event(event_id="s1", ts_ms=base_ts, bid_p="100", ask_p="101"))
        lines.append(_synth_snapshot_event(event_id="s2", ts_ms=base_ts + 6 * 3600_000, bid_p="100", ask_p="101"))
    elif case_norm == "crossed_book":
        lines.append(_synth_snapshot_event(event_id="s1", ts_ms=base_ts, bid_p="101", ask_p="100"))
    elif case_norm == "corrupt_line":
        expected_ok = False
        lines.append(_synth_snapshot_event(event_id="s1", ts_ms=base_ts, bid_p="100", ask_p="101"))
        lines.append("{not-json")
    elif case_norm == "missing_fields":
        expected_ok = False
        obj = {
            "event_id": "s1",
            "event_type": "BOOK_SNAPSHOT",
            "instrument_id": "btcusdt",
            "venue": "SYNTH",
            "source": "depth",
            "ts_recv": base_ts,
            "ts_event": base_ts,
            "source_seq": 1,
            "bids": [["100", "10"]],
        }
        lines.append(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
    else:
        raise ValueError(f"Unknown synthetic case: {case}")

    os.makedirs(os.path.dirname(out_path_abs) or ".", exist_ok=True)
    _write_jsonl(out_path_abs, lines)
    return {"case": case_norm, "out_path": out_path_abs, "expected_ok": expected_ok, "lines": len(lines), "sha256": _sha256_file(out_path_abs)}


def _run_robustness(out_dir: str) -> Dict[str, Any]:
    out_dir_abs = os.path.abspath(out_dir)
    os.makedirs(out_dir_abs, exist_ok=True)
    cases = ["minimal_1", "gap_large", "crossed_book", "corrupt_line", "missing_fields"]
    results: List[Dict[str, Any]] = []
    for c in cases:
        replay_path = os.path.join(out_dir_abs, f"synth_{c}.jsonl")
        meta = _generate_synthetic(c, replay_path)
        metrics_path = os.path.join(out_dir_abs, f"synth_{c}_metrics.json")
        csv_path = os.path.join(out_dir_abs, f"synth_{c}_audit.csv")
        try:
            base_events = _read_json_events(replay_path)
            out = _process_replay_events(base_events, csv_out_path=csv_path)
            out["dataset"]["input_file_path"] = os.path.abspath(replay_path)
            out["dataset"]["input_file_sha256"] = _sha256_file(replay_path)
            _write_json_out(metrics_path, out)
            acceptance = _validate_replay_and_metrics(replay_path=replay_path, metrics_path=metrics_path, csv_path=csv_path)
            ok = all(ch.get("ok") is True for ch in acceptance.get("checks", []))
            results.append({"case": c, "expected_ok": meta["expected_ok"], "ok": ok, "acceptance": acceptance})
        except Exception as e:
            results.append({"case": c, "expected_ok": meta["expected_ok"], "ok": False, "error": repr(e)})
    strict_ok = all((r["ok"] is True) == (r["expected_ok"] is True) for r in results)
    return {"out_dir": out_dir_abs, "strict_ok": bool(strict_ok), "results": results}


def _jsonl_first_last_ts_ms(path: str) -> Tuple[int, int]:
    first: Optional[int] = None
    last: Optional[int] = None
    with open(path, "r", encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            obj = json.loads(ln)
            ts = obj.get("ts_event") or obj.get("ts_recv")
            if ts is None:
                raise ValueError("Missing ts_event/ts_recv in replay")
            ts_i = int(ts)
            first = ts_i if first is None else first
            last = ts_i
    if first is None or last is None:
        raise ValueError("Empty JSONL")
    return first, last


def _benchmark_generate_jsonl(
    *,
    base_jsonl: str,
    out_jsonl: str,
    target_events: int,
    ts_stride_ms: Optional[int],
) -> Dict[str, Any]:
    base_abs = os.path.abspath(base_jsonl)
    out_abs = os.path.abspath(out_jsonl)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)

    base_first, base_last = _jsonl_first_last_ts_ms(base_abs)
    base_span = max(1, base_last - base_first)
    stride = int(ts_stride_ms) if ts_stride_ms is not None else (base_span + 1)

    written = 0
    epoch = 0
    sha = hashlib.sha256()
    t0 = time.perf_counter()
    with open(out_abs, "w", encoding="utf-8") as out_f:
        while written < target_events:
            epoch_offset = epoch * stride
            with open(base_abs, "r", encoding="utf-8") as in_f:
                for ln in in_f:
                    if written >= target_events:
                        break
                    ln = ln.strip()
                    if not ln:
                        continue
                    obj = json.loads(ln)
                    ts = int(obj.get("ts_event") or obj.get("ts_recv"))
                    ts2 = ts + epoch_offset
                    obj["ts_event"] = ts2
                    obj["ts_recv"] = ts2
                    obj["source_seq"] = int(obj.get("source_seq") or 0) + epoch * 10_000_000 + 1
                    obj["event_id"] = f"{obj.get('event_id','e')}::bench:{epoch}:{written+1}"
                    out_ln = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
                    sha.update(out_ln)
                    sha.update(b"\n")
                    out_f.write(out_ln.decode("utf-8"))
                    out_f.write("\n")
                    written += 1
            epoch += 1
    dt = time.perf_counter() - t0
    return {
        "base_jsonl": base_abs,
        "out_jsonl": out_abs,
        "target_events": int(target_events),
        "written": int(written),
        "base_first_ts_ms": base_first,
        "base_last_ts_ms": base_last,
        "stride_ms": stride,
        "sha256": sha.hexdigest(),
        "wall_s": dt,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="", help="Path to base events JSON (array or JSONL)")
    ap.add_argument("--dsl", default="", help="Path to DSL v0.1 text")
    ap.add_argument("--params", default="", help="Path to JSON parameter bindings")
    ap.add_argument("--tick-sizes", default="", help="instrument_id=tick_size,...")
    ap.add_argument("--enabled-patterns", default="", help="Comma-separated pattern names (default: all)")
    ap.add_argument("--profile", default="trader", help="iniciante|beginner|trader")
    ap.add_argument("--db-symbol", default="", help="Se definido, lê orderbook_snapshots do PostgreSQL")
    ap.add_argument("--replay-json", default="", help="Processa arquivo JSON de replay (array ou JSONL)")
    ap.add_argument("--stream-jsonl", action="store_true", help="Faz parsing streaming do replay JSONL")
    ap.add_argument("--csv-out", default="", help="CSV opcional de auditoria de eventos críticos")
    ap.add_argument("--out", default="", help="Caminho opcional para salvar o JSON de saída")
    ap.add_argument("--validate", action="store_true", help="Valida replay/métricas com critérios de aceite")
    ap.add_argument("--metrics-json", default="", help="Arquivo de métricas para comparar (modo --validate)")
    ap.add_argument("--csv-in", default="", help="CSV existente para comparar (modo --validate)")
    ap.add_argument("--perf-profile", action="store_true", help="Gera profiling do processamento (tempo/memória)")
    ap.add_argument("--list-db-symbols", action="store_true", help="Lista símbolos disponíveis no orderbook_snapshots")
    ap.add_argument("--db-bounds", default="", help="Mostra bounds de tempo do símbolo (ms UTC)")
    ap.add_argument("--db-symbols", default="", help="Lista CSV de símbolos para workflow")
    ap.add_argument("--db-start-ts-ms", default="", help="Filtro opcional start_ts_ms para --db-symbol")
    ap.add_argument("--db-end-ts-ms", default="", help="Filtro opcional end_ts_ms para --db-symbol")
    ap.add_argument("--replay-out", default="", help="Caminho do replay JSON gerado no modo --db-symbol")
    ap.add_argument("--workflow", action="store_true", help="Roda testes+pipeline+validate fail-fast")
    ap.add_argument("--workflow-out-dir", default="", help="Diretório de saída do workflow")
    ap.add_argument("--generate-synth", default="", help="Gera dataset sintético (minimal_1|gap_large|crossed_book|corrupt_line|missing_fields)")
    ap.add_argument("--synth-out", default="", help="Caminho de saída do dataset sintético")
    ap.add_argument("--robustness", action="store_true", help="Executa edge cases sintéticos e valida comportamento")
    ap.add_argument("--robustness-out-dir", default="", help="Diretório de saída do relatório de robustez")
    ap.add_argument("--benchmark-generate", action="store_true", help="Gera dataset benchmark por repetição determinística")
    ap.add_argument("--benchmark-base-jsonl", default="", help="Replay base JSONL para repetição")
    ap.add_argument("--benchmark-out-jsonl", default="", help="Caminho do replay benchmark JSONL gerado")
    ap.add_argument("--benchmark-target-events", default="", help="Quantidade alvo de eventos no benchmark")
    ap.add_argument("--benchmark-stride-ms", default="", help="Offset fixo de timestamp por epoch (opcional)")
    args = ap.parse_args()

    if args.list_db_symbols:
        syms = _db_list_symbols()
        print(json.dumps({"symbols": syms}, ensure_ascii=False, indent=2))
        return 0

    if args.db_bounds.strip():
        sym = args.db_bounds.strip().lower()
        mn, mx = _db_symbol_time_bounds_ms(sym)
        print(json.dumps({"symbol": sym, "min_ts_ms": mn, "max_ts_ms": mx}, ensure_ascii=False, indent=2))
        return 0

    if args.generate_synth.strip():
        out_path = args.synth_out.strip()
        if not out_path:
            raise SystemExit("--generate-synth requer --synth-out")
        meta = _generate_synthetic(args.generate_synth.strip(), out_path)
        out_path_json = args.out.strip()
        if out_path_json:
            _write_json_out(out_path_json, meta)
        else:
            print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.robustness:
        out_dir = args.robustness_out_dir.strip() or os.path.abspath(os.path.join(os.getcwd(), "artifacts_robustness"))
        rep = _run_robustness(out_dir)
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, rep)
        else:
            print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.benchmark_generate:
        base = args.benchmark_base_jsonl.strip()
        outp = args.benchmark_out_jsonl.strip()
        tgt = int(args.benchmark_target_events) if str(args.benchmark_target_events).strip() else 0
        stride = int(args.benchmark_stride_ms) if str(args.benchmark_stride_ms).strip() else None
        if not base or not outp or tgt <= 0:
            raise SystemExit("--benchmark-generate requer --benchmark-base-jsonl, --benchmark-out-jsonl, --benchmark-target-events")
        meta = _benchmark_generate_jsonl(base_jsonl=base, out_jsonl=outp, target_events=tgt, ts_stride_ms=stride)
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, meta)
        else:
            print(json.dumps(meta, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.validate:
        replay_path = args.replay_json.strip()
        if not replay_path:
            raise SystemExit("--validate requer --replay-json")
        metrics_path = args.metrics_json.strip() or None
        csv_in = args.csv_in.strip() or None
        summary = _validate_replay_and_metrics(
            replay_path=replay_path,
            metrics_path=metrics_path,
            csv_path=csv_in,
            stream_jsonl=bool(args.stream_jsonl),
        )
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, summary)
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.replay_json.strip():
        csv_out = args.csv_out.strip() or None
        replay_path = args.replay_json.strip()
        base_events: Iterable[BaseEvent]
        if args.stream_jsonl:
            base_events = _iter_jsonl_events(replay_path)
        else:
            base_events = _read_json_events(replay_path)
        if args.perf_profile:
            prof, out = _profile_call(_process_replay_events, base_events, csv_out_path=csv_out)
            out["profile"] = prof
        else:
            out = _process_replay_events(base_events, csv_out_path=csv_out)
        out["dataset"]["input_file_path"] = os.path.abspath(replay_path)
        out["dataset"]["input_file_sha256"] = _sha256_file(replay_path)
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, out)
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.db_symbol.strip():
        symbol = args.db_symbol.strip().lower()
        inferred_tick: Optional[Decimal] = None

        start_ts_ms = int(args.db_start_ts_ms) if str(args.db_start_ts_ms).strip() else None
        end_ts_ms = int(args.db_end_ts_ms) if str(args.db_end_ts_ms).strip() else None

        snap_iter_for_tick = _iter_orderbook_snapshots(symbol)
        ts_ms, bids, asks = next(snap_iter_for_tick)
        inferred_tick = _infer_tick_size_from_snapshot(bids, asks)

        replay_path = os.path.abspath(args.replay_out.strip()) if args.replay_out.strip() else os.path.abspath(f"context_v01_report_{symbol}.json")
        sha = hashlib.sha256()
        csv_out = args.csv_out.strip() or None

        def _iter_and_export() -> Iterator[BaseEvent]:
            with open(replay_path, "w", encoding="utf-8") as f:
                for ev in _db_base_events_snapshots_range(symbol, start_ts_ms, end_ts_ms):
                    obj = _base_event_to_json(ev)
                    ln = json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
                    sha.update(ln)
                    sha.update(b"\n")
                    f.write(ln.decode("utf-8"))
                    f.write("\n")
                    yield ev

        if args.perf_profile:
            prof, out = _profile_call(_process_replay_events, _iter_and_export(), csv_out_path=csv_out)
            out["profile"] = prof
        else:
            out = _process_replay_events(_iter_and_export(), csv_out_path=csv_out)
        out["dataset"]["source"] = "postgresql.orderbook_snapshots"
        out["dataset"]["symbol"] = symbol
        out["dataset"]["tick_size_inferred"] = str(inferred_tick)
        out["dataset"]["replay_file_path"] = replay_path
        out["dataset"]["replay_file_sha256"] = sha.hexdigest()
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, out)
        else:
            print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.workflow:
        symbols = _split_csv_symbols(args.db_symbols) if args.db_symbols.strip() else ["btcusdt"]
        start_ts_ms = int(args.db_start_ts_ms) if str(args.db_start_ts_ms).strip() else None
        end_ts_ms = int(args.db_end_ts_ms) if str(args.db_end_ts_ms).strip() else None
        out_dir = args.workflow_out_dir.strip() or os.path.abspath(os.path.join(os.getcwd(), "artifacts_workflow"))
        res = _workflow_fail_fast(symbols=symbols, start_ts_ms=start_ts_ms, end_ts_ms=end_ts_ms, out_dir=out_dir)
        out_path = args.out.strip()
        if out_path:
            _write_json_out(out_path, res)
        else:
            print(json.dumps(res, ensure_ascii=False, indent=2, default=str))
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
    out_path = args.out.strip()
    if out_path:
        _write_json_out(out_path, out)
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
