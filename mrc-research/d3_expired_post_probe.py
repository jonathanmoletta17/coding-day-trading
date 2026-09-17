from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

RESULT: dict = {"status": "NOT_RUN"}


def safe_locks() -> dict:
    return {
        "mode_demo": os.getenv("MRC_EXECUTION_MODE", "").strip() == "DEMO",
        "execution_disabled": os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0").strip() == "0",
        "kill_active": os.getenv("MRC_KILL_SWITCH", "1").strip() != "0",
        "diagnostic_only": os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1").strip() == "1",
        "arm_empty": os.getenv("MRC_D3_ARM", "").strip() == "",
    }


async def run() -> dict:
    locks = safe_locks()
    if not all(locks.values()):
        raise RuntimeError("EXPIRED_PROBE_REQUIRES_SAFE_LOCKS")

    c = d3.Client()
    try:
        server = await c.public_get("/api/v5/public/time")
        if not server:
            raise RuntimeError("OKX_TIME_EMPTY")
        server_ms = int(server[0]["ts"])

        # Prove flat before any diagnostic POST.
        before_pos = await d3.current_pos(c)
        before_pending = await d3.pending_orders(c)
        if before_pos != 0 or before_pending:
            raise RuntimeError("EXPIRED_PROBE_ACCOUNT_NOT_CLEAN")

        probe_id = "MRCD3EXPIRED260917A"
        payload = {
            "instId": d3.INST,
            "tdMode": "cross",
            "clOrdId": probe_id,
            "side": "buy",
            "ordType": "market",
            "sz": format(d3.QTY, "f"),
        }
        path = "/api/v5/trade/order"
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        headers = c.headers(ts, "POST", path, body)
        # Intentionally expired by 60 seconds using OKX server time.
        headers["expTime"] = str(server_ms - 60_000)
        r = await c.h.post(path, content=body.encode(), headers=headers)
        try:
            response_json = r.json()
        except Exception:
            response_json = {"raw_text": r.text[:500]}

        # Reconcile immediately; an expired request must never create exposure.
        after_pos = await d3.current_pos(c)
        after_pending = await d3.pending_orders(c)
        hist = await c.private_get("/api/v5/trade/orders-history", {"instType": "SWAP", "instId": d3.INST, "limit": "100"})
        fills = await c.private_get("/api/v5/trade/fills", {"instType": "SWAP", "instId": d3.INST, "limit": "100"})
        order_matches = [x for x in hist if str(x.get("clOrdId") or "") == probe_id]
        fill_matches = [x for x in fills if str(x.get("clOrdId") or "") == probe_id]

        safe = after_pos == 0 and not after_pending and not order_matches and not fill_matches
        return {
            "status": "PASS" if safe else "FAIL",
            "probe": "EXPIRED_PLACE_ORDER_POST",
            "http_status": r.status_code,
            "okx_code": response_json.get("code") if isinstance(response_json, dict) else None,
            "okx_msg": response_json.get("msg") if isinstance(response_json, dict) else None,
            "response_data": response_json.get("data") if isinstance(response_json, dict) else None,
            "expired_ms_before_server_time": 60_000,
            "before_position": str(before_pos),
            "after_position": str(after_pos),
            "before_pending": len(before_pending),
            "after_pending": len(after_pending),
            "history_matches": len(order_matches),
            "fill_matches": len(fill_matches),
            "safe_locks": locks,
            "request_was_deliberately_expired": True,
            "live_order_created": not safe,
        }
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps({"ok": RESULT.get("status") == "PASS", "mode": "D3_EXPIRED_POST_PROBE", "result": RESULT}, separators=(",", ":"), ensure_ascii=False).encode()
            self.send_response(200 if RESULT.get("status") == "PASS" else 503)
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
    global RESULT
    try:
        RESULT = asyncio.run(run())
    except Exception as exc:
        RESULT = {"status": "FAIL", "error": type(exc).__name__ + ": " + str(exc), "safe_locks": safe_locks()}
    print("OKX_DEMO_D3_EXPIRED_POST_PROBE=" + json.dumps(RESULT, separators=(",", ":"), ensure_ascii=False), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
