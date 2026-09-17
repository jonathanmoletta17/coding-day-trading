from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

INST = "BTC-USDT-SWAP"
QTY = Decimal("0.01")
ARM = "DEMO_D4_SAFE_LIFECYCLE_V1"
ORDER_EXPIRY_MS = 10_000


def dec(v, default="0") -> Decimal:
    return d3.dec(v, default)


def cid(attempt: str, kind: str) -> str:
    import hashlib
    h = hashlib.sha256(f"SLOW_TREND_BREAKOUT_V1|D4|{attempt}|{kind}|{INST}|{QTY}|V1".encode()).hexdigest()[:18].upper()
    return ("MRCD4" + kind[:1].upper() + h)[:32]


async def raw_post(c: d3.Client, path: str, payload: dict, exp_ms: int | None = None) -> tuple[int, dict]:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    headers = c.headers(ts, "POST", path, body)
    headers["expTime"] = str(exp_ms if exp_ms is not None else int(time.time() * 1000) + ORDER_EXPIRY_MS)
    r = await c.h.post(path, content=body.encode(), headers=headers)
    try:
        j = r.json()
    except Exception:
        j = {}
    return r.status_code, j


async def post_ok(c: d3.Client, path: str, payload: dict) -> dict:
    status, j = await raw_post(c, path, payload)
    if status >= 400:
        raise RuntimeError(f"HTTP_{status} {j}")
    if str(j.get("code")) != "0":
        raise RuntimeError(f"OKX_TOP_ERROR {j.get('code')} {j.get('msg')}")
    rows = j.get("data") or []
    if not rows:
        raise RuntimeError("EMPTY_POST_DATA")
    row = rows[0]
    if str(row.get("sCode") or "0") != "0":
        raise RuntimeError(f"OKX_ITEM_ERROR {row.get('sCode')} {row.get('sMsg')}")
    return row


async def details_by_clid(c: d3.Client, clid: str) -> dict:
    rows = await c.private_get("/api/v5/trade/order", {"instId": INST, "clOrdId": clid})
    return rows[0] if rows else {}


async def wait_state(c: d3.Client, *, ord_id: str = "", clid: str = "", wanted: set[str], timeout_s: float = 8) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        params = {"instId": INST}
        if ord_id:
            params["ordId"] = ord_id
        else:
            params["clOrdId"] = clid
        rows = await c.private_get("/api/v5/trade/order", params)
        if rows:
            last = rows[0]
            if str(last.get("state")) in wanted:
                return last
        await asyncio.sleep(0.25)
    return last


async def flat(c: d3.Client) -> dict:
    p = await d3.current_pos(c)
    pending = await d3.pending_orders(c)
    return {"position": str(p), "pending": len(pending)}


async def assert_flat(c: d3.Client, where: str) -> None:
    s = await flat(c)
    if Decimal(s["position"]) != 0 or s["pending"] != 0:
        raise RuntimeError(f"NOT_FLAT_{where} {s}")


async def preflight(c: d3.Client) -> dict:
    if os.getenv("MRC_EXECUTION_MODE", "").strip() != "DEMO":
        raise RuntimeError("MODE_NOT_DEMO")
    if os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0") != "1":
        raise RuntimeError("D4_EXECUTION_NOT_ENABLED")
    if os.getenv("MRC_KILL_SWITCH", "1") != "0":
        raise RuntimeError("KILL_SWITCH_ACTIVE")
    if os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1") != "0":
        raise RuntimeError("DIAGNOSTIC_ONLY_ACTIVE")
    if os.getenv("MRC_D4_ARM", "").strip() != ARM:
        raise RuntimeError("D4_NOT_ARMED")
    attempt = os.getenv("MRC_D4_ATTEMPT_ID", "").strip()
    if not d3.ATTEMPT_RE.fullmatch(attempt):
        raise RuntimeError("D4_ATTEMPT_ID_INVALID")

    cfg = (await c.private_get("/api/v5/account/config"))[0]
    if str(cfg.get("acctLv")) != "2" or str(cfg.get("posMode")) != "net_mode":
        raise RuntimeError("ACCOUNT_MODE_INVALID")
    if "trade" not in {x.strip() for x in str(cfg.get("perm") or "").split(",") if x.strip()}:
        raise RuntimeError("TRADE_PERMISSION_MISSING")

    lev = await c.private_get("/api/v5/account/leverage-info", {"instId": INST, "mgnMode": "cross"})
    values = {dec(x.get("lever")) for x in lev if x.get("mgnMode") == "cross"}
    expected = dec(os.getenv("MRC_D4_EXPECTED_LEVERAGE", "3"))
    if values != {expected}:
        raise RuntimeError(f"LEVERAGE_MISMATCH {values} expected={expected}")

    specs = await c.public_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": INST})
    if len(specs) != 1:
        raise RuntimeError("SPEC_NOT_UNIQUE")
    spec = specs[0]
    if spec.get("state") != "live" or spec.get("ctType") != "linear" or spec.get("settleCcy") != "USDT":
        raise RuntimeError("SPEC_INVALID")
    if QTY < dec(spec.get("minSz")):
        raise RuntimeError("QTY_BELOW_MIN")

    await assert_flat(c, "PREFLIGHT")
    ticker = (await c.public_get("/api/v5/market/ticker", {"instId": INST}))[0]
    last = dec(ticker.get("last"))
    tick = dec(spec.get("tickSz"), "0.1")
    px = (last * Decimal("0.50") / tick).to_integral_value(rounding=ROUND_DOWN) * tick
    if px <= 0 or px >= last * Decimal("0.8"):
        raise RuntimeError("RESTING_PRICE_NOT_CONSERVATIVE")
    return {"attempt": attempt, "last": str(last), "tick": str(tick), "resting_buy_px": format(px, "f"), "leverage": sorted(str(x) for x in values)}


