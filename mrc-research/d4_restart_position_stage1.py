from __future__ import annotations

import asyncio
import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3
import d4_safe_lifecycle as d4

ARM = "DEMO_D4_RESTART_POSITION_STAGE1_V1"


def pos_cid(attempt: str, kind: str) -> str:
    return d4.cid(attempt, "POS" + kind)


async def emergency_flat(c: d3.Client, attempt: str) -> dict:
    p = await d3.current_pos(c)
    if p <= 0:
        return {"needed": False, "observed": str(p)}
    if p > d4.QTY:
        return {"needed": False, "refused": "POSITION_EXCEEDS_D4_QTY", "observed": str(p)}
    row = await d4.post_ok(c, "/api/v5/trade/order", {
        "instId": d4.INST, "tdMode": "cross", "clOrdId": pos_cid(attempt, "SAFE"),
        "side": "sell", "ordType": "market", "sz": format(p, "f"), "reduceOnly": True,
    })
    final = await d3.wait_pos(c, want_zero=True, timeout_s=10)
    return {"needed": True, "ordId": row.get("ordId"), "final_pos": str(final)}


async def run() -> dict:
    if os.getenv("MRC_D4_RESTART_ARM", "").strip() != ARM:
        raise RuntimeError("RESTART_POSITION_STAGE1_NOT_ARMED")
    c = d3.Client()
    opened = False
    attempt = os.getenv("MRC_D4_ATTEMPT_ID", "").strip()
    try:
        pf = await d4.preflight(c)
        attempt = pf["attempt"]
        clid = pos_cid(attempt, "OPEN")
        row = await d4.post_ok(c, "/api/v5/trade/order", {
            "instId": d4.INST, "tdMode": "cross", "clOrdId": clid,
            "side": "buy", "ordType": "market", "sz": str(d4.QTY),
        })
        opened = True
        p = await d3.wait_pos(c, want_zero=False, timeout_s=10)
        if p != d4.QTY:
            raise RuntimeError(f"RESTART_POSITION_STAGE1_POS_MISMATCH pos={p} expected={d4.QTY}")
        detail = await d3.order_details(c, str(row.get("ordId")), timeout_s=8)
        if str(detail.get("state")) != "filled" or d4.dec(detail.get("accFillSz")) != d4.QTY:
            raise RuntimeError(f"RESTART_POSITION_STAGE1_OPEN_NOT_FILLED {detail}")
        pending = await d3.pending_orders(c)
        if pending:
            raise RuntimeError(f"RESTART_POSITION_STAGE1_UNEXPECTED_PENDING count={len(pending)}")
        out = {
            "status": "PASS_POSITION_LEFT_FOR_RESTART",
            "attempt_id": attempt,
            "clOrdId": clid,
            "ordId": row.get("ordId"),
            "state": detail.get("state"),
            "avgPx": detail.get("avgPx"),
            "accFillSz": detail.get("accFillSz"),
            "position": str(p),
            "pending": 0,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D4_RESTART_POSITION_STAGE1=" + json.dumps(out, separators=(",", ":")), flush=True)
        return out
    except Exception:
        if opened and attempt:
            try:
                cleanup = await emergency_flat(c, attempt)
                print("D4_RESTART_POSITION_STAGE1_EMERGENCY=" + json.dumps(cleanup, separators=(",", ":")), flush=True)
            except Exception as ce:
                print("D4_RESTART_POSITION_STAGE1_EMERGENCY_ERROR=" + repr(ce), flush=True)
        raise
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    RESULT = {"status": "STARTING"}
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps(self.RESULT, separators=(",", ":")).encode()
            self.send_response(200 if self.RESULT.get("status") == "PASS_POSITION_LEFT_FOR_RESTART" else 503)
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
        print("OKX_DEMO_D4_RESTART_POSITION_STAGE1=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
