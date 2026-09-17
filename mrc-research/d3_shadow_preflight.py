from __future__ import annotations

import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

# IMPORTANT: This script never calls Client.private_post. It temporarily mirrors
# the intended D3 execution gate values only inside this Python process so the
# exact authenticated GET-only preflight can be evaluated while Railway itself
# remains locked (execution disabled, kill switch on, diagnostic-only on).
SIMULATED = {
    "MRC_EXECUTION_MODE": "DEMO",
    "MRC_DEMO_EXECUTION_ENABLED": "1",
    "MRC_KILL_SWITCH": "0",
    "MRC_DEMO_DIAGNOSTIC_ONLY": "0",
    "MRC_D3_ARM": d3.ARM,
    "MRC_D3_ATTEMPT_ID": os.getenv("MRC_D3_ATTEMPT_ID", "D3BTC260917A"),
    "MRC_D3_EXPECTED_LEVERAGE": os.getenv("MRC_D3_EXPECTED_LEVERAGE", "3"),
}

RESULT: dict = {"status": "NOT_RUN"}


def safe_lock_snapshot() -> dict:
    return {
        "railway_execution_mode": os.getenv("MRC_EXECUTION_MODE", ""),
        "railway_demo_execution_enabled": os.getenv("MRC_DEMO_EXECUTION_ENABLED", ""),
        "railway_kill_switch": os.getenv("MRC_KILL_SWITCH", ""),
        "railway_diagnostic_only": os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", ""),
        "railway_arm_is_empty": os.getenv("MRC_D3_ARM", "").strip() == "",
        "attempt_id": os.getenv("MRC_D3_ATTEMPT_ID", ""),
        "expected_leverage": os.getenv("MRC_D3_EXPECTED_LEVERAGE", ""),
    }


async def run() -> dict:
    before = safe_lock_snapshot()
    # Require the actual service to remain safe before simulating the gates.
    if not (
        before["railway_execution_mode"] == "DEMO"
        and before["railway_demo_execution_enabled"] == "0"
        and before["railway_kill_switch"] != "0"
        and before["railway_diagnostic_only"] == "1"
        and before["railway_arm_is_empty"]
    ):
        raise RuntimeError("SHADOW_PREFLIGHT_REQUIRES_ACTUAL_SAFE_LOCKS")

    saved = {k: os.environ.get(k) for k in SIMULATED}
    c = d3.Client()
    try:
        for k, v in SIMULATED.items():
            os.environ[k] = str(v)
        preflight = await d3.validate_preflight(c)
        return {
            "status": "PASS",
            "actual_safe_locks_before": before,
            "simulated_gate_values": {
                "execution_mode": "DEMO",
                "demo_execution_enabled": "1",
                "kill_switch": "0",
                "diagnostic_only": "0",
                "arm_matches_v2": True,
                "attempt_id": SIMULATED["MRC_D3_ATTEMPT_ID"],
                "expected_leverage": SIMULATED["MRC_D3_EXPECTED_LEVERAGE"],
            },
            "preflight": preflight,
            "private_post_performed": False,
            "order_submission_performed": False,
        }
    finally:
        await c.close()
        for k, old in saved.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            body = json.dumps({"ok": RESULT.get("status") == "PASS", "mode": "D3_SHADOW_PREFLIGHT_NO_ORDER", "result": RESULT}, separators=(",", ":"), ensure_ascii=False).encode()
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
        RESULT = {"status": "FAIL", "error": type(exc).__name__ + ": " + str(exc), "actual_safe_locks": safe_lock_snapshot(), "private_post_performed": False}
    print("OKX_DEMO_D3_SHADOW_PREFLIGHT=" + json.dumps(RESULT, separators=(",", ":"), ensure_ascii=False), flush=True)
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


if __name__ == "__main__":
    main()
