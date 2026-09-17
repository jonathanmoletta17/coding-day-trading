from __future__ import annotations
import asyncio, json, os, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
import slow_engine_v2 as eng
from slow_store_v3 import Store

SYMBOLS=("BTCUSDT","ETHUSDT")
INST={"BTCUSDT":"BTC-USDT-SWAP","ETHUSDT":"ETH-USDT-SWAP"}
BASE="https://www.okx.com"
POLL=max(10,int(os.getenv("MRC_POLL_SECONDS","15")))
DB_PATH=os.getenv("MRC_STAGING_DB","/tmp/mrc_slow_staging.sqlite3")
DATABASE_URL=os.getenv("DATABASE_URL","").strip()
START_EQUITY=float(os.getenv("MRC_PAPER_EQUITY","10000"))
RISK_PCT=float(os.getenv("MRC_RISK_PCT","0.0025"))
COST=float(os.getenv("MRC_ROUNDTRIP_COST","0.0006"))
DAILY_LOCK_PCT=.01
RELEASE_SHA=os.getenv("MRC_SLOW_RELEASE_SHA","UNPINNED")
DURABLE_STORAGE=bool(DATABASE_URL) or (not DATABASE_URL and os.path.abspath(DB_PATH).startswith("/data/"))

def iso(ms=None):
    if ms is None:return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat()

db=Store(DB_PATH,DATABASE_URL)

def load_telemetry():
    last={};counts={};decided={}
    for s in SYMBOLS:
        d=db.last_decision(s);last[s]=int(d["close_ms"]) if d else None;counts[s]=db.decision_count(s);decided[s]=d["decided_at"] if d else None
    return {"last_processed_close":last,"processed_close_count":counts,"last_decision_at":decided,
            "signals_created":db.signal_count(),"paper_positions_opened":db.trade_count()}

def refresh_telemetry():STATE["telemetry"]=load_telemetry()

class OKX:
    def __init__(self):self.h=httpx.AsyncClient(timeout=12,headers={"User-Agent":"MRC-Slow-Staging/4.3"})
    async def g(self,path,**params):
        r=await self.h.get(BASE+path,params=params);r.raise_for_status();j=r.json()
        if j.get("code")!="0":raise RuntimeError(f"OKX {j.get('code')} {j.get('msg')}")
        return j.get("data") or []
    async def snapshot(self,s):
        inst=INST[s]
        h1,h4,tick=await asyncio.gather(
            self.g("/api/v5/market/candles",instId=inst,bar="1H",limit="120"),
            self.g("/api/v5/market/candles",instId=inst,bar="4H",limit="150"),
            self.g("/api/v5/market/ticker",instId=inst),
        )
        return h1,h4,tick[0] if tick else {}
    async def ticker(self,s):
        x=await self.g("/api/v5/market/ticker",instId=INST[s]);return x[0] if x else {}
    async def minute_rows(self,s):return await self.g("/api/v5/market/candles",instId=INST[s],bar="1m",limit="300")
    async def close(self):await self.h.aclose()

def one_minute(rows,cutoff):
    out=[]
    for r in rows:
        if len(r)<9 or str(r[8])!="1":continue
        ot=int(r[0]);ct=ot+eng.MINUTE
        if ct<=cutoff:out.append({"ot":ot,"ct":ct,"o":eng.f(r[1]),"h":eng.f(r[2]),"l":eng.f(r[3]),"c":eng.f(r[4])})
    return sorted(out,key=lambda x:x["ot"])

STATE={
    "started_at":iso(),"heartbeat":0.0,"symbols":{},"last_error":None,"strategy":eng.STRATEGY,
    "mode":"PAPER_STAGING","version":"slow-staging-v4.3-causal-exits","release_sha":RELEASE_SHA,"coverage_gap":None,
    "storage":{"backend":db.backend,"durable":DURABLE_STORAGE,"sqlite_path":DB_PATH if db.backend=="sqlite" else None},
    "risk_controls":{
        "risk_pct":RISK_PCT,"daily_loss_lock_pct":DAILY_LOCK_PCT,"daily_locked":False,"daily_realized_pnl_utc":0.0,
        "max_signal_age_min":eng.MAX_AGE_MIN,"max_signal_age_role":"operational_guard_after_downtime_not_research_edge",
        "one_global_position":"database_enforced","strict_next_entry_gt_prior_exit":True,
        "entry_partial_minute_policy":"exclude_pre_entry_ohlc; current_bid_ask_can_trigger_stop; target_requires_closed_causal_1m",
    },"telemetry":load_telemetry(),
}
LOCK=asyncio.Lock();TASK=None

