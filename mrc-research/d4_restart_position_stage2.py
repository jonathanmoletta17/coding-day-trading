from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3
import d4_safe_lifecycle as d4
import d4_restart_position_stage1 as s1

ARM = "DEMO_D4_RESTART_POSITION_STAGE2_V1"


async def run() -> dict:
    if os.getenv("MRC_D4_RESTART_ARM", "").strip() != ARM:
        raise RuntimeError("RESTART_POSITION_STAGE2_NOT_ARMED")
    if os.getenv("MRC_EXECUTION_MODE", "").strip() != "DEMO":
        raise RuntimeError("MODE_NOT_DEMO")
    if os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0") != "0":
        raise RuntimeError("STAGE2_REQUIRES_OPENING_DISABLED")
    if os.getenv("MRC_KILL_SWITCH", "1") != "1":
        raise RuntimeError("STAGE2_REQUIRES_KILL_SWITCH")
    if os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1") != "1":
        raise RuntimeError("STAGE2_REQUIRES_DIAGNOSTIC_ONLY")

    attempt = os.getenv("MRC_D4_ATTEMPT_ID", "").strip()
    if not d3.ATTEMPT_RE.fullmatch(attempt):
        raise RuntimeError("D4_ATTEMPT_ID_INVALID")
    open_clid = s1.pos_cid(attempt, "OPEN")
    close_clid = s1.pos_cid(attempt, "CLOSE")

    c = d3.Client()
    try:
        p = await d3.current_pos(c)
        if p <= 0 or p > d4.QTY:
            raise RuntimeError(f"RESTART_POSITION_STAGE2_OWNERSHIP_BOUND_FAILED pos={p}")
        pending = await d3.pending_orders(c)
        if pending:
            raise RuntimeError(f"RESTART_POSITION_STAGE2_UNEXPECTED_PENDING count={len(pending)}")

        history = await c.private_get("/api/v5/trade/orders-history", {"instType": "SWAP", "instId": d4.INST, "limit": "100"})
        owned_open = [x for x in history if str(x.get("clOrdId")) == open_clid and str(x.get("state")) == "filled"]
        if len(owned_open) != 1:
            raise RuntimeError(f"RESTART_POSITION_STAGE2_OPEN_OWNERSHIP_NOT_PROVEN count={len(owned_open)}")
        if d4.dec(owned_open[0].get("accFillSz")) != p:
            raise RuntimeError("RESTART_POSITION_STAGE2_FILLED_QTY_MISMATCH")

        # Kill switch remains active: no new opening submission is possible. The only
        # trade POST permitted here is reduceOnly risk-reducing flattening.
        row = await d4.post_ok(c, "/api/v5/trade/order", {
            "instId": d4.INST, "tdMode": "cross", "clOrdId": close_clid,
            "side": "sell", "ordType": "market", "sz": format(p, "f"), "reduceOnly": True,
        })
        final = await d3.wait_pos(c, want_zero=True, timeout_s=10)
        if final != 0:
            raise RuntimeError(f"RESTART_POSITION_STAGE2_FLATTEN_FAILED pos={final}")
        detail = await d3.order_details(c, str(row.get("ordId")), timeout_s=8)
        if str(detail.get("state")) != "filled":
            raise RuntimeError(f"RESTART_POSITION_STAGE2_CLOSE_NOT_FILLED {detail}")
        await d4.assert_flat(c, "RESTART_POSITION_STAGE2_FINAL")

        out = {
            "status": "PASS",
            "attempt_id": attempt,
            "discovered_exchange_position": True,
            "opening_post_performed": False,
            "owned_open_clOrdId": open_clid,
            "owned_open_ordId": owned_open[0].get("ordId"),
            "position_before": str(p),
            "reduce_only_close": {
                "clOrdId": close_clid,
                "ordId": row.get("ordId"),
                "state": detail.get("state"),
                "avgPx": detail.get("avgPx"),
                "accFillSz": detail.get("accFillSz"),
                "pnl": detail.get("pnl"),
            },
            "final": await d4.flat(c),
            "safe_locks": {"opening_disabled": True, "kill_switch_active": True, "diagnostic_only": True},
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D4_RESTART_POSITION_STAGE2=" + json.dumps(out, separators=(",", ":")), flush=True)
        return out
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    RESULT = {"status": "STARTING"}
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps(self.RESULT, separators=(",", ":")).encode()
            self.send_response(200 if self.RESULT.get("status") == "PASS" else 503)
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
        print("OKX_DEMO_D4_RESTART_POSITION_STAGE2=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
