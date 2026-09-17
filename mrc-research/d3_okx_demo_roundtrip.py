from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

import httpx

BASE = "https://openapi.okx.com"
STRATEGY = "SLOW_TREND_BREAKOUT_V1"
INST = "BTC-USDT-SWAP"
QTY = Decimal("0.01")
MAX_NOTIONAL_USDT = Decimal("20")
EXPECTED_LABEL = "MRC-SLOW-DEMO-GLOBAL"
ARM = "DEMO_BTC_MIN_ROUNDTRIP_V2"
ATTEMPT_RE = re.compile(r"^[A-Za-z0-9_-]{8,24}$")


def dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def sign(ts: str, method: str, request_path: str, body: str, secret: str) -> str:
    msg = f"{ts}{method.upper()}{request_path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


def deterministic_client_id(attempt_id: str, kind: str) -> str:
    digest = hashlib.sha256(f"{STRATEGY}|D3|{attempt_id}|{kind}|{INST}|{QTY}|V2".encode()).hexdigest()[:20].upper()
    prefix = {"OPEN": "MRCD3O", "CLOSE": "MRCD3C", "SAFE": "MRCD3S"}[kind]
    return f"{prefix}{digest}"[:32]


class Client:
    def __init__(self):
        self.key = os.getenv("OKX_DEMO_API_KEY", "").strip()
        self.secret = os.getenv("OKX_DEMO_SECRET_KEY", "").strip()
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE", "").strip()
        if not all((self.key, self.secret, self.passphrase)):
            raise RuntimeError("DEMO_CREDENTIALS_MISSING")
        self.h = httpx.AsyncClient(base_url=BASE, timeout=20, headers={"User-Agent": "MRC-OKX-D3-Demo/2.0"})

    def headers(self, ts: str, method: str, request_path: str, body: str = "") -> dict:
        return {
            "Content-Type": "application/json",
            "OK-ACCESS-KEY": self.key,
            "OK-ACCESS-SIGN": sign(ts, method, request_path, body, self.secret),
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "x-simulated-trading": "1",
        }

    async def public_get(self, path: str, params: dict | None = None):
        r = await self.h.get(path, params=params or {})
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise RuntimeError(f"OKX_PUBLIC_ERROR {j.get('code')} {j.get('msg')}")
        return j.get("data") or []

    async def private_get(self, path: str, params: dict | None = None):
        params = params or {}
        qs = urlencode(params)
        request_path = path + (("?" + qs) if qs else "")
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        r = await self.h.get(path, params=params, headers=self.headers(ts, "GET", request_path))
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise RuntimeError(f"OKX_PRIVATE_ERROR {j.get('code')} {j.get('msg')}")
        return j.get("data") or []

    async def private_post(self, path: str, payload: dict):
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        r = await self.h.post(path, content=body.encode(), headers=self.headers(ts, "POST", path, body))
        try:
            j = r.json()
        except Exception:
            j = {}
        if r.status_code >= 400:
            raise RuntimeError(f"OKX_POST_HTTP {r.status_code} {j.get('code')} {j.get('msg')}")
        if j.get("code") != "0":
            raise RuntimeError(f"OKX_POST_ERROR {j.get('code')} {j.get('msg')}")
        rows = j.get("data") or []
        if not rows:
            raise RuntimeError("OKX_POST_EMPTY")
        row = rows[0]
        if str(row.get("sCode") or "0") != "0":
            raise RuntimeError(f"OKX_ORDER_REJECTED {row.get('sCode')} {row.get('sMsg')}")
        return row

    async def close(self):
        await self.h.aclose()


async def order_details(c: Client, ord_id: str, timeout_s: float = 12.0) -> dict:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        rows = await c.private_get("/api/v5/trade/order", {"instId": INST, "ordId": ord_id})
        if rows:
            last = rows[0]
            if last.get("state") in {"filled", "canceled", "mmp_canceled"}:
                return last
        await asyncio.sleep(0.4)
    return last


async def current_pos(c: Client) -> Decimal:
    rows = await c.private_get("/api/v5/account/positions", {"instId": INST})
    total = Decimal("0")
    for r in rows:
        if r.get("instId") == INST:
            total += dec(r.get("pos"))
    return total


async def pending_orders(c: Client) -> list[dict]:
    rows = await c.private_get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
    return [r for r in rows if r.get("instId") == INST]


async def wait_pos(c: Client, want_zero: bool, timeout_s: float = 10.0) -> Decimal:
    deadline = time.time() + timeout_s
    last = Decimal("0")
    while time.time() < deadline:
        last = await current_pos(c)
        if (last == 0) == want_zero:
            return last
        await asyncio.sleep(0.4)
    return last


