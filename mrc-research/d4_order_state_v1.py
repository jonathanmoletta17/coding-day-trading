from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


@dataclass(frozen=True)
class RemoteOrderProgress:
    exchange_state: str
    lifecycle_state: str
    total: Decimal
    filled: Decimal
    remaining: Decimal
    terminal: bool
    retry_open_allowed: bool


def normalize_remote_order(row: dict) -> RemoteOrderProgress:
    """Normalize OKX order progress without inferring absence as failure.

    Any observed remote order, including partial or canceled, blocks blind opening
    retries. A retry decision belongs to a higher-level intent/reconciliation policy.
    """
    state = str(row.get("state") or "").lower()
    total = dec(row.get("sz"))
    filled = dec(row.get("accFillSz"))
    if total <= 0:
        raise ValueError("REMOTE_ORDER_TOTAL_INVALID")
    if filled < 0 or filled > total:
        raise ValueError("REMOTE_ORDER_FILL_INVALID")
    remaining = total - filled

    if state == "filled":
        if remaining != 0:
            raise ValueError("FILLED_STATE_WITH_REMAINING_QTY")
        life, terminal = "FILLED", True
    elif state in {"canceled", "mmp_canceled"}:
        life, terminal = ("CANCELED_PARTIAL" if filled > 0 else "CANCELED_UNFILLED"), True
    elif state == "partially_filled":
        if filled <= 0 or remaining <= 0:
            raise ValueError("PARTIAL_STATE_QTY_INCONSISTENT")
        life, terminal = "PARTIALLY_FILLED", False
    elif state == "live":
        if remaining <= 0:
            raise ValueError("LIVE_STATE_WITHOUT_REMAINING_QTY")
        life, terminal = ("PARTIALLY_FILLED" if filled > 0 else "LIVE_UNFILLED"), False
    else:
        life, terminal = "REMOTE_UNKNOWN", False

    return RemoteOrderProgress(
        exchange_state=state,
        lifecycle_state=life,
        total=total,
        filled=filled,
        remaining=remaining,
        terminal=terminal,
        retry_open_allowed=False,
    )


def ambiguous_submission_resolution(remote_row: dict | None) -> str:
    """Fail-closed retry policy for an ambiguous client result."""
    if remote_row:
        normalize_remote_order(remote_row)
        return "RECONCILE_REMOTE_DO_NOT_RETRY"
    return "BOUNDED_QUERY_AGAIN_BEFORE_RETRY"
