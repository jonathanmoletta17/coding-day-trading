from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

import httpx

BASE = "https://openapi.okx.com"
INST = "BTC-USDT-SWAP"
QTY = Decimal("0.01")
MAX_NOTIONAL_USDT = Decimal("20")
EXPECTED_LABEL = "MRC-SLOW-DEMO-GLOBAL"
ARM = "DEMO_BTC_MIN_ROUNDTRIP_V1"


def dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def sign(ts: str, method: str, request_path: str, body: str, secret: str) -> str:
    msg = f"{ts}{method.upper()}{request_path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


class Client:
    def __init__(self):
        self.key = os.getenv("OKX_DEMO_API_KEY", "").strip()
        self.secret = os.getenv("OKX_DEMO_SECRET_KEY", "").strip()
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE", "").strip()
        if not all((self.key, self.secret, self.passphrase)):
            raise RuntimeError("DEMO_CREDENTIALS_MISSING")
        self.h = httpx.AsyncClient(base_url=BASE, timeout=20, headers={"User-Agent": "MRC-OKX-D3-Demo/1.0"})

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


async def wait_pos(c: Client, want_zero: bool, timeout_s: float = 10.0) -> Decimal:
    deadline = time.time() + timeout_s
    last = Decimal("0")
    while time.time() < deadline:
        last = await current_pos(c)
        if (last == 0) == want_zero:
            return last
        await asyncio.sleep(0.4)
    return last


def client_id(kind: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%y%m%d%H%M%S%f")[:16]
    return f"MRC{kind}{stamp}"[:32]


async def validate_preflight(c: Client) -> dict:
    mode = os.getenv("MRC_EXECUTION_MODE", "").strip()
    enabled = os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0") == "1"
    kill = os.getenv("MRC_KILL_SWITCH", "1") != "0"
    arm = os.getenv("MRC_D3_ARM", "")
    if mode != "DEMO":
        raise RuntimeError("MODE_NOT_DEMO")
    if not enabled:
        raise RuntimeError("DEMO_EXECUTION_NOT_ENABLED")
    if kill:
        raise RuntimeError("KILL_SWITCH_ACTIVE")
    if arm != ARM:
        raise RuntimeError("D3_NOT_ARMED")

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
    if spec.get("state") != "live" or spec.get("ctType") != "linear" or spec.get("ctValCcy") != "BTC":
        raise RuntimeError("BTC_SWAP_METADATA_INVALID")
    lot = dec(spec.get("lotSz"))
    minimum = dec(spec.get("minSz"))
    if QTY < minimum or lot <= 0 or (QTY / lot) != (QTY / lot).to_integral_value():
        raise RuntimeError("TEST_QTY_INVALID")

    before_pos = await current_pos(c)
    if before_pos != 0:
        raise RuntimeError(f"EXISTING_POSITION_ABORT pos={before_pos}")

    ticker = await c.public_get("/api/v5/market/ticker", {"instId": INST})
    if len(ticker) != 1:
        raise RuntimeError("TICKER_UNAVAILABLE")
    last = dec(ticker[0].get("last"))
    ct_val = dec(spec.get("ctVal"))
    notional = QTY * ct_val * last
    if last <= 0 or notional <= 0 or notional > MAX_NOTIONAL_USDT:
        raise RuntimeError(f"NOTIONAL_CAP_FAILED notional={notional}")

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

    return {
        "acctLv": str(cfg.get("acctLv")),
        "posMode": str(cfg.get("posMode")),
        "perm": sorted(perms),
        "api_label": cfg.get("label"),
        "private_swap_count": len(swaps),
        "qty_contracts": str(QTY),
        "ctVal": str(spec.get("ctVal")),
        "last_px": str(last),
        "approx_notional_usdt": str(notional),
        "demo_usdt_available": str(avail),
        "demo_total_equity": str(equity),
        "existing_position": str(before_pos),
        "x_simulated_trading": True,
        "real_money_allowed": False,
    }


async def emergency_flatten(c: Client) -> dict:
    p = await current_pos(c)
    if p == 0:
        return {"needed": False, "final_pos": "0"}
    side = "sell" if p > 0 else "buy"
    payload = {
        "instId": INST,
        "tdMode": "cross",
        "clOrdId": client_id("SAFE"),
        "side": side,
        "ordType": "market",
        "sz": format(abs(p), "f"),
        "reduceOnly": True,
    }
    row = await c.private_post("/api/v5/trade/order", payload)
    od = await order_details(c, str(row.get("ordId")))
    final_p = await wait_pos(c, True)
    return {"needed": True, "ordId": row.get("ordId"), "state": od.get("state"), "final_pos": str(final_p)}


async def run() -> dict:
    c = Client()
    opening_ord = None
    closing_ord = None
    preflight = None
    try:
        preflight = await validate_preflight(c)
        print("D3_PREFLIGHT=" + json.dumps(preflight, separators=(",", ":")), flush=True)

        open_payload = {
            "instId": INST,
            "tdMode": "cross",
            "clOrdId": client_id("OPEN"),
            "side": "buy",
            "ordType": "market",
            "sz": format(QTY, "f"),
        }
        opening_ord = await c.private_post("/api/v5/trade/order", open_payload)
        open_id = str(opening_ord.get("ordId"))
        open_detail = await order_details(c, open_id)
        if open_detail.get("state") != "filled":
            raise RuntimeError(f"OPEN_NOT_FILLED state={open_detail.get('state')}")
        filled = dec(open_detail.get("accFillSz"))
        if filled <= 0:
            raise RuntimeError("OPEN_FILLED_SIZE_ZERO")
        pos_after_open = await wait_pos(c, False)
        if pos_after_open <= 0:
            raise RuntimeError(f"OPEN_POSITION_NOT_VISIBLE pos={pos_after_open}")

        close_payload = {
            "instId": INST,
            "tdMode": "cross",
            "clOrdId": client_id("CLOSE"),
            "side": "sell",
            "ordType": "market",
            "sz": format(filled, "f"),
            "reduceOnly": True,
        }
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
                selected.append({k: f.get(k) for k in ("ordId", "clOrdId", "side", "fillPx", "fillSz", "fee", "feeCcy", "fillPnl", "fillTime")})

        out = {
            "status": "PASS",
            "environment": "OKX_DEMO_ONLY",
            "instrument": INST,
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
            cleanup = await emergency_flatten(c)
        except Exception as cleanup_exc:
            cleanup = {"needed": True, "cleanup_error": type(cleanup_exc).__name__ + ": " + str(cleanup_exc)}
        fail = {
            "status": "FAIL",
            "error": type(exc).__name__ + ": " + str(exc),
            "preflight": preflight,
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
            body = b'{"ok":true,"service":"mrc-research-audit","mode":"D3_DEMO_ROUNDTRIP_COMPLETE"}'
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
    print("D3_COMPLETE_DEMO_ONLY_REAL_MONEY_BLOCKED", flush=True)
    port = int(os.getenv("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
