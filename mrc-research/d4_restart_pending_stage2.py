from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3
import d4_safe_lifecycle as d4

ARM = "DEMO_D4_RESTART_PENDING_STAGE2_V1"


async def run() -> dict:
    if os.getenv("MRC_D4_RESTART_ARM", "").strip() != ARM:
        raise RuntimeError("RESTART_PENDING_STAGE2_NOT_ARMED")
    # Stage 2 intentionally runs under SAFE locks. New opens are disabled;
    # cancellation/reconciliation remains available as risk-reducing behavior.
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
    clid = d4.cid(attempt, "RESTARTPENDING")
    c = d3.Client()
    try:
        found = await d4.details_by_clid(c, clid)
        if not found or str(found.get("clOrdId")) != clid:
            raise RuntimeError("RESTART_STAGE2_EXISTING_ORDER_NOT_FOUND")
        state_before = str(found.get("state") or "")
        pos_before = await d3.current_pos(c)
        if d4.dec(found.get("accFillSz")) != 0 or pos_before != 0:
            raise RuntimeError(f"RESTART_STAGE2_UNEXPECTED_FILL state={state_before} accFillSz={found.get('accFillSz')} pos={pos_before}")
        if state_before not in {"live", "partially_filled"}:
            raise RuntimeError(f"RESTART_STAGE2_ORDER_NOT_PENDING state={state_before}")

        # Crucial invariant: discover exchange state first; no opening POST occurs.
        canceled = await d4.cancel_by_clid(c, clid)
        await d4.assert_flat(c, "RESTART_STAGE2_FINAL")
        out = {
            "status": "PASS",
            "attempt_id": attempt,
            "clOrdId": clid,
            "ordId": found.get("ordId"),
            "discovered_existing_order": True,
            "opening_post_performed": False,
            "state_before": state_before,
            "state_after": canceled.get("state"),
            "position_before": str(pos_before),
            "final": await d4.flat(c),
            "safe_locks": {
                "opening_disabled": True,
                "kill_switch_active": True,
                "diagnostic_only": True,
            },
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D4_RESTART_PENDING_STAGE2=" + json.dumps(out, separators=(",", ":")), flush=True)
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
        print("OKX_DEMO_D4_RESTART_PENDING_STAGE2=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
