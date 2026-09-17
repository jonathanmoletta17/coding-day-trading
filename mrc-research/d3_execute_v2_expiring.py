from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import d3_okx_demo_roundtrip as d3

ORDER_EXPIRY_MS = 5_000


async def expiring_private_post(self: d3.Client, path: str, payload: dict):
    """D3-only POST adapter with an OKX expTime deadline.

    The D3 core remains the authority for all fail-closed gates and cleanup.
    This wrapper only adds a short server-side expiry deadline to trade POSTs.
    """
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    ts = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    headers = self.headers(ts, "POST", path, body)
    headers["expTime"] = str(int(time.time() * 1000) + ORDER_EXPIRY_MS)
    r = await self.h.post(path, content=body.encode(), headers=headers)
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code >= 400:
        raise RuntimeError(f"OKX_POST_HTTP {r.status_code} {j.get('code')} {j.get('msg')}")
    if j.get("code") != "0":
        raise RuntimeError(f"OKX_POST_ERROR {j.get('code')} {j.get('msg')}")
    rows = j.get("data") or []
    if not rows:
        raise RuntimeError("OKX_POST_EMPTY")
    row = rows[0]
    if str(row.get("sCode") or "0") != "0":
        raise RuntimeError(f"OKX_ORDER_REJECTED {row.get('sCode')} {row.get('sMsg')}")
    return row


def main():
    d3.Client.private_post = expiring_private_post
    print(f"D3_ORDER_EXPIRY_POLICY_MS={ORDER_EXPIRY_MS}", flush=True)
    d3.main()


if __name__ == "__main__":
    main()