async def manage_open(client,now_ms):
    t=db.open_trade()
    if not t:STATE["coverage_gap"]=None;return
    all_bars=one_minute(await client.minute_rows(t["symbol"]),now_ms)
    opened=int(t["opened_ms"]);monitor_start=eng.first_full_minute_open(opened)
    last_check=int(t["last_check_ms"] or opened);expected=max(monitor_start,last_check)
    bars=[b for b in all_bars if b["ot"]>=monitor_start and b["ct"]>expected]
    if bars and bars[0]["ot"]>expected:
        STATE["coverage_gap"]=f"{t['symbol']} 1M_COVERAGE_GAP from {iso(expected)} to {iso(bars[0]['ot'])}";return
    # For an incomplete minute we only use the executable side of the current ticker for STOP.
    tick=await client.ticker(t["symbol"]);bid=eng.f(tick.get("bidPx"));ask=eng.f(tick.get("askPx"))
    instant=eng.current_stop_from_ticker(t,bid,ask,now_ms)
    if instant:
        outcome,px,closed_ms=instant;STATE["coverage_gap"]=None;db.close(t,px,outcome,closed_ms,COST);return
    if not bars:return
    STATE["coverage_gap"]=None
    ex=eng.exit_from_1m(t,bars,now_ms)
    if ex:
        outcome,px,closed_ms=ex;db.close(t,px,outcome,closed_ms,COST)
    else:db.mark_checked(t["trade_id"],bars[-1]["ct"])

async def loop():
    client=OKX();fresh_boot=True
    try:
        while True:
            now_ms=int(time.time()*1000);errors=[]
            try:await manage_open(client,now_ms)
            except Exception as e:errors.append(f"position: {type(e).__name__}: {e}")
            daily_pnl=db.daily_realized_pnl(now_ms);daily_locked=daily_pnl<=-(START_EQUITY*DAILY_LOCK_PCT)
            STATE["risk_controls"].update(daily_locked=daily_locked,daily_realized_pnl_utc=round(daily_pnl,8))
            slot=db.open_trade() is not None
            for s in SYMBOLS:
                try:
                    h1,h4,t=await client.snapshot(s);bid=eng.f(t.get("bidPx"));ask=eng.f(t.get("askPx"))
                    closed=eng.confirmed(h1,eng.HOUR,now_ms);current_close=closed[-1]["ct"] if closed else 0
                    key="last_processed_1h_close:"+s;raw=db.get(key);last=int(raw) if raw is not None else None
                    process,newmark=eng.should_process(last,current_close,fresh_boot)
                    last_exit=db.latest_exit_ms();reentry_blocked=bool(last_exit is not None and current_close and current_close<=last_exit)
                    ctx,p=eng.evaluate(s,h1,h4,bid,ask,now_ms,db.equity(START_EQUITY),RISK_PCT,
                        slot_open=slot,reentry_blocked=reentry_blocked,daily_locked=daily_locked)
                    action="WATERMARK_ONLY"
                    if process:
                        decided_at=iso(now_ms)
                        if p:db.record_signal(p,decided_at);action=p.decision
                        else:action=ctx.get("state","UNKNOWN")
                        db.record_decision(eng.STRATEGY,s,int(newmark),decided_at,ctx,p,action_override=action)
                        if p and p.decision in ("LONG","SHORT") and not slot:
                            if STATE["coverage_gap"]:
                                action="BLOCKED_COVERAGE_GAP";db.update_decision_action(eng.STRATEGY,s,int(newmark),action)
                            elif db.open(p,now_ms):
                                slot=True;action="PAPER_OPEN";db.update_decision_action(eng.STRATEGY,s,int(newmark),action)
                            else:
                                slot=db.open_trade() is not None;action="BLOCKED_ATOMIC_SLOT_OR_REENTRY";db.update_decision_action(eng.STRATEGY,s,int(newmark),action)
                        db.set(key,newmark);refresh_telemetry()
                    elif current_close and last is None:db.set(key,newmark)
                    async with LOCK:
                        STATE["symbols"][s]={"context":ctx,"candidate":p.__dict__ if p else None,"watermark":newmark if current_close else None,
                            "processed_this_cycle":bool(process),"action":action,"reentry_blocked":reentry_blocked,"last_exit_ms":last_exit,"error":None}
                except Exception as e:
                    msg=f"{type(e).__name__}: {e}";errors.append(f"{s}: {msg}")
                    async with LOCK:STATE["symbols"][s]={"context":{"ready":False,"state":"DATA_ERROR"},"candidate":None,"error":msg}
            fresh_boot=False
            async with LOCK:
                STATE["heartbeat"]=time.time();STATE["last_error"]=" | ".join(errors) if errors else None;STATE["position"]=db.open_trade()
                STATE["equity"]=round(db.equity(START_EQUITY),2);STATE["recent_trades"]=db.recent();refresh_telemetry()
            await asyncio.sleep(POLL)
    finally:await client.close()