async def assert_entry_still_clean(c: Client) -> None:
    pos = await current_pos(c)
    if pos != 0:
        raise RuntimeError(f"ENTRY_RECHECK_POSITION_NOT_FLAT pos={pos}")
    pending = await pending_orders(c)
    if pending:
        raise RuntimeError(f"ENTRY_RECHECK_PENDING_ORDERS count={len(pending)}")


async def validate_preflight(c: Client) -> dict:
    mode = os.getenv("MRC_EXECUTION_MODE", "").strip()
    enabled = os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0") == "1"
    kill = os.getenv("MRC_KILL_SWITCH", "1") != "0"
    diagnostic_only = os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1") != "0"
    arm = os.getenv("MRC_D3_ARM", "").strip()
    attempt_id = os.getenv("MRC_D3_ATTEMPT_ID", "").strip()
    expected_leverage_raw = os.getenv("MRC_D3_EXPECTED_LEVERAGE", "").strip()

    if mode != "DEMO":
        raise RuntimeError("MODE_NOT_DEMO")
    if not enabled:
        raise RuntimeError("DEMO_EXECUTION_NOT_ENABLED")
    if kill:
        raise RuntimeError("KILL_SWITCH_ACTIVE")
    if diagnostic_only:
        raise RuntimeError("DIAGNOSTIC_ONLY_ACTIVE")
    if arm != ARM:
        raise RuntimeError("D3_NOT_ARMED_V2")
    if not ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("D3_ATTEMPT_ID_INVALID")
    if not expected_leverage_raw:
        raise RuntimeError("EXPECTED_LEVERAGE_NOT_DECLARED")
    expected_leverage = dec(expected_leverage_raw)
    if expected_leverage <= 0:
        raise RuntimeError("EXPECTED_LEVERAGE_INVALID")

    cfg_rows = await c.private_get("/api/v5/account/config")
    if not cfg_rows:
        raise RuntimeError("ACCOUNT_CONFIG_EMPTY")
    cfg = cfg_rows[0]
    perms = {p.strip() for p in str(cfg.get("perm") or "").split(",") if p.strip()}
    if str(cfg.get("acctLv") or "") != "2":
        raise RuntimeError(f"ACCOUNT_MODE_NOT_FUTURES acctLv={cfg.get('acctLv')}")
    if str(cfg.get("posMode") or "") != "net_mode":
        raise RuntimeError(f"POSITION_MODE_NOT_NET posMode={cfg.get('posMode')}")
    if "trade" not in perms:
        raise RuntimeError("TRADE_PERMISSION_MISSING")
    if str(cfg.get("label") or "") != EXPECTED_LABEL:
        raise RuntimeError("API_LABEL_MISMATCH")

    swaps = await c.private_get("/api/v5/account/instruments", {"instType": "SWAP"})
    private_ids = {r.get("instId") for r in swaps}
    if INST not in private_ids:
        raise RuntimeError("BTC_SWAP_NOT_PRIVATE_AVAILABLE")

    pub = await c.public_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": INST})
    if len(pub) != 1:
        raise RuntimeError("BTC_SWAP_PUBLIC_NOT_UNIQUE")
    spec = pub[0]
    if (
        spec.get("state") != "live"
        or spec.get("ctType") != "linear"
        or spec.get("ctValCcy") != "BTC"
        or spec.get("settleCcy") != "USDT"
    ):
        raise RuntimeError("BTC_SWAP_METADATA_INVALID")
    lot = dec(spec.get("lotSz"))
    minimum = dec(spec.get("minSz"))
    if QTY < minimum or lot <= 0 or (QTY / lot) != (QTY / lot).to_integral_value():
        raise RuntimeError("TEST_QTY_INVALID")

    before_pos = await current_pos(c)
    if before_pos != 0:
        raise RuntimeError(f"EXISTING_POSITION_ABORT pos={before_pos}")
    pending = await pending_orders(c)
    if pending:
        raise RuntimeError(f"EXISTING_PENDING_ORDER_ABORT count={len(pending)}")

    leverage_rows = await c.private_get("/api/v5/account/leverage-info", {"instId": INST, "mgnMode": "cross"})
    if not leverage_rows:
        raise RuntimeError("LEVERAGE_INFO_EMPTY")
    cross_net = [r for r in leverage_rows if r.get("mgnMode") == "cross" and r.get("posSide") in (None, "", "net")]
    if not cross_net:
        cross_net = [r for r in leverage_rows if r.get("mgnMode") == "cross"]
    if not cross_net:
        raise RuntimeError("CROSS_LEVERAGE_NOT_FOUND")
    leverage_values = {dec(r.get("lever")) for r in cross_net}
    if leverage_values != {expected_leverage}:
        raise RuntimeError(
            "LEVERAGE_POLICY_MISMATCH actual="
            + ",".join(sorted(str(v) for v in leverage_values))
            + f" expected={expected_leverage}"
        )

    ticker = await c.public_get("/api/v5/market/ticker", {"instId": INST})
    if len(ticker) != 1:
        raise RuntimeError("TICKER_UNAVAILABLE")
    last = dec(ticker[0].get("last"))
    ct_val = dec(spec.get("ctVal"))
    notional = QTY * ct_val * last
    if last <= 0 or notional <= 0 or notional > MAX_NOTIONAL_USDT:
        raise RuntimeError(f"NOTIONAL_CAP_FAILED notional={notional}")

    max_rows = await c.private_get("/api/v5/account/max-size", {"instId": INST, "tdMode": "cross"})
    max_buy = max((dec(r.get("maxBuy")) for r in max_rows), default=Decimal("0"))
    if max_buy < QTY:
        raise RuntimeError(f"MAX_SIZE_INSUFFICIENT maxBuy={max_buy} required={QTY}")

    bal_rows = await c.private_get("/api/v5/account/balance", {"ccy": "USDT"})
    avail = Decimal("0")
    equity = Decimal("0")
    if bal_rows:
        equity = dec(bal_rows[0].get("totalEq"))
        for d in bal_rows[0].get("details") or []:
            if d.get("ccy") == "USDT":
                avail = max(dec(d.get("availBal")), dec(d.get("availEq")), dec(d.get("cashBal")))
    if avail <= 0 and equity <= 0:
        raise RuntimeError("NO_DEMO_USDT_BALANCE")

    open_clid = deterministic_client_id(attempt_id, "OPEN")
    close_clid = deterministic_client_id(attempt_id, "CLOSE")
    safe_clid = deterministic_client_id(attempt_id, "SAFE")

    return {
        "strategy": STRATEGY,
        "acctLv": str(cfg.get("acctLv")),
        "posMode": str(cfg.get("posMode")),
        "perm": sorted(perms),
        "api_label": cfg.get("label"),
        "private_swap_count": len(swaps),
        "qty_contracts": str(QTY),
        "ctVal": str(spec.get("ctVal")),
        "last_px": str(last),
        "approx_notional_usdt": str(notional),
        "max_buy_contracts": str(max_buy),
        "cross_leverage": sorted(str(v) for v in leverage_values),
        "expected_leverage": str(expected_leverage),
        "demo_usdt_available": str(avail),
        "demo_total_equity": str(equity),
        "existing_position": str(before_pos),
        "pending_orders": len(pending),
        "attempt_id": attempt_id,
        "client_ids": {"open": open_clid, "close": close_clid, "safe": safe_clid},
        "x_simulated_trading": True,
        "real_money_allowed": False,
    }