async def place_resting(c: d3.Client, clid: str, px: str) -> dict:
    payload = {"instId": INST, "tdMode": "cross", "clOrdId": clid, "side": "buy", "ordType": "limit", "px": px, "sz": str(QTY)}
    row = await post_ok(c, "/api/v5/trade/order", payload)
    ord_id = str(row.get("ordId") or "")
    if not ord_id:
        raise RuntimeError("PLACE_NO_ORDID")
    d = await wait_state(c, ord_id=ord_id, wanted={"live", "partially_filled"})
    if str(d.get("state")) not in {"live", "partially_filled"}:
        raise RuntimeError(f"ORDER_NOT_RESTING {d}")
    if dec(d.get("accFillSz")) != 0:
        raise RuntimeError(f"UNEXPECTED_FILL_ON_DEEP_RESTING_ORDER {d.get('accFillSz')}")
    if await d3.current_pos(c) != 0:
        raise RuntimeError("UNEXPECTED_POSITION_FROM_RESTING_ORDER")
    return d


async def cancel_by_ordid(c: d3.Client, d: dict) -> dict:
    await post_ok(c, "/api/v5/trade/cancel-order", {"instId": INST, "ordId": str(d["ordId"])})
    out = await wait_state(c, ord_id=str(d["ordId"]), wanted={"canceled", "mmp_canceled"})
    if str(out.get("state")) not in {"canceled", "mmp_canceled"}:
        raise RuntimeError(f"CANCEL_BY_ORDID_NOT_FINAL {out}")
    await assert_flat(c, "AFTER_CANCEL_ORDID")
    return out


async def cancel_by_clid(c: d3.Client, clid: str) -> dict:
    await post_ok(c, "/api/v5/trade/cancel-order", {"instId": INST, "clOrdId": clid})
    out = await wait_state(c, clid=clid, wanted={"canceled", "mmp_canceled"})
    if str(out.get("state")) not in {"canceled", "mmp_canceled"}:
        raise RuntimeError(f"CANCEL_BY_CLID_NOT_FINAL {out}")
    await assert_flat(c, "AFTER_CANCEL_CLID")
    return out