@asynccontextmanager
async def life(app):
    global TASK
    TASK=asyncio.create_task(loop());yield;TASK.cancel();db.close_conn()

app=FastAPI(title="MRC Slow Trend Staging",version="4.3",lifespan=life)
def checks():return {s:bool(STATE["symbols"].get(s,{}).get("context",{}).get("ready") and not STATE["symbols"].get(s,{}).get("error")) for s in SYMBOLS}
@app.get("/healthz")
async def health():
    age=time.time()-STATE.get("heartbeat",0);ck=checks();process_ok=TASK is not None and not TASK.done() and age<90;ok=bool(process_ok and ck and all(ck.values()) and not STATE.get("coverage_gap"))
    return JSONResponse({"ok":ok,"feed_ready":bool(ck and all(ck.values())),"checks":ck,"coverage_gap":STATE.get("coverage_gap"),"heartbeat_age_s":round(age,1),
        "strategy":eng.STRATEGY,"storage_backend":db.backend,"durable_storage":DURABLE_STORAGE,"last_error":STATE.get("last_error")},status_code=200 if ok else 503)
@app.get("/readyz")
async def ready():
    ck=checks();ok=bool(ck and all(ck.values()) and not STATE.get("coverage_gap"))
    return JSONResponse({"ready":ok,"checks":ck,"coverage_gap":STATE.get("coverage_gap"),"strategy":eng.STRATEGY,"mode":"PAPER_STAGING",
        "storage_backend":db.backend,"durable_storage":DURABLE_STORAGE,"release_sha":RELEASE_SHA},status_code=200 if ok else 503)
@app.get("/api/state")
async def api_state():
    async with LOCK:return json.loads(json.dumps(STATE,default=str))
@app.get("/api/audit")
async def api_audit():
    now_ms=int(time.time()*1000)
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"storage":{"backend":db.backend,"durable":DURABLE_STORAGE},
        "risk_controls":STATE["risk_controls"],"prospective":db.audit_summary(COST,START_EQUITY,now_ms),"recent_decisions":db.recent_decisions(20),"recent_trades":db.recent(20)}
@app.get("/",response_class=HTMLResponse)
async def root():
    return """<html><body style='background:#071019;color:#eaf2f8;font-family:system-ui;padding:28px'><h1>MRC Slow Trend — PAPER AUDIT</h1>
    <p>4H EMA20/50 + 1H Donchian20 + ATR14 · PAPER ONLY</p><p><a style='color:#70c7ff' href='/api/state'>State</a> · <a style='color:#70c7ff' href='/api/audit'>Audit</a> · <a style='color:#70c7ff' href='/readyz'>Readiness</a></p>
    <div id='x'>loading…</div><script>async function g(){let r=await fetch('/api/audit'),x=await r.json();document.querySelector('#x').innerHTML='<pre>'+JSON.stringify(x,null,2)+'</pre>'};g();setInterval(g,10000)</script></body></html>"""