async def emergency_cleanup_owned_position(c: Client, attempt_id: str, open_submission_attempted: bool) -> dict:
    if not open_submission_attempted:
        return {"needed": False, "reason": "OPEN_SUBMISSION_NOT_ATTEMPTED"}

    # A POST can reach OKX even if our client loses the response. Give a market
    # order a short observation window before concluding that no exposure exists.
    deadline = time.time() + 8.0
    p = Decimal("0")
    while time.time() < deadline:
        p = await current_pos(c)
        if p != 0:
            break
        await asyncio.sleep(0.4)

    if p == 0:
        return {"needed": False, "reason": "NO_EXPOSURE_OBSERVED_AFTER_OPEN_ATTEMPT", "final_pos": "0"}
    if p < 0:
        return {"needed": False, "reason": "UNEXPECTED_SHORT_POSITION_REFUSE_CLEANUP", "observed_pos": str(p)}
    if p > QTY:
        return {
            "needed": False,
            "reason": "POSITION_EXCEEDS_D3_MAX_REFUSE_CLEANUP",
            "observed_pos": str(p),
            "d3_max_qty": str(QTY),
        }

    payload = {
        "instId": INST,
        "tdMode": "cross",
        "clOrdId": deterministic_client_id(attempt_id, "SAFE"),
        "side": "sell",
        "ordType": "market",
        "sz": format(p, "f"),
        "reduceOnly": True,
    }
    row = await c.private_post("/api/v5/trade/order", payload)
    od = await order_details(c, str(row.get("ordId")))
    final_p = await wait_pos(c, True)
    return {
        "needed": True,
        "scope": "D3_OWNED_POSITION_ONLY",
        "ordId": row.get("ordId"),
        "clOrdId": payload["clOrdId"],
        "state": od.get("state"),
        "reduced_qty": str(p),
        "final_pos": str(final_p),
    }


