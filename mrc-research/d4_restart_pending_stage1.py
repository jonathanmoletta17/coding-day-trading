from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3
import d4_safe_lifecycle as d4

ARM = "DEMO_D4_RESTART_PENDING_STAGE1_V1"


async def run() -> dict:
    if os.getenv("MRC_D4_RESTART_ARM", "").strip() != ARM:
        raise RuntimeError("RESTART_PENDING_STAGE1_NOT_ARMED")
    c = d3.Client()
    created = None
    try:
        pf = await d4.preflight(c)
        attempt = pf["attempt"]
        clid = d4.cid(attempt, "RESTARTPENDING")
        created = await d4.place_resting(c, clid, pf["resting_buy_px"])
        pending = await d3.pending_orders(c)
        owned = [x for x in pending if str(x.get("clOrdId")) == clid]
        if len(owned) != 1:
            raise RuntimeError(f"RESTART_STAGE1_PENDING_NOT_UNIQUE count={len(owned)}")
        if await d3.current_pos(c) != 0:
            raise RuntimeError("RESTART_STAGE1_POSITION_NOT_ZERO")
        out = {
            "status": "PASS_PENDING_LEFT_FOR_RESTART",
            "attempt_id": attempt,
            "clOrdId": clid,
            "ordId": created.get("ordId"),
            "state": created.get("state"),
            "px": created.get("px"),
            "sz": created.get("sz"),
            "position": "0",
            "owned_pending": 1,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D4_RESTART_PENDING_STAGE1=" + json.dumps(out, separators=(",", ":")), flush=True)
        return out
    except Exception:
        # Leave an exchange order behind ONLY after a fully successful stage-1 result.
        if created:
            try:
                await d4.post_ok(c, "/api/v5/trade/cancel-order", {"instId": d4.INST, "ordId": str(created.get("ordId"))})
            except Exception:
                pass
        raise
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    RESULT = {"status": "STARTING"}
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            ok = self.RESULT.get("status") == "PASS_PENDING_LEFT_FOR_RESTART"
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
        print("OKX_DEMO_D4_RESTART_PENDING_STAGE1=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
