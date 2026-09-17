from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3
import d4_safe_lifecycle as d4
import d4_restart_position_stage1 as pos1

ATTEMPT_SAFE = "D4BTC260917A"
ATTEMPT_PENDING = "D4BTC260917R"
ATTEMPT_POSITION = "D4BTC260917P"


async def run() -> dict:
    locks = {
        "mode_demo": os.getenv("MRC_EXECUTION_MODE", "").strip() == "DEMO",
        "opening_disabled": os.getenv("MRC_DEMO_EXECUTION_ENABLED", "0") == "0",
        "kill_switch_active": os.getenv("MRC_KILL_SWITCH", "1") == "1",
        "diagnostic_only": os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", "1") == "1",
        "d4_arm_empty": os.getenv("MRC_D4_ARM", "").strip() == "",
    }
    if not all(locks.values()):
        raise RuntimeError("FINAL_AUDIT_REQUIRES_SAFE_LOCKS")

    c = d3.Client()
    try:
        pos = await d3.current_pos(c)
        pending = await d3.pending_orders(c)
        lev = await c.private_get("/api/v5/account/leverage-info", {"instId": d4.INST, "mgnMode": "cross"})
        lev_values = sorted({str(d4.dec(x.get("lever"))) for x in lev if x.get("mgnMode") == "cross"})
        history = await c.private_get("/api/v5/trade/orders-history", {"instType": "SWAP", "instId": d4.INST, "limit": "100"})
        fills = await c.private_get("/api/v5/trade/fills", {"instType": "SWAP", "instId": d4.INST, "limit": "100"})

        expected = {
            "safe_cancel_ordid": d4.cid(ATTEMPT_SAFE, "ORDID"),
            "safe_cancel_clid": d4.cid(ATTEMPT_SAFE, "CLID"),
            "safe_ambiguous": d4.cid(ATTEMPT_SAFE, "AMBIG"),
            "safe_expired": d4.cid(ATTEMPT_SAFE, "EXPIRED"),
            "restart_pending": d4.cid(ATTEMPT_PENDING, "RESTARTPENDING"),
            "restart_position_open": pos1.pos_cid(ATTEMPT_POSITION, "OPEN"),
            "restart_position_close": pos1.pos_cid(ATTEMPT_POSITION, "CLOSE"),
        }
        by_clid = {str(x.get("clOrdId")): x for x in history if x.get("clOrdId")}
        fill_counts = {}
        for f in fills:
            k = str(f.get("clOrdId") or "")
            fill_counts[k] = fill_counts.get(k, 0) + 1

        evidence = {}
        for name, clid in expected.items():
            row = by_clid.get(clid)
            evidence[name] = {
                "clOrdId": clid,
                "seen": bool(row),
                "ordId": row.get("ordId") if row else None,
                "state": row.get("state") if row else None,
                "side": row.get("side") if row else None,
                "ordType": row.get("ordType") if row else None,
                "accFillSz": row.get("accFillSz") if row else None,
                "avgPx": row.get("avgPx") if row else None,
                "pnl": row.get("pnl") if row else None,
                "fills": fill_counts.get(clid, 0),
            }

        checks = {
            "flat": pos == 0,
            "no_pending": len(pending) == 0,
            "leverage_3x": lev_values == ["3"],
            "safe_cancel_ordid_canceled": evidence["safe_cancel_ordid"]["state"] == "canceled",
            "safe_cancel_clid_canceled": evidence["safe_cancel_clid"]["state"] == "canceled",
            "safe_ambiguous_canceled": evidence["safe_ambiguous"]["state"] == "canceled",
            "expired_has_no_order": evidence["safe_expired"]["seen"] is False,
            "restart_pending_canceled": evidence["restart_pending"]["state"] == "canceled",
            "restart_position_open_filled": evidence["restart_position_open"]["state"] == "filled" and d4.dec(evidence["restart_position_open"]["accFillSz"]) == d4.QTY,
            "restart_position_close_filled": evidence["restart_position_close"]["state"] == "filled" and d4.dec(evidence["restart_position_close"]["accFillSz"]) == d4.QTY,
            "position_open_fill_seen": evidence["restart_position_open"]["fills"] >= 1,
            "position_close_fill_seen": evidence["restart_position_close"]["fills"] >= 1,
            "safe_locks": all(locks.values()),
            "real_money_execution_blocked": True,
        }
        out = {
            "status": "PASS" if all(checks.values()) else "FAIL",
            "position": str(pos),
            "pending": len(pending),
            "cross_leverage": lev_values,
            "safe_locks": locks,
            "checks": checks,
            "evidence": evidence,
            "private_post_performed": False,
            "real_money_execution_enabled": False,
        }
        print("OKX_DEMO_D4_FINAL_AUDIT=" + json.dumps(out, separators=(",", ":"), ensure_ascii=False), flush=True)
        if out["status"] != "PASS":
            raise RuntimeError("D4_FINAL_AUDIT_FAILED " + ",".join(k for k, v in checks.items() if not v))
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
        print("OKX_DEMO_D4_FINAL_AUDIT=" + json.dumps(H.RESULT, separators=(",", ":")), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