async def run() -> dict:
    c = Client()
    opening_ord = None
    closing_ord = None
    preflight = None
    open_submission_attempted = False
    close_submission_attempted = False
    attempt_id = os.getenv("MRC_D3_ATTEMPT_ID", "").strip()

    try:
        preflight = await validate_preflight(c)
        attempt_id = preflight["attempt_id"]
        print("D3_PREFLIGHT=" + json.dumps(preflight, separators=(",", ":")), flush=True)

        # Final fail-closed TOCTOU check immediately before the first POST.
        await assert_entry_still_clean(c)

        open_payload = {
            "instId": INST,
            "tdMode": "cross",
            "clOrdId": preflight["client_ids"]["open"],
            "side": "buy",
            "ordType": "market",
            "sz": format(QTY, "f"),
        }
        open_submission_attempted = True
        opening_ord = await c.private_post("/api/v5/trade/order", open_payload)
        open_id = str(opening_ord.get("ordId"))
        open_detail = await order_details(c, open_id)
        if open_detail.get("state") != "filled":
            raise RuntimeError(f"OPEN_NOT_FILLED state={open_detail.get('state')}")
        filled = dec(open_detail.get("accFillSz"))
        if filled <= 0 or filled > QTY:
            raise RuntimeError(f"OPEN_FILLED_SIZE_INVALID filled={filled} max={QTY}")

        pos_after_open = await wait_pos(c, False)
        if pos_after_open <= 0 or pos_after_open > QTY:
            raise RuntimeError(f"OPEN_POSITION_INVALID pos={pos_after_open} max={QTY}")

        close_payload = {
            "instId": INST,
            "tdMode": "cross",
            "clOrdId": preflight["client_ids"]["close"],
            "side": "sell",
            "ordType": "market",
            "sz": format(filled, "f"),
            "reduceOnly": True,
        }
        close_submission_attempted = True
        closing_ord = await c.private_post("/api/v5/trade/order", close_payload)
        close_id = str(closing_ord.get("ordId"))
        close_detail = await order_details(c, close_id)
        if close_detail.get("state") != "filled":
            raise RuntimeError(f"CLOSE_NOT_FILLED state={close_detail.get('state')}")
        final_pos = await wait_pos(c, True)
        if final_pos != 0:
            raise RuntimeError(f"FINAL_POSITION_NOT_FLAT pos={final_pos}")

        fills = await c.private_get("/api/v5/trade/fills", {"instType": "SWAP", "instId": INST})
        selected = []
        ids = {open_id, close_id}
        for f in fills:
            if str(f.get("ordId")) in ids:
                selected.append(
                    {
                        k: f.get(k)
                        for k in ("ordId", "clOrdId", "side", "fillPx", "fillSz", "fee", "feeCcy", "fillPnl", "fillTime")
                    }
                )

        out = {
            "status": "PASS",
            "strategy": STRATEGY,
            "environment": "OKX_DEMO_ONLY",
            "instrument": INST,
            "attempt_id": attempt_id,
            "preflight": preflight,
            "open": {k: open_detail.get(k) for k in ("ordId", "clOrdId", "state", "avgPx", "accFillSz", "side", "tdMode")},
            "position_after_open": str(pos_after_open),
            "close": {k: close_detail.get(k) for k in ("ordId", "clOrdId", "state", "avgPx", "accFillSz", "side", "tdMode", "pnl")},
            "final_position": str(final_pos),
            "fills": selected,
            "roundtrip_completed": True,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D3_ROUNDTRIP=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        return out

    except Exception as exc:
        cleanup = None
        try:
            cleanup = await emergency_cleanup_owned_position(c, attempt_id, open_submission_attempted)
        except Exception as cleanup_exc:
            cleanup = {
                "needed": bool(open_submission_attempted),
                "cleanup_error": type(cleanup_exc).__name__ + ": " + str(cleanup_exc),
            }

        fail = {
            "status": "FAIL",
            "strategy": STRATEGY,
            "error": type(exc).__name__ + ": " + str(exc),
            "attempt_id": attempt_id,
            "preflight": preflight,
            "open_submission_attempted": open_submission_attempted,
            "close_submission_attempted": close_submission_attempted,
            "opening_order_created": bool(opening_ord),
            "closing_order_created": bool(closing_ord),
            "cleanup": cleanup,
            "environment": "OKX_DEMO_ONLY",
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D3_ROUNDTRIP=" + json.dumps(fail, separators=(",", ":"), ensure_ascii=False), flush=True)
        raise
    finally:
        await c.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = b'{"ok":true,"service":"mrc-research-audit","mode":"D3_DEMO_ROUNDTRIP_V2_COMPLETE"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        return


def main():
    asyncio.run(run())
    print("D3_V2_COMPLETE_DEMO_ONLY_REAL_MONEY_BLOCKED", flush=True)
    port = int(os.getenv("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
