from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple


EventType = str
Side = str


ALLOWED_BASE_EVENT_TYPES: frozenset[EventType] = frozenset(
    {"BOOK_SNAPSHOT", "LEVEL_SET", "TRADE_PRINT", "SEQUENCE_GAP", "BOOK_RESET"}
)

ALLOWED_DERIVED_EVENT_TYPES: frozenset[EventType] = frozenset(
    {
        "LIQUIDITY_ADD",
        "LIQUIDITY_REMOVE",
        "CANCEL",
        "EXECUTION_BY_AGGRESSION",
        "REPLENISH_AFTER_CONSUMPTION",
        "LEVEL_SHIFT",
    }
)


def parse_decimal(v: Any, field: str) -> Decimal:
    if isinstance(v, Decimal):
        return v
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, float):
        return Decimal(repr(v))
    if isinstance(v, str):
        try:
            return Decimal(v)
        except InvalidOperation as e:
            raise ValueError(f"Invalid decimal for {field}: {v!r}") from e
    raise ValueError(f"Invalid decimal type for {field}: {type(v).__name__}")


def parse_int(v: Any, field: str) -> int:
    if isinstance(v, bool):
        raise ValueError(f"Invalid int for {field}: bool")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        raise ValueError(f"Invalid int for {field}: {v!r}")
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
    raise ValueError(f"Invalid int for {field}: {v!r}")


def parse_ts_ms(v: Any, field: str) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, bool):
        raise ValueError(f"Invalid timestamp for {field}: bool")
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip()
        if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
            return int(s)
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError as e:
            raise ValueError(f"Invalid timestamp for {field}: {v!r}") from e
    raise ValueError(f"Invalid timestamp for {field}: {v!r}")


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    event_type: EventType
    instrument_id: str
    venue: str
    source: str
    ts_recv: int
    ts_event: Optional[int] = None
    source_seq: Optional[int] = None

    def stream_key(self) -> Tuple[str, str, str]:
        return (self.venue, self.instrument_id, self.source)

    def ordering_key(self) -> Tuple[str, str, str, int, int, int, str]:
        if self.source_seq is not None:
            primary = int(self.source_seq)
            secondary = int(self.ts_event) if self.ts_event is not None else int(self.ts_recv)
            return (self.venue, self.instrument_id, self.source, 0, primary, secondary, self.event_id)
        primary = int(self.ts_event) if self.ts_event is not None else int(self.ts_recv)
        secondary = int(self.ts_recv)
        return (self.venue, self.instrument_id, self.source, 1, primary, secondary, self.event_id)

    def effective_ts(self) -> int:
        return self.ts_event if self.ts_event is not None else self.ts_recv


@dataclass(frozen=True)
class BaseEvent:
    envelope: EventEnvelope
    payload: Dict[str, Any]

    @staticmethod
    def from_json(obj: Dict[str, Any]) -> "BaseEvent":
        env = EventEnvelope(
            event_id=str(obj["event_id"]),
            event_type=str(obj["event_type"]),
            instrument_id=str(obj["instrument_id"]),
            venue=str(obj["venue"]),
            source=str(obj["source"]),
            ts_recv=parse_int(obj["ts_recv"], "ts_recv"),
            ts_event=parse_ts_ms(obj.get("ts_event"), "ts_event"),
            source_seq=parse_int(obj["source_seq"], "source_seq") if obj.get("source_seq") is not None else None,
        )
        if env.event_type not in ALLOWED_BASE_EVENT_TYPES:
            raise ValueError(f"Unsupported base event_type: {env.event_type}")
        payload = {k: v for k, v in obj.items()}
        for k in (
            "event_id",
            "event_type",
            "instrument_id",
            "venue",
            "source",
            "ts_recv",
            "ts_event",
            "source_seq",
        ):
            payload.pop(k, None)
        return BaseEvent(envelope=env, payload=payload)


@dataclass(frozen=True)
class DerivedEvent:
    envelope: EventEnvelope
    payload: Dict[str, Any]
    parent_event_id: str


@dataclass(frozen=True)
class EventRecord:
    envelope: EventEnvelope
    payload: Dict[str, Any]
    is_derived: bool
    parent_event_id: Optional[str]
    pre_state: Any
    post_state: Any
    captures: Dict[str, Any]

    def effective_ts(self) -> int:
        return self.envelope.effective_ts()

    @property
    def side(self) -> Optional[str]:
        v = self.payload.get("side")
        return str(v) if v is not None else None

    @property
    def price(self) -> Optional[Decimal]:
        v = self.payload.get("price")
        return parse_decimal(v, "price") if v is not None else None

    @property
    def new_size(self) -> Optional[Decimal]:
        v = self.payload.get("new_size")
        return parse_decimal(v, "new_size") if v is not None else None

    @property
    def delta_size(self) -> Optional[Decimal]:
        v = self.payload.get("delta_size")
        return parse_decimal(v, "delta_size") if v is not None else None
