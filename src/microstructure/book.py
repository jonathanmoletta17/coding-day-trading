from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Sequence, Tuple

from src.microstructure.models import Side, parse_decimal


def tick_distance(price_a: Decimal, price_b: Decimal, tick_size: Decimal) -> int:
    if tick_size <= 0:
        raise ValueError("tick_size must be > 0")
    diff = (price_a - price_b).copy_abs() / tick_size
    if diff == diff.to_integral_value():
        return int(diff)
    return int(diff.to_integral_value(rounding="ROUND_HALF_UP"))


@dataclass(frozen=True)
class BookStateSnapshot:
    bids: Dict[Decimal, Decimal]
    asks: Dict[Decimal, Decimal]
    tick_size: Decimal
    depth_limit: Optional[int]
    valid: bool

    @property
    def best_bid_price(self) -> Optional[Decimal]:
        return max(self.bids.keys()) if self.bids else None

    @property
    def best_ask_price(self) -> Optional[Decimal]:
        return min(self.asks.keys()) if self.asks else None

    def touch_price(self, side: Side) -> Optional[Decimal]:
        if side == "BID":
            return self.best_bid_price
        if side == "ASK":
            return self.best_ask_price
        raise ValueError(f"Invalid side: {side}")

    @property
    def spread_ticks(self) -> Optional[int]:
        bb = self.best_bid_price
        ba = self.best_ask_price
        if bb is None or ba is None:
            return None
        return tick_distance(ba, bb, self.tick_size)

    def level_size(self, side: Side, price: Decimal) -> Decimal:
        if side == "BID":
            return self.bids.get(price, Decimal(0))
        if side == "ASK":
            return self.asks.get(price, Decimal(0))
        raise ValueError(f"Invalid side: {side}")

    def top_n(self, side: Side, n: int) -> List[Tuple[Decimal, Decimal]]:
        if n <= 0:
            return []
        if side == "BID":
            return sorted(self.bids.items(), key=lambda kv: kv[0], reverse=True)[:n]
        if side == "ASK":
            return sorted(self.asks.items(), key=lambda kv: kv[0])[:n]
        raise ValueError(f"Invalid side: {side}")


class OrderBook:
    def __init__(self, tick_size: Decimal):
        if tick_size <= 0:
            raise ValueError("tick_size must be > 0")
        self._tick_size = tick_size
        self._bids: Dict[Decimal, Decimal] = {}
        self._asks: Dict[Decimal, Decimal] = {}
        self._depth_limit: Optional[int] = None
        self._valid: bool = False

    def invalidate(self) -> None:
        self._bids = {}
        self._asks = {}
        self._depth_limit = None
        self._valid = False

    def snapshot(self) -> BookStateSnapshot:
        return BookStateSnapshot(
            bids=dict(self._bids),
            asks=dict(self._asks),
            tick_size=self._tick_size,
            depth_limit=self._depth_limit,
            valid=self._valid,
        )

    def apply_snapshot(self, bids: Sequence[Sequence[object]], asks: Sequence[Sequence[object]], depth_limit: Optional[int]) -> None:
        nb: Dict[Decimal, Decimal] = {}
        na: Dict[Decimal, Decimal] = {}
        for p, s in bids:
            price = parse_decimal(p, "bids.price")
            size = parse_decimal(s, "bids.size")
            if size < 0:
                raise ValueError("snapshot size must be >= 0")
            if size == 0:
                continue
            nb[price] = size
        for p, s in asks:
            price = parse_decimal(p, "asks.price")
            size = parse_decimal(s, "asks.size")
            if size < 0:
                raise ValueError("snapshot size must be >= 0")
            if size == 0:
                continue
            na[price] = size
        self._bids = nb
        self._asks = na
        self._depth_limit = depth_limit
        self._valid = True

    def apply_level_set(self, side: Side, price: Decimal, new_size: Decimal) -> Decimal:
        if not self._valid:
            raise ValueError("Book state is invalid: expected BOOK_SNAPSHOT after gap/reset")
        if new_size < 0:
            raise ValueError("new_size must be >= 0")
        if side == "BID":
            old = self._bids.get(price, Decimal(0))
            if new_size == 0:
                self._bids.pop(price, None)
            else:
                self._bids[price] = new_size
            return old
        if side == "ASK":
            old = self._asks.get(price, Decimal(0))
            if new_size == 0:
                self._asks.pop(price, None)
            else:
                self._asks[price] = new_size
            return old
        raise ValueError(f"Invalid side: {side}")

