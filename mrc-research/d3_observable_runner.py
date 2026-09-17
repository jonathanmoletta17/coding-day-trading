from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import d3_okx_demo_roundtrip as d3

ORDER_EXPIRY_MS = 10_000
STATE: dict = {"status": "BOOTING", "updated_at": time.time()}
LOCK = threading.Lock()


def set_state(**kwargs):
    with LOCK:
        STATE.update(kwargs)
        STATE["updated_at"] = time.time()


def get_state():
    with LOCK:
        return dict(STATE)


async def expiring_private_post(self: d3.Client, path: str, payload: dict):
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    headers = self.headers(ts, "POST", path, body)
    headers["expTime"] = str(int(time.time() * 1000) + ORDER_EXPIRY_MS)
    set_state(last_post_path=path, last_post_clOrdId=payload.get("clOrdId"), last_post_side=payload.get("side"), last_post_sz=payload.get("sz"))
    r = await self.h.post(path, content=body.encode(), headers=headers)
    try:
        j = r.json()
    except Exception:
        j = {"raw_text": r.text[:500]}
    set_state(last_post_http_status=r.status_code, last_post_okx_code=j.get("code"), last_post_okx_msg=j.get("msg"), last_post_data=j.get("data"))
    if r.status_code >= 400:
        raise RuntimeError(f"OKX_POST_HTTP {r.status_code} {j.get('code')} {j.get('msg')}")
    if j.get("code") != "0":
        raise RuntimeError(f"OKX_POST_ERROR {j.get('code')} {j.get('msg')} data={j.get('data')}")
    rows = j.get("data") or []
    if not rows:
        raise RuntimeError("OKX_POST_EMPTY")
    row = rows[0]
    if str(row.get("sCode") or "0") != "0":
        raise RuntimeError(f"OKX_ORDER_REJECTED {row.get('sCode')} {row.get('sMsg')}")
    return row


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/healthz"):
            state = get_state()
            # 200 ONLY after a completed flat round-trip. RUNNING/FAIL remain 503.
            ok = state.get("status") == "PASS"
            body = json.dumps({"ok": ok, "mode": "D3_OBSERVABLE_RUNNER", "state": state}, separators=(",", ":"), ensure_ascii=False).encode()
            self.send_response(200 if ok else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        return


def serve():
    HTTPServer(("0.0.0.0", int(os.getenv("PORT", "8080"))), H).serve_forever()


def main():
    threading.Thread(target=serve, daemon=True).start()
    d3.Client.private_post = expiring_private_post
    set_state(
        status="RUNNING",
        order_expiry_ms=ORDER_EXPIRY_MS,
        execution_mode=os.getenv("MRC_EXECUTION_MODE", ""),
        demo_execution_enabled=os.getenv("MRC_DEMO_EXECUTION_ENABLED", ""),
        kill_switch=os.getenv("MRC_KILL_SWITCH", ""),
        diagnostic_only=os.getenv("MRC_DEMO_DIAGNOSTIC_ONLY", ""),
        arm_matches=os.getenv("MRC_D3_ARM", "") == d3.ARM,
        attempt_id=os.getenv("MRC_D3_ATTEMPT_ID", ""),
        expected_leverage=os.getenv("MRC_D3_EXPECTED_LEVERAGE", ""),
    )
    print("D3_OBSERVABLE_START=" + json.dumps(get_state(), separators=(",", ":"), ensure_ascii=False), flush=True)
    try:
        out = asyncio.run(d3.run())
        set_state(status="PASS", result=out)
        print("D3_OBSERVABLE_FINAL=" + json.dumps(get_state(), separators=(",", ":"), ensure_ascii=False), flush=True)
    except Exception as exc:
        set_state(status="FAIL", error=type(exc).__name__ + ": " + str(exc))
        print("D3_OBSERVABLE_FINAL=" + json.dumps(get_state(), separators=(",", ":"), ensure_ascii=False), flush=True)
    # Keep diagnostic state inspectable; health remains 503 on FAIL.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
