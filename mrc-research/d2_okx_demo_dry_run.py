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
EXPECTED_LABEL = "MRC-SLOW-DEMO-GLOBAL"
TARGETS = ("BTC-USDT-SWAP", "ETH-USDT-SWAP")
ROUNDTRIP_INST = "BTC-USDT-SWAP"
ROUNDTRIP_QTY = Decimal("0.01")
MAX_NOTIONAL_USDT = Decimal("20")


def dec(v, default="0") -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else default))
    except (InvalidOperation, ValueError):
        return Decimal(default)


def sign(ts: str, method: str, request_path: str, body: str, secret: str) -> str:
    msg = f"{ts}{method.upper()}{request_path}{body}".encode()
    return base64.b64encode(hmac.new(secret.encode(), msg, hashlib.sha256).digest()).decode()


def deterministic_clordid(leg: str) -> str:
    seed = f"SLOW_TREND_BREAKOUT_V1|D2|{ROUNDTRIP_INST}|cross|{leg}|market|{ROUNDTRIP_QTY}|v1"
    digest = hashlib.sha256(seed.encode()).hexdigest()[:20].upper()
    return f"MRCD2{leg[:1].upper()}{digest}"[:32]


class Client:
    def __init__(self):
        self.key = os.getenv("OKX_DEMO_API_KEY", "").strip()
        self.secret = os.getenv("OKX_DEMO_SECRET_KEY", "").strip()
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE", "").strip()
        if not all((self.key, self.secret, self.passphrase)):
            raise RuntimeError("DEMO_CREDENTIALS_MISSING")
        self.h = httpx.AsyncClient(base_url=BASE, timeout=20, headers={"User-Agent": "MRC-OKX-D2-DryRun/1.0"})

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

    async def close(self):
        await self.h.aclose()


def env_safety() -> dict:
    mode = os.getenv("MRC_EXECUTION_MODE", "").strip()
    enabled = os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0").strip()
    kill = os.getenv("MRC_KILL_SWITCH", "1").strip()
    diagnostic = os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1").strip()
    return {
        "execution_mode_demo": mode == "DEMO",
        "demo_execution_disabled": enabled == "0",
        "kill_switch_active": kill != "0",
        "diagnostic_only_active": diagnostic == "1",
    }


