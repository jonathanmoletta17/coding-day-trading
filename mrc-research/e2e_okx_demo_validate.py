from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode

import httpx

BASE = "https://openapi.okx.com"
TARGETS = (
    ("BTC-USDT-SWAP", Decimal("0.001")),
    ("ETH-USDT-SWAP", Decimal("0.01")),
)


def signature(ts: str, method: str, request_path: str, body: str, secret: str) -> str:
    prehash = f"{ts}{method.upper()}{request_path}{body}".encode()
    digest = hmac.new(secret.encode(), prehash, hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def headers(key: str, secret: str, passphrase: str, ts: str, method: str, path: str, body: str = "") -> dict:
    return {
        "Content-Type": "application/json",
        "OK-ACCESS-KEY": key,
        "OK-ACCESS-SIGN": signature(ts, method, path, body, secret),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": passphrase,
        "x-simulated-trading": "1",
    }


class Client:
    def __init__(self):
        self.key = os.getenv("OKX_DEMO_API_KEY", "").strip()
        self.secret = os.getenv("OKX_DEMO_SECRET_KEY", "").strip()
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE", "").strip()
        self.creds_present = bool(self.key and self.secret and self.passphrase)
        if not self.creds_present:
            raise RuntimeError("DEMO_CREDENTIALS_MISSING")
        self.h = httpx.AsyncClient(base_url=BASE, timeout=20, headers={"User-Agent": "MRC-OKX-Demo-E2E/2.0"})

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
        request_path = path + ("?" + qs if qs else "")
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        r = await self.h.get(path, params=params, headers=headers(self.key, self.secret, self.passphrase, ts, "GET", request_path))
        r.raise_for_status()
        j = r.json()
        if j.get("code") != "0":
            raise RuntimeError(f"OKX_PRIVATE_ERROR {j.get('code')} {j.get('msg')}")
        return j.get("data") or []

    async def close(self):
        await self.h.aclose()


def contracts_for_base_qty(base_qty: Decimal, row: dict) -> str:
    if row.get("state") != "live":
        raise RuntimeError("INSTRUMENT_NOT_LIVE")
    if row.get("ctType") != "linear":
        raise RuntimeError("UNSUPPORTED_CONTRACT_TYPE")
    ct_val = Decimal(str(row.get("ctVal")))
    lot = Decimal(str(row.get("lotSz")))
    minimum = Decimal(str(row.get("minSz")))
    if ct_val <= 0 or lot <= 0 or minimum <= 0:
        raise RuntimeError("INVALID_INSTRUMENT_METADATA")
    raw = base_qty / ct_val
    qty = (raw / lot).to_integral_value(rounding=ROUND_DOWN) * lot
    if qty < minimum:
        raise RuntimeError("BELOW_MIN_CONTRACT_SIZE")
    return format(qty.normalize(), "f")


async def validate() -> dict:
    c = Client()
    try:
        timerows = await c.public_get("/api/v5/public/time")
        if not timerows:
            raise RuntimeError("OKX_TIME_EMPTY")
        server_ms = int(timerows[0]["ts"])
        drift_ms = abs(int(time.time() * 1000) - server_ms)

        cfgrows = await c.private_get("/api/v5/account/config")
        if not cfgrows:
            raise RuntimeError("ACCOUNT_CONFIG_EMPTY")
        cfg = cfgrows[0]
        acct_lv = str(cfg.get("acctLv") or "")
        pos_mode = str(cfg.get("posMode") or "")
        perm_raw = str(cfg.get("perm") or "")
        perms = {p.strip() for p in perm_raw.split(",") if p.strip()}

        swaps = await c.private_get("/api/v5/account/instruments", {"instType": "SWAP"})
        private_ids = {x.get("instId") for x in swaps}

        target_rows = []
        for inst_id, base_qty in TARGETS:
            rows = await c.public_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst_id})
            if len(rows) != 1:
                raise RuntimeError(f"PUBLIC_INSTRUMENT_NOT_UNIQUE {inst_id} count={len(rows)}")
            x = rows[0]
            ct_val_ccy = str(x.get("ctValCcy") or "")
            expected_ccy = "BTC" if inst_id.startswith("BTC-") else "ETH"
            if ct_val_ccy != expected_ccy:
                raise RuntimeError(f"CTVAL_CCY_MISMATCH {inst_id}")
            contracts = contracts_for_base_qty(base_qty, x)
            target_rows.append({
                "instId": inst_id,
                "private_available": inst_id in private_ids,
                "state": x.get("state"),
                "ctType": x.get("ctType"),
                "ctVal": x.get("ctVal"),
                "ctValCcy": x.get("ctValCcy"),
                "lotSz": x.get("lotSz"),
                "minSz": x.get("minSz"),
                "settleCcy": x.get("settleCcy"),
                "sample_base_qty": str(base_qty),
                "sample_contracts": contracts,
            })

        gates = {
            "credentials_present": True,
            "clock_ok": drift_ms < 10_000,
            "account_mode_verified": acct_lv in {"2", "3", "4"},
            "trade_permission_verified": "trade" in perms,
            "read_permission_verified": ("read_only" in perms) or ("trade" in perms),
            "btc_swap_private_available": "BTC-USDT-SWAP" in private_ids,
            "eth_swap_private_available": "ETH-USDT-SWAP" in private_ids,
            "targets_live": all(x["state"] == "live" for x in target_rows),
            "contracts_conversion_verified": all(Decimal(x["sample_contracts"]) > 0 for x in target_rows),
            "demo_header_required": True,
            "order_submission_blocked": True,
            "real_money_execution_blocked": True,
        }

        out = {
            "status": "PASS" if all(v is True for v in gates.values()) else "FAIL",
            "clock_drift_ms": drift_ms,
            "account": {
                "acctLv": acct_lv,
                "posMode": pos_mode,
                "perm": sorted(perms),
                "api_label": cfg.get("label"),
                "ip_bound": bool(str(cfg.get("ip") or "").strip()),
            },
            "private_swap_count": len(swaps),
            "targets": target_rows,
            "gates": gates,
            "order_submission_performed": False,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_E2E=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        if out["status"] != "PASS":
            failed = [k for k, v in gates.items() if v is not True]
            raise RuntimeError("E2E_GATE_FAILED " + ",".join(failed))
        return out
    finally:
        await c.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = b'{"ok":true,"service":"mrc-research-audit","mode":"OKX_DEMO_E2E_PASS"}'
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
    asyncio.run(validate())
    print("E2E_COMPLETE_NO_ORDER_SUBMITTED", flush=True)
    port = int(os.getenv("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
