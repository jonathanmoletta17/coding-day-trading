from __future__ import annotations

import json
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from first_trade_postmortem import build_report

LOCK=threading.Lock()
STATE={"status":"STARTING","report":None,"error":None,"generated_at":None}


def generate()->None:
    try:
        report=build_report()
        with LOCK:STATE.update(status="PASS",report=report,error=None,generated_at=datetime.now(timezone.utc).isoformat())
        print("FIRST_TRADE_POSTMORTEM="+json.dumps(report,separators=(",",":"),ensure_ascii=False,default=str),flush=True)
    except Exception as exc:
        with LOCK:STATE.update(status="FAIL",report=None,error=f"{type(exc).__name__}: {exc}",generated_at=datetime.now(timezone.utc).isoformat())
        print("FIRST_TRADE_POSTMORTEM_ERROR="+STATE["error"],flush=True)


@asynccontextmanager
async def life(app):
    generate();yield


app=FastAPI(title="MRC Read-Only Postmortem Lab",version="1.0",lifespan=life)


@app.get("/healthz")
async def health():
    with LOCK:body={"ok":STATE["status"]=="PASS","status":STATE["status"],"generated_at":STATE["generated_at"],"error":STATE["error"],
        "read_only":True,"paper_mutation_performed":False,"private_exchange_api_used":False}
    return JSONResponse(body,status_code=200 if body["ok"] else 503)


@app.get("/report")
async def report():
    with LOCK:body=json.loads(json.dumps(STATE,default=str))
    return JSONResponse(body,status_code=200 if body["status"]=="PASS" else 503)