async def validate() -> dict:
    safety = env_safety()
    if not all(safety.values()):
        raise RuntimeError("D2_SAFETY_ENV_FAILED " + ",".join(k for k, v in safety.items() if not v))

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
        perms = {p.strip() for p in str(cfg.get("perm") or "").split(",") if p.strip()}

        swaps = await c.private_get("/api/v5/account/instruments", {"instType": "SWAP"})
        private_ids = {r.get("instId") for r in swaps}

        positions = await c.private_get("/api/v5/account/positions", {"instType": "SWAP"})
        target_positions = [
            {"instId": r.get("instId"), "pos": str(r.get("pos") or "0"), "posSide": r.get("posSide"), "mgnMode": r.get("mgnMode")}
            for r in positions if r.get("instId") in TARGETS and dec(r.get("pos")) != 0
        ]

        pending = await c.private_get("/api/v5/trade/orders-pending", {"instType": "SWAP"})
        target_pending = [
            {"instId": r.get("instId"), "ordId": r.get("ordId"), "clOrdId": r.get("clOrdId"), "state": r.get("state")}
            for r in pending if r.get("instId") in TARGETS
        ]

        balance_rows = await c.private_get("/api/v5/account/balance", {"ccy": "USDT"})
        avail = Decimal("0")
        total_eq = Decimal("0")
        if balance_rows:
            total_eq = dec(balance_rows[0].get("totalEq"))
            for d in balance_rows[0].get("details") or []:
                if d.get("ccy") == "USDT":
                    avail = max(dec(d.get("availBal")), dec(d.get("availEq")), dec(d.get("cashBal")))

        instruments = {}
        leverage = {}
        for inst_id in TARGETS:
            pub = await c.public_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": inst_id})
            if len(pub) != 1:
                raise RuntimeError(f"PUBLIC_INSTRUMENT_NOT_UNIQUE {inst_id} count={len(pub)}")
            spec = pub[0]
            tick = await c.public_get("/api/v5/market/ticker", {"instId": inst_id})
            if len(tick) != 1:
                raise RuntimeError(f"TICKER_UNAVAILABLE {inst_id}")
            lev = await c.private_get("/api/v5/account/leverage-info", {"instId": inst_id, "mgnMode": "cross"})
            leverage[inst_id] = [
                {"mgnMode": x.get("mgnMode"), "posSide": x.get("posSide"), "lever": x.get("lever")}
                for x in lev
            ]
            instruments[inst_id] = {
                "private_available": inst_id in private_ids,
                "state": spec.get("state"),
                "ctType": spec.get("ctType"),
                "ctVal": spec.get("ctVal"),
                "ctValCcy": spec.get("ctValCcy"),
                "lotSz": spec.get("lotSz"),
                "minSz": spec.get("minSz"),
                "settleCcy": spec.get("settleCcy"),
                "last": tick[0].get("last"),
            }

        spec = instruments[ROUNDTRIP_INST]
        qty = ROUNDTRIP_QTY
        lot = dec(spec["lotSz"])
        minimum = dec(spec["minSz"])
        ct_val = dec(spec["ctVal"])
        last = dec(spec["last"])
        if lot <= 0 or minimum <= 0 or ct_val <= 0 or last <= 0:
            raise RuntimeError("ROUNDTRIP_METADATA_INVALID")
        if qty < minimum or (qty / lot) != (qty / lot).to_integral_value():
            raise RuntimeError("ROUNDTRIP_QTY_INVALID")
        notional = qty * ct_val * last

        max_rows = await c.private_get("/api/v5/account/max-size", {"instId": ROUNDTRIP_INST, "tdMode": "cross"})
        max_buy = max((dec(r.get("maxBuy")) for r in max_rows), default=Decimal("0"))
        max_sell = max((dec(r.get("maxSell")) for r in max_rows), default=Decimal("0"))

        open_payload = {
            "instId": ROUNDTRIP_INST,
            "tdMode": "cross",
            "clOrdId": deterministic_clordid("OPEN"),
            "side": "buy",
            "ordType": "market",
            "sz": format(qty, "f"),
        }
        close_payload = {
            "instId": ROUNDTRIP_INST,
            "tdMode": "cross",
            "clOrdId": deterministic_clordid("CLOSE"),
            "side": "sell",
            "ordType": "market",
            "sz": format(qty, "f"),
            "reduceOnly": True,
        }

        gates = {
            **safety,
            "clock_ok": drift_ms < 10_000,
            "acctLv_futures": str(cfg.get("acctLv") or "") == "2",
            "posMode_net": str(cfg.get("posMode") or "") == "net_mode",
            "api_label_match": str(cfg.get("label") or "") == EXPECTED_LABEL,
            "trade_permission_verified": "trade" in perms,
            "read_permission_verified": ("read_only" in perms) or ("trade" in perms),
            "private_swap_count_nonzero": len(swaps) > 0,
            "btc_private_available": ROUNDTRIP_INST in private_ids,
            "eth_private_available": "ETH-USDT-SWAP" in private_ids,
            "targets_live": all(instruments[i]["state"] == "live" for i in TARGETS),
            "targets_linear_usdt": all(
                instruments[i]["ctType"] == "linear" and instruments[i]["settleCcy"] == "USDT"
                for i in TARGETS
            ),
            "no_target_positions": len(target_positions) == 0,
            "no_target_pending_orders": len(target_pending) == 0,
            "demo_usdt_present": avail > 0 or total_eq > 0,
            "roundtrip_qty_valid": qty >= minimum and (qty / lot) == (qty / lot).to_integral_value(),
            "roundtrip_notional_capped": Decimal("0") < notional <= MAX_NOTIONAL_USDT,
            "max_size_sufficient": max_buy >= qty,
            "leverage_info_readable": bool(leverage[ROUNDTRIP_INST]),
            "order_payload_built_in_memory": True,
            "order_submission_blocked": True,
            "real_money_execution_blocked": True,
        }

        out = {
            "status": "PASS" if all(v is True for v in gates.values()) else "FAIL",
            "clock_drift_ms": drift_ms,
            "account": {
                "acctLv": str(cfg.get("acctLv") or ""),
                "posMode": str(cfg.get("posMode") or ""),
                "perm": sorted(perms),
                "api_label": cfg.get("label"),
            },
            "private_swap_count": len(swaps),
            "instruments": instruments,
            "cross_leverage": leverage,
            "target_nonzero_positions": target_positions,
            "target_pending_orders": target_pending,
            "demo_usdt_available": str(avail),
            "demo_total_equity": str(total_eq),
            "roundtrip": {
                "instrument": ROUNDTRIP_INST,
                "qty_contracts": str(qty),
                "approx_notional_usdt": str(notional),
                "max_buy_contracts": str(max_buy),
                "max_sell_contracts": str(max_sell),
                "open_payload": open_payload,
                "close_payload": close_payload,
            },
            "gates": gates,
            "order_submission_performed": False,
            "private_post_performed": False,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D2_DRY_RUN=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        if out["status"] != "PASS":
            failed = [k for k, v in gates.items() if v is not True]
            raise RuntimeError("D2_GATE_FAILED " + ",".join(failed))
        return out
    finally:
        await c.close()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = b'{"ok":true,"service":"mrc-research-audit","mode":"OKX_DEMO_D2_DRY_RUN_PASS"}'
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
    print("D2_COMPLETE_NO_ORDER_SUBMITTED", flush=True)
    port = int(os.getenv("PORT", "8080"))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
