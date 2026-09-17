from decimal import Decimal

from d4_order_state_v1 import ambiguous_submission_resolution, normalize_remote_order


def check(name, cond):
    if not cond:
        raise AssertionError(name)


# 1) pristine resting order
x = normalize_remote_order({"state":"live","sz":"1.00","accFillSz":"0"})
check("live state", x.lifecycle_state == "LIVE_UNFILLED")
check("live remaining", x.remaining == Decimal("1.00"))
check("live no retry", x.retry_open_allowed is False)

# 2) partial fill must preserve exact remaining quantity and block duplicate open
x = normalize_remote_order({"state":"partially_filled","sz":"1.00","accFillSz":"0.35"})
check("partial state", x.lifecycle_state == "PARTIALLY_FILLED")
check("partial filled", x.filled == Decimal("0.35"))
check("partial remaining", x.remaining == Decimal("0.65"))
check("partial nonterminal", x.terminal is False)
check("partial no duplicate", x.retry_open_allowed is False)

# 3) some OKX-style live snapshots may carry a nonzero accFillSz; normalize conservatively
x = normalize_remote_order({"state":"live","sz":"0.01","accFillSz":"0.004"})
check("live partial normalized", x.lifecycle_state == "PARTIALLY_FILLED")
check("live partial remaining", x.remaining == Decimal("0.006"))

# 4) terminal fill
x = normalize_remote_order({"state":"filled","sz":"0.01","accFillSz":"0.01"})
check("filled terminal", x.terminal is True and x.remaining == 0)

# 5) canceled after partial must retain evidence of the partial execution
x = normalize_remote_order({"state":"canceled","sz":"1.00","accFillSz":"0.40"})
check("cancel partial", x.lifecycle_state == "CANCELED_PARTIAL")
check("cancel partial remaining", x.remaining == Decimal("0.60"))
check("cancel terminal", x.terminal is True)
check("cancel no blind retry", x.retry_open_allowed is False)

# 6) ambiguous result: if exchange row exists, reconcile; never blind retry
check("ambig remote", ambiguous_submission_resolution({"state":"partially_filled","sz":"1","accFillSz":"0.2"}) == "RECONCILE_REMOTE_DO_NOT_RETRY")
check("ambig absent", ambiguous_submission_resolution(None) == "BOUNDED_QUERY_AGAIN_BEFORE_RETRY")

# 7) inconsistent states must fail closed
for bad in (
    {"state":"partially_filled","sz":"1","accFillSz":"0"},
    {"state":"partially_filled","sz":"1","accFillSz":"1"},
    {"state":"filled","sz":"1","accFillSz":"0.9"},
    {"state":"live","sz":"1","accFillSz":"1.1"},
):
    try:
        normalize_remote_order(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(f"inconsistent order accepted: {bad}")

print("D4_ORDER_STATE_TEST=PASS partial_fill=true idempotency=true invalid_states_fail_closed=true")
