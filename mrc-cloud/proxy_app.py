from __future__ import annotations

import httpx
from fastapi import HTTPException
from trend_v1 import app

SIDECAR = "http://127.0.0.1:8081"

async def _proxy(path: str):
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(SIDECAR + path)
        if r.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"slow sidecar HTTP {r.status_code}")
        return r.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"slow sidecar unavailable: {type(exc).__name__}: {exc}")

@app.get('/slow/readyz')
async def slow_readyz():
    return await _proxy('/readyz')

@app.get('/slow/audit')
async def slow_audit():
    return await _proxy('/api/audit')

@app.get('/slow/evidence')
async def slow_evidence():
    return await _proxy('/api/evidence')

@app.get('/slow/cost-sensitivity')
async def slow_cost_sensitivity():
    return await _proxy('/api/cost-sensitivity')

@app.get('/slow/latest-closed-trade-review')
async def slow_latest_closed_trade_review():
    return await _proxy('/api/latest-closed-trade-review')
