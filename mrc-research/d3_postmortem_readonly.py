from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

RESULT: dict = {"status": "NOT_RUN"}


async def run() -> dict:
    locks = {
        "demo_execution_disabled": os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0").strip() == "0",
        "kill_switch_active": os.getenv("MRC_KILL_SWITCH", "1").strip() != "0",
        "diagnostic_only_active": os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1").strip() == "1",
        "arm_empty": os.getenv("MRC_D3_ARM", "").strip() == "",
    }
    if not all(locks.values()):
        raise RuntimeError("POSTMORTEM_REQUIRES_SAFE_LOCKS")

    attempt_id = os.getenv("MRC_D3_ATTEMPT_ID", "").strip()
    if not d3.ATTEMPT_RE.fullmatch(attempt_id):
        raise RuntimeError("D3_ATTEMPT_ID_INVALID")

    ids = {k.lower(): d3.deterministic_client_id(attempt_id, k) for k in ("OPEN", "CLOSE", "SAFE")}
    wanted = set(ids.values())

    c = d3.Client()
    try:
        position = await d3.current_pos(c)
        pending = await d3.pending_orders(c)
        history = await c.private_get(
            "/api/v5/trade/orders-history",
            {"instType": "SWAP", "instId": d3.INST, "limit": "100"},
        )
        fills = await c.private_get(
            "/api/v5/trade/fills",
            {"instType": "SWAP", "instId": d3.INST, "limit": "100"},
        )

        matched_orders = [
            {
                k: row.get(k)
                for k in ("ordId", "clOrdId", "state", "side", "avgPx", "accFillSz", "fee", "feeCcy", "pnl", "cTime", "uTime")
            }
            for row in history
            if str(row.get("clOrdId") or "") in wanted
        ]
        matched_fills = [
            {
                k: row.get(k)
                for k in ("ordId", "clOrdId", "tradeId", "side", "fillPx", "fillSz", "fee", "feeCcy", "fillPnl", "fillTime")
            }
            for row in fills
            if str(row.get("clOrdId") or "") in wanted
        ]

        seen_ids = {str(x.get("clOrdId")) for x in matched_orders + matched_fills}
        out = {
            "status": "PASS" if position == 0 and not pending else "FAIL",
            "attempt_id": attempt_id,
            "client_ids": ids,
            "position": str(position),
            "pending_btc_orders": len(pending),
            "matched_orders": matched_orders,
            "matched_fills": matched_fills,
            "open_seen": ids["open"] in seen_ids,
            "close_seen": ids["close"] in seen_ids,
            "safe_seen": ids["safe"] in seen_ids,
            "any_d3_order_evidence": bool(matched_orders or matched_fills),
            "safe_locks": locks,
            "private_post_performed": False,
        }
        print("OKX_DEMO_D3_POSTMORTEM=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        return out
    finally:
        await c.close()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps({"ok": True, "mode": "D3_POSTMORTEM_READONLY_DIAGNOSTIC", "result": RESULT}, separators=(",", ":")).encode()
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
    global RESULT
    try:
        RESULT = asyncio.run(run())
    except Exception as exc:
        RESULT = {"status": "DIAGNOSTIC_ERROR", "error": type(exc).__name__ + ": " + str(exc)}
        print("OKX_DEMO_D3_POSTMORTEM_DIAGNOSTIC=" + json.dumps(RESULT, separators=(",", ":"), ensure_ascii=False), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
