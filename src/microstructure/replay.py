from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from src.microstructure.book import BookStateSnapshot, OrderBook
from src.microstructure.models import BaseEvent, DerivedEvent, EventEnvelope, EventRecord, parse_decimal, parse_int


class InvariantError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReplayResult:
    records: List[EventRecord]
    derived_events: List[DerivedEvent]


class ReplayEngineV01:
    def __init__(self, tick_size_by_instrument: Dict[str, Decimal]):
        self._tick_size_by_instrument = tick_size_by_instrument
        self._seen_event_ids: set[str] = set()
        self._last_source_seq: Dict[Tuple[str, str, str], int] = {}

    def _tick_size_for(self, instrument_id: str) -> Decimal:
        if instrument_id in self._tick_size_by_instrument:
            return self._tick_size_by_instrument[instrument_id]
        raise InvariantError(f"Missing tick_size for instrument_id={instrument_id!r}")

    def _validate_idempotent(self, env: EventEnvelope) -> None:
        if env.event_id in self._seen_event_ids:
            raise InvariantError(f"Duplicate event_id: {env.event_id}")
        self._seen_event_ids.add(env.event_id)

    def _validate_ordering(self, env: EventEnvelope) -> None:
        if env.source_seq is None:
            return
        key = env.stream_key()
        last = self._last_source_seq.get(key)
        if last is not None and env.source_seq < last:
            raise InvariantError(f"Non-monotonic source_seq for {key}: {env.source_seq} < {last}")
        self._last_source_seq[key] = env.source_seq

    def replay(self, base_events: Sequence[BaseEvent]) -> ReplayResult:
        self._seen_event_ids = set()
        self._last_source_seq = {}

        ordered = _order_events_canonically(base_events)

        books: Dict[Tuple[str, str, str], OrderBook] = {}
        records: List[EventRecord] = []
        derived_events: List[DerivedEvent] = []

        for ev in ordered:
            env = ev.envelope
            self._validate_idempotent(env)
            self._validate_ordering(env)

            book = books.get(env.stream_key())
            if book is None:
                book = OrderBook(tick_size=self._tick_size_for(env.instrument_id))
                books[env.stream_key()] = book

            pre = book.snapshot()
            post = pre
            derived_for_base: List[DerivedEvent] = []

            if env.event_type in ("SEQUENCE_GAP", "BOOK_RESET"):
                book.invalidate()
                post = book.snapshot()
            elif env.event_type == "BOOK_SNAPSHOT":
                bids = ev.payload.get("bids", [])
                asks = ev.payload.get("asks", [])
                depth_limit = ev.payload.get("depth_limit")
                if depth_limit is not None:
                    depth_limit = parse_int(depth_limit, "depth_limit")
                book.apply_snapshot(bids=bids, asks=asks, depth_limit=depth_limit)
                post = book.snapshot()
            elif env.event_type == "LEVEL_SET":
                side = str(ev.payload["side"])
                price = parse_decimal(ev.payload["price"], "price")
                new_size = parse_decimal(ev.payload["new_size"], "new_size")
                old_size = book.apply_level_set(side=side, price=price, new_size=new_size)
                post = book.snapshot()

                delta = new_size - old_size
                if delta != 0:
                    dtype = "LIQUIDITY_ADD" if delta > 0 else "LIQUIDITY_REMOVE"
                    derived_for_base.append(
                        _make_liquidity_delta(
                            base_env=env,
                            derived_type=dtype,
                            side=side,
                            price=price,
                            old_size=old_size,
                            new_size=new_size,
                            delta=delta,
                        )
                    )

                if post.depth_limit is not None:
                    shifts = _derive_level_shift(pre=pre, post=post, depth_limit=post.depth_limit)
                    if shifts:
                        derived_for_base.append(_make_level_shift(base_env=env, depth_limit=post.depth_limit, shifts=shifts))
            elif env.event_type == "TRADE_PRINT":
                size = parse_decimal(ev.payload["size"], "size")
                if size <= 0:
                    raise InvariantError("TRADE_PRINT.size must be > 0")
            else:
                raise InvariantError(f"Unsupported event_type: {env.event_type}")

            records.append(
                EventRecord(
                    envelope=env,
                    payload=ev.payload,
                    is_derived=False,
                    parent_event_id=None,
                    pre_state=pre,
                    post_state=post,
                    captures={},
                )
            )

            if derived_for_base:
                derived_events.extend(derived_for_base)
                for d in derived_for_base:
                    records.append(
                        EventRecord(
                            envelope=d.envelope,
                            payload=d.payload,
                            is_derived=True,
                            parent_event_id=d.parent_event_id,
                            pre_state=pre,
                            post_state=post,
                            captures={},
                        )
                    )

        records.sort(key=lambda r: (r.envelope.stream_key(), r.envelope.ordering_key(), 0 if not r.is_derived else 1, r.envelope.event_id))
        return ReplayResult(records=records, derived_events=derived_events)