async def run() -> dict:
    c = d3.Client()
    owned: list[str] = []
    try:
        pf = await preflight(c)
        attempt = pf["attempt"]
        px = pf["resting_buy_px"]
        results: dict = {"status": "RUNNING", "preflight": pf, "scenarios": {}}

        # D4.2: RESTING + CANCEL BY ordId
        c1 = cid(attempt, "ORDID")
        d1 = await place_resting(c, c1, px); owned.append(c1)
        z1 = await cancel_by_ordid(c, d1)
        results["scenarios"]["cancel_by_ordid"] = {"status": "PASS", "clOrdId": c1, "ordId": d1.get("ordId"), "final_state": z1.get("state")}

        # D4.3: RESTING + CANCEL BY clOrdId
        c2 = cid(attempt, "CLID")
        d2 = await place_resting(c, c2, px); owned.append(c2)
        z2 = await cancel_by_clid(c, c2)
        results["scenarios"]["cancel_by_clOrdId"] = {"status": "PASS", "clOrdId": c2, "ordId": d2.get("ordId"), "final_state": z2.get("state")}

        # D4.1 / D4.5: simulate ambiguous ACK, then query-before-retry by deterministic clOrdId.
        # The POST response is intentionally discarded from the state machine. We prove that
        # the resolver finds the exchange order and therefore retry_allowed=False.
        c3 = cid(attempt, "AMBIG")
        payload3 = {"instId": INST, "tdMode": "cross", "clOrdId": c3, "side": "buy", "ordType": "limit", "px": px, "sz": str(QTY)}
        await post_ok(c, "/api/v5/trade/order", payload3); owned.append(c3)
        resolved = await details_by_clid(c, c3)
        if not resolved or str(resolved.get("clOrdId")) != c3 or str(resolved.get("state")) not in {"live", "partially_filled"}:
            raise RuntimeError(f"AMBIGUOUS_RECONCILIATION_FAILED {resolved}")
        if dec(resolved.get("accFillSz")) != 0:
            raise RuntimeError("AMBIGUOUS_ORDER_UNEXPECTED_FILL")
        retry_allowed = False  # found-on-exchange means idempotent state machine MUST NOT resubmit
        z3 = await cancel_by_clid(c, c3)
        results["scenarios"]["ambiguous_ack_query_before_retry"] = {
            "status": "PASS", "clOrdId": c3, "resolved_ordId": resolved.get("ordId"),
            "resolved_state": resolved.get("state"), "retry_allowed": retry_allowed, "final_state": z3.get("state")
        }

        # D4.4: deterministic rejection using an already-expired server deadline.
        c4 = cid(attempt, "EXPIRED")
        payload4 = {"instId": INST, "tdMode": "cross", "clOrdId": c4, "side": "buy", "ordType": "limit", "px": px, "sz": str(QTY)}
        server = await c.public_get("/api/v5/public/time")
        server_ms = int(server[0]["ts"])
        http_status, jr = await raw_post(c, "/api/v5/trade/order", payload4, exp_ms=server_ms - 60_000)
        row4 = (jr.get("data") or [{}])[0]
        rejected = str(row4.get("sCode") or "") != "0"
        hist = await c.private_get("/api/v5/trade/orders-history", {"instType": "SWAP", "instId": INST, "limit": "100"})
        fills = await c.private_get("/api/v5/trade/fills", {"instType": "SWAP", "instId": INST, "limit": "100"})
        if not rejected or any(str(x.get("clOrdId")) == c4 for x in hist + fills):
            raise RuntimeError(f"EXPIRED_REJECTION_NOT_CLEAN status={http_status} response={jr}")
        await assert_flat(c, "AFTER_EXPIRED_REJECT")
        results["scenarios"]["expired_rejection"] = {"status": "PASS", "http_status": http_status, "okx_code": jr.get("code"), "sCode": row4.get("sCode"), "sMsg": row4.get("sMsg"), "order_evidence": False}

        await assert_flat(c, "FINAL")
        results["status"] = "PASS"
        results["final"] = await flat(c)
        results["real_money_execution_enabled"] = False
        print("OKX_DEMO_D4_SAFE_LIFECYCLE=" + json.dumps(results, separators=(",", ":"), ensure_ascii=False), flush=True)
        return results
    finally:
        # Fail-safe cleanup of owned resting orders only; never opens or flips a position.
        try:
            pending = await d3.pending_orders(c)
            for o in pending:
                if str(o.get("clOrdId")) in set(owned):
                    try:
                        await post_ok(c, "/api/v5/trade/cancel-order", {"instId": INST, "ordId": str(o.get("ordId"))})
                    except Exception:
                        pass
        finally:
            await c.close()


class H(BaseHTTPRequestHandler):
    RESULT: dict = {"status": "STARTING"}
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            ok = self.RESULT.get("status") == "PASS"
            body = json.dumps(self.RESULT, separators=(",", ":")).encode()
            self.send_response(200 if ok else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()
    def log_message(self, *args): return


def main():
    try:
        H.RESULT = asyncio.run(run())
    except Exception as e:
        H.RESULT = {"status": "FAIL", "error": f"{type(e).__name__}: {e}", "real_money_execution_enabled": False}
        print("OKX_DEMO_D4_SAFE_LIFECYCLE=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
