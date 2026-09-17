from __future__ import annotations

import asyncio
import json
import os
import time
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

EXPECTED_LEVERAGE = Decimal("3")


async def run() -> dict:
    # This gate MUST run while execution remains disabled.
    safe_env = {
        "execution_mode_demo": os.getenv("MRC_EXECUTION_MODE", "").strip() == "DEMO",
        "demo_execution_disabled": os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0").strip() == "0",
        "kill_switch_active": os.getenv("MRC_KILL_SWITCH", "1").strip() != "0",
        "diagnostic_only_active": os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1").strip() == "1",
    }
    if not all(safe_env.values()):
        raise RuntimeError("READINESS_REQUIRES_SAFE_LOCKS " + ",".join(k for k, v in safe_env.items() if not v))

    attempt_id = os.getenv("MRC_D3_ATTEMPT_ID", "").strip()
    declared_leverage = d3.dec(os.getenv("MRC_D3_EXPECTED_LEVERAGE", ""))
    if not d3.ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("D3_ATTEMPT_ID_INVALID")
    if declared_leverage != EXPECTED_LEVERAGE:
        raise RuntimeError(f"EXPECTED_LEVERAGE_POLICY_MISMATCH declared={declared_leverage} expected={EXPECTED_LEVERAGE}")

    c = d3.Client()
    try:
        server = await c.public_get("/api/v5/public/time")
        if not server:
            raise RuntimeError("OKX_TIME_EMPTY")
        drift_ms = abs(int(time.time() * 1000) - int(server[0]["ts"]))

        cfg_rows = await c.private_get("/api/v5/account/config")
        if not cfg_rows:
            raise RuntimeError("ACCOUNT_CONFIG_EMPTY")
        cfg = cfg_rows[0]
        perms = {p.strip() for p in str(cfg.get("perm") or "").split(",") if p.strip()}

        swaps = await c.private_get("/api/v5/account/instruments", {"instType": "SWAP"})
        private_ids = {r.get("instId") for r in swaps}

        pub = await c.public_get("/api/v5/public/instruments", {"instType": "SWAP", "instId": d3.INST})
        if len(pub) != 1:
            raise RuntimeError("BTC_SWAP_PUBLIC_NOT_UNIQUE")
        spec = pub[0]

        ticker = await c.public_get("/api/v5/market/ticker", {"instId": d3.INST})
        if len(ticker) != 1:
            raise RuntimeError("TICKER_UNAVAILABLE")
        last = d3.dec(ticker[0].get("last"))
        notional = d3.QTY * d3.dec(spec.get("ctVal")) * last

        pos = await d3.current_pos(c)
        pending = await d3.pending_orders(c)

        lev_rows = await c.private_get("/api/v5/account/leverage-info", {"instId": d3.INST, "mgnMode": "cross"})
        lev_values = {d3.dec(r.get("lever")) for r in lev_rows if r.get("mgnMode") == "cross"}

        max_rows = await c.private_get("/api/v5/account/max-size", {"instId": d3.INST, "tdMode": "cross"})
        max_buy = max((d3.dec(r.get("maxBuy")) for r in max_rows), default=Decimal("0"))

        bal = await c.private_get("/api/v5/account/balance", {"ccy": "USDT"})
        avail = Decimal("0")
        total_eq = Decimal("0")
        if bal:
            total_eq = d3.dec(bal[0].get("totalEq"))
            for detail in bal[0].get("details") or []:
                if detail.get("ccy") == "USDT":
                    avail = max(d3.dec(detail.get("availBal")), d3.dec(detail.get("availEq")), d3.dec(detail.get("cashBal")))

        client_ids = {k.lower(): d3.deterministic_client_id(attempt_id, k) for k in ("OPEN", "CLOSE", "SAFE")}

        gates = {
            **safe_env,
            "clock_ok": drift_ms < 10_000,
            "acctLv_futures": str(cfg.get("acctLv") or "") == "2",
            "posMode_net": str(cfg.get("posMode") or "") == "net_mode",
            "api_label_match": str(cfg.get("label") or "") == d3.EXPECTED_LABEL,
            "trade_permission": "trade" in perms,
            "btc_private_available": d3.INST in private_ids,
            "btc_live_linear_usdt": (
                spec.get("state") == "live"
                and spec.get("ctType") == "linear"
                and spec.get("ctValCcy") == "BTC"
                and spec.get("settleCcy") == "USDT"
            ),
            "account_flat": pos == 0,
            "no_pending_btc_orders": len(pending) == 0,
            "cross_leverage_exactly_3x": lev_values == {EXPECTED_LEVERAGE},
            "declared_leverage_exactly_3x": declared_leverage == EXPECTED_LEVERAGE,
            "qty_valid": d3.QTY >= d3.dec(spec.get("minSz")) and (d3.QTY / d3.dec(spec.get("lotSz"))) == (d3.QTY / d3.dec(spec.get("lotSz"))).to_integral_value(),
            "notional_capped": Decimal("0") < notional <= d3.MAX_NOTIONAL_USDT,
            "max_size_sufficient": max_buy >= d3.QTY,
            "demo_balance_present": avail > 0 or total_eq > 0,
            "client_ids_unique": len(set(client_ids.values())) == 3,
            "client_ids_within_limit": all(len(x) <= 32 and x.isalnum() for x in client_ids.values()),
            "order_submission_blocked": True,
            "private_post_not_performed": True,
            "real_money_execution_blocked": True,
        }

        out = {
            "status": "PASS" if all(gates.values()) else "FAIL",
            "attempt_id": attempt_id,
            "expected_arm_for_execution": d3.ARM,
            "account": {
                "acctLv": str(cfg.get("acctLv") or ""),
                "posMode": str(cfg.get("posMode") or ""),
                "perm": sorted(perms),
                "api_label": cfg.get("label"),
            },
            "private_swap_count": len(swaps),
            "position": str(pos),
            "pending_orders": len(pending),
            "cross_leverage": sorted(str(x) for x in lev_values),
            "qty_contracts": str(d3.QTY),
            "last_px": str(last),
            "approx_notional_usdt": str(notional),
            "max_buy_contracts": str(max_buy),
            "demo_usdt_available": str(avail),
            "demo_total_equity": str(total_eq),
            "client_ids": client_ids,
            "gates": gates,
            "order_submission_performed": False,
            "private_post_performed": False,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D3_READINESS=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        if out["status"] != "PASS":
            raise RuntimeError("D3_READINESS_FAILED " + ",".join(k for k, v in gates.items() if not v))
        return out
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = b'{"ok":true,"mode":"D3_READINESS_PASS_NO_ORDER"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        return


def main():
    asyncio.run(run())
    print("D3_READINESS_COMPLETE_NO_ORDER_SUBMITTED", flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