def _order_events_canonically(base_events: Sequence[BaseEvent]) -> List[BaseEvent]:
    per_stream: Dict[Tuple[str, str, str], List[BaseEvent]] = {}
    for ev in base_events:
        per_stream.setdefault(ev.envelope.stream_key(), []).append(ev)

    ordered: List[BaseEvent] = []
    for sk in sorted(per_stream.keys()):
        stream_events = per_stream[sk]
        has_seq = any(e.envelope.source_seq is not None for e in stream_events)
        if has_seq and any(e.envelope.source_seq is None for e in stream_events):
            raise InvariantError(f"Mixed presence of source_seq within stream {sk}")

        if has_seq:
            stream_events.sort(
                key=lambda e: (
                    int(e.envelope.source_seq),  # type: ignore[arg-type]
                    int(e.envelope.ts_event) if e.envelope.ts_event is not None else int(e.envelope.ts_recv),
                    int(e.envelope.ts_recv),
                    e.envelope.event_id,
                )
            )
        else:
            stream_events.sort(
                key=lambda e: (
                    int(e.envelope.ts_event) if e.envelope.ts_event is not None else int(e.envelope.ts_recv),
                    int(e.envelope.ts_recv),
                    e.envelope.event_id,
                )
            )
        ordered.extend(stream_events)
    return ordered


def _make_liquidity_delta(
    base_env: EventEnvelope,
    derived_type: str,
    side: str,
    price: Decimal,
    old_size: Decimal,
    new_size: Decimal,
    delta: Decimal,
) -> DerivedEvent:
    denv = dataclasses.replace(base_env, event_id=f"{base_env.event_id}:{derived_type}", event_type=derived_type)
    return DerivedEvent(
        envelope=denv,
        payload={
            "side": side,
            "price": str(price),
            "old_size": str(old_size),
            "new_size": str(new_size),
            "delta_size": str(delta),
        },
        parent_event_id=base_env.event_id,
    )


def _make_level_shift(base_env: EventEnvelope, depth_limit: int, shifts: List[Dict[str, object]]) -> DerivedEvent:
    denv = dataclasses.replace(base_env, event_id=f"{base_env.event_id}:LEVEL_SHIFT", event_type="LEVEL_SHIFT")
    return DerivedEvent(
        envelope=denv,
        payload={"depth_limit": depth_limit, "shifts": shifts},
        parent_event_id=base_env.event_id,
    )


def _derive_level_shift(pre: BookStateSnapshot, post: BookStateSnapshot, depth_limit: int) -> List[Dict[str, object]]:
    shifts: List[Dict[str, object]] = []
    if depth_limit <= 0:
        return shifts
    for side in ("BID", "ASK"):
        pre_top = pre.top_n(side, depth_limit)
        post_top = post.top_n(side, depth_limit)
        pre_index = {p: i for i, (p, _) in enumerate(pre_top)}
        post_index = {p: i for i, (p, _) in enumerate(post_top)}
        all_prices = set(pre_index.keys()) | set(post_index.keys())
        for p in sorted(all_prices):
            oi = pre_index.get(p)
            ni = post_index.get(p)
            if oi == ni:
                continue
            size = post.level_size(side, p) if ni is not None else pre.level_size(side, p)
            shifts.append(
                {
                    "side": side,
                    "price": str(p),
                    "size": str(size),
                    "old_index": oi,
                    "new_index": ni,
                }
            )
    return shifts
