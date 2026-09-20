from __future__ import annotations
import asyncio, json, os, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
import slow_engine_v2 as eng
import slow_replay_v1 as replay
import slow_log_probe as archive
from slow_store_v3 import Store
from slow_evidence_v1 import (
    closed_trade_reviews,
    evidence_summary,
    latest_closed_trade_review,
    scientific_readiness,
    signal_reviews,
)

SYMBOLS=("BTCUSDT","ETHUSDT")
INST={"BTCUSDT":"BTC-USDT-SWAP","ETHUSDT":"ETH-USDT-SWAP"}
BASE="https://www.okx.com"
POLL=max(10,int(os.getenv("MRC_POLL_SECONDS","15")))
DB_PATH=os.getenv("MRC_STAGING_DB","/tmp/mrc_slow_staging.sqlite3")
DATABASE_URL=os.getenv("DATABASE_URL","").strip()
START_EQUITY=float(os.getenv("MRC_PAPER_EQUITY","10000"))
RISK_PCT=float(os.getenv("MRC_RISK_PCT","0.0025"))
COST=float(os.getenv("MRC_ROUNDTRIP_COST","0.0006"))
COST_SCENARIOS={"baseline_6bps":COST,"stress_10bps":0.0010,"stress_15bps":0.0015}
DEMO_CALIBRATION_BPS=float(os.getenv("MRC_DEMO_CALIBRATION_BPS","0") or 0)
DAILY_LOCK_PCT=.01
RELEASE_SHA=os.getenv("MRC_SLOW_RELEASE_SHA","UNPINNED")
DURABLE_STORAGE=bool(DATABASE_URL) or (not DATABASE_URL and os.path.abspath(DB_PATH).startswith("/data/"))
RECENT_1M_SAFE_BARS=280
HISTORY_PAGE_LIMIT=100
HISTORY_PAGE_SLEEP=.11
ARCHIVE_HEALTH_PATH=os.getenv("MRC_EVIDENCE_ARCHIVE_HEALTH","/data/evidence/archive_health.json")
ARCHIVE_MAX_STALE_SECONDS=max(600,int(os.getenv("MRC_EVIDENCE_ARCHIVE_MAX_STALE_SECONDS","900")))
ARCHIVE_EMBEDDED=os.getenv("MRC_ARCHIVE_EMBEDDED","0").strip()=="1"
ARCHIVE_START_DELAY=max(1,int(os.getenv("MRC_ARCHIVE_START_DELAY_SECONDS","3")))

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
def read_evidence():return evidence_summary(db,SYMBOLS,eng.HOUR)

def read_latest_closed_trade_review():return latest_closed_trade_review(db,COST_SCENARIOS)
def read_signal_reviews():return signal_reviews(db,100)
def read_closed_trade_reviews():return closed_trade_reviews(db,COST_SCENARIOS,200)
def read_scientific_readiness():return scientific_readiness(db,SYMBOLS,eng.HOUR)
def read_archive_health():
    try:
        body=json.loads(Path(ARCHIVE_HEALTH_PATH).read_text(encoding="utf-8"))
        heartbeat=float(body.get("heartbeat_epoch") or 0);age=max(0.0,time.time()-heartbeat)
        body["heartbeat_age_s"]=round(age,1);body["fresh"]=age<=ARCHIVE_MAX_STALE_SECONDS
        body["ok"]=bool(body.get("chain_ok") and body.get("last_snapshot_hash") and body.get("last_backup_sha256") and body["fresh"] and not body.get("last_error"))
        body["read_only_status_view"]=True
        return body
    except Exception as exc:
        return {"ok":False,"fresh":False,"read_only_status_view":True,"error":f"{type(exc).__name__}: {exc}"}

class OKX:
    def __init__(self):self.h=httpx.AsyncClient(timeout=12,headers={"User-Agent":"MRC-Slow-Staging/4.7"})
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
    async def minute_rows_range(self,s,start_open_ms:int,cutoff_ms:int):
        """Fetch all confirmed 1m bars required for causal replay.

        Recent windows use /candles. Longer windows page backwards through
        /history-candles with OKX's `after` cursor until start_open_ms is covered.
        Returns (bars, metadata).
        """
        start=int(start_open_ms);cutoff=int(cutoff_ms)
        if cutoff<=start:return [],{"source":"none","pages":0,"bars":0,"from":start,"to":cutoff}
        inst=INST[s];span=cutoff-start
        if span<=RECENT_1M_SAFE_BARS*eng.MINUTE:
            rows=await self.g("/api/v5/market/candles",instId=inst,bar="1m",limit="300")
            bars=replay.confirmed_1m(rows,cutoff,start)
            return bars,{"source":"recent","pages":1,"bars":len(bars),"from":start,"to":cutoff}
        pages=[];cursor=cutoff+1;requests=0
        while cursor>start:
            rows=await self.g("/api/v5/market/history-candles",instId=inst,bar="1m",after=str(cursor),limit=str(HISTORY_PAGE_LIMIT))
            requests+=1
            if not rows:break
            pages.append(rows)
            ots=[int(r[0]) for r in rows if r]
            if not ots:break
            oldest=min(ots)
            if oldest<=start:break
            if oldest>=cursor:raise RuntimeError(f"OKX_HISTORY_CURSOR_STALLED {s} cursor={cursor} oldest={oldest}")
            cursor=oldest
            await asyncio.sleep(HISTORY_PAGE_SLEEP)
            if requests>60:raise RuntimeError(f"OKX_HISTORY_PAGE_GUARD {s} requests={requests}")
        bars=replay.merge_pages(pages,cutoff,start)
        return bars,{"source":"history","pages":requests,"bars":len(bars),"from":start,"to":cutoff}
    async def close(self):await self.h.aclose()

STATE={
    "started_at":iso(),"heartbeat":0.0,"symbols":{},"last_error":None,"strategy":eng.STRATEGY,
    "mode":"PAPER_STAGING","version":"slow-staging-v4.9-evidence-preservation","release_sha":RELEASE_SHA,"coverage_gap":None,
    "storage":{"backend":db.backend,"durable":DURABLE_STORAGE,"sqlite_path":DB_PATH if db.backend=="sqlite" else None},
    "replay":{"max_hold_h":eng.MAX_HOLD_H,"history_page_limit":HISTORY_PAGE_LIMIT,"last":None},
    "cost_policy":{"paper_baseline_bps":COST*10000.0,"audit_scenarios_bps":{k:v*10000.0 for k,v in COST_SCENARIOS.items()},
                   "demo_calibration_bps":DEMO_CALIBRATION_BPS if DEMO_CALIBRATION_BPS>0 else None,
                   "role":"audit_only_scenarios_do_not_affect_signals_or_trade_management"},
    "risk_controls":{
        "risk_pct":RISK_PCT,"daily_loss_lock_pct":DAILY_LOCK_PCT,"daily_locked":False,"daily_realized_pnl_utc":0.0,
        "max_signal_age_min":eng.MAX_AGE_MIN,"max_signal_age_role":"operational_guard_after_downtime_not_research_edge",
        "one_global_position":"database_enforced","strict_next_entry_gt_prior_exit":True,
        "entry_partial_minute_policy":"exclude_pre_entry_ohlc; current_bid_ask_can_trigger_stop; target_requires_closed_causal_1m",
        "max_hold_replay_policy":"paginate confirmed 1m through 72h deadline; STOP conservative on deadline-straddling bar; no post-deadline TARGET",
    },"telemetry":load_telemetry(),
}
LOCK=asyncio.Lock();TASK=None;ARCHIVE_TASK=None

async def manage_open(client,now_ms):
    t=db.open_trade()
    if not t:STATE["coverage_gap"]=None;STATE["replay"]["last"]=None;return
    w=replay.replay_window(int(t["opened_ms"]),int(t["last_check_ms"] or t["opened_ms"]),now_ms,eng.MAX_HOLD_H*eng.HOUR)
    bars,meta=await client.minute_rows_range(t["symbol"],w["expected_open"],w["cutoff_ms"])
    meta.update(symbol=t["symbol"],deadline_ms=w["deadline_ms"],expected_open=w["expected_open"])
    STATE["replay"]["last"]=meta
    gap=replay.first_gap(bars,w["expected_open"],w["cutoff_ms"])
    if gap:
        STATE["coverage_gap"]=f"{t['symbol']} 1M_COVERAGE_GAP missing {iso(gap['missing_open_ms'])} through {iso(gap['expected_through_open_ms'])}"
        return
    STATE["coverage_gap"]=None
    ex=eng.exit_from_1m(t,bars,now_ms)
    if ex:
        outcome,px,closed_ms=ex;db.close(t,px,outcome,closed_ms,COST);return
    tick=await client.ticker(t["symbol"]);bid=eng.f(tick.get("bidPx"));ask=eng.f(tick.get("askPx"))
    instant=eng.current_stop_from_ticker(t,bid,ask,now_ms)
    if instant:
        outcome,px,closed_ms=instant;db.close(t,px,outcome,closed_ms,COST);return
    if bars:db.mark_checked(t["trade_id"],bars[-1]["ct"])

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
    global TASK,ARCHIVE_TASK
    TASK=asyncio.create_task(loop())
    if ARCHIVE_EMBEDDED:
        async def delayed_archive():
            await asyncio.sleep(ARCHIVE_START_DELAY)
            await archive.main()
        ARCHIVE_TASK=asyncio.create_task(delayed_archive())
    try:
        yield
    finally:
        TASK.cancel()
        if ARCHIVE_TASK is not None:ARCHIVE_TASK.cancel()
        db.close_conn()

app=FastAPI(title="MRC Slow Trend Staging",version="4.9",lifespan=life)
def checks():return {s:bool(STATE["symbols"].get(s,{}).get("context",{}).get("ready") and not STATE["symbols"].get(s,{}).get("error")) for s in SYMBOLS}
@app.get("/healthz")
async def health():
    age=time.time()-STATE.get("heartbeat",0);ck=checks();process_ok=TASK is not None and not TASK.done() and age<90;ok=bool(process_ok and ck and all(ck.values()) and not STATE.get("coverage_gap"))
    return JSONResponse({"ok":ok,"feed_ready":bool(ck and all(ck.values())),"checks":ck,"coverage_gap":STATE.get("coverage_gap"),"heartbeat_age_s":round(age,1),
        "strategy":eng.STRATEGY,"storage_backend":db.backend,"durable_storage":DURABLE_STORAGE,"replay":STATE.get("replay"),"last_error":STATE.get("last_error")},status_code=200 if ok else 503)
@app.get("/livez")
async def live():
    age=time.time()-STATE.get("heartbeat",0);process_ok=TASK is not None and not TASK.done() and age<90
    return JSONResponse({"live":bool(process_ok),"heartbeat_age_s":round(age,1),"task_running":bool(TASK is not None and not TASK.done()),
        "strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA},status_code=200 if process_ok else 503)
@app.get("/readyz")
async def ready():
    ck=checks();ok=bool(ck and all(ck.values()) and not STATE.get("coverage_gap"));ev=read_evidence()
    return JSONResponse({"ready":ok,"checks":ck,"coverage_gap":STATE.get("coverage_gap"),"strategy":eng.STRATEGY,"mode":"PAPER_STAGING",
        "storage_backend":db.backend,"durable_storage":DURABLE_STORAGE,"release_sha":RELEASE_SHA,"evidence_integrity_pass":ev["integrity_pass"],
        "last_error":STATE.get("last_error"),"symbol_errors":{s:(STATE.get("symbols",{}).get(s,{}) or {}).get("error") for s in SYMBOLS},
        "replay":STATE.get("replay")},status_code=200 if ok else 503)
@app.get("/api/state")
async def api_state():
    async with LOCK:return json.loads(json.dumps(STATE,default=str))
@app.get("/api/audit")
async def api_audit():
    now_ms=int(time.time()*1000)
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"storage":{"backend":db.backend,"durable":DURABLE_STORAGE},
        "replay":STATE["replay"],"risk_controls":STATE["risk_controls"],"cost_policy":STATE["cost_policy"],
        "prospective":db.audit_summary(COST,START_EQUITY,now_ms),"cost_sensitivity":db.cost_sensitivity(COST_SCENARIOS,START_EQUITY),
        "evidence_quality":read_evidence(),"latest_closed_trade_review":read_latest_closed_trade_review(),
        "scientific_readiness":read_scientific_readiness(),"archive_health":read_archive_health(),
        "recent_decisions":db.recent_decisions(20),"recent_trades":db.recent(20)}
@app.get("/api/evidence")
async def api_evidence():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"evidence_quality":read_evidence()}
@app.get("/api/latest-closed-trade-review")
async def api_latest_closed_trade_review():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"review":read_latest_closed_trade_review()}
@app.get("/api/signal-reviews")
async def api_signal_reviews():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"signal_reviews":read_signal_reviews()}
@app.get("/api/closed-trade-reviews")
async def api_closed_trade_reviews():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"closed_trade_reviews":read_closed_trade_reviews()}
@app.get("/api/scientific-readiness")
async def api_scientific_readiness():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"scientific_readiness":read_scientific_readiness()}
@app.get("/api/archive-health")
async def api_archive_health():
    health=read_archive_health()
    return JSONResponse({"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"archive_health":health},status_code=200 if health.get("ok") else 503)
@app.get("/api/cost-sensitivity")
async def api_cost_sensitivity():
    return {"strategy":eng.STRATEGY,"mode":"PAPER_STAGING","release_sha":RELEASE_SHA,"cost_policy":STATE["cost_policy"],
            "scenarios":db.cost_sensitivity(COST_SCENARIOS,START_EQUITY)}
@app.get("/",response_class=HTMLResponse)
async def root():
    return """<html><body style='background:#071019;color:#eaf2f8;font-family:system-ui;padding:28px'><h1>MRC Slow Trend — PAPER AUDIT</h1>
    <p>4H EMA20/50 + 1H Donchian20 + ATR14 · PAPER ONLY</p><p><a style='color:#70c7ff' href='/api/state'>State</a> · <a style='color:#70c7ff' href='/api/audit'>Audit</a> · <a style='color:#70c7ff' href='/api/evidence'>Evidence</a> · <a style='color:#70c7ff' href='/api/latest-closed-trade-review'>Latest Trade Review</a> · <a style='color:#70c7ff' href='/api/closed-trade-reviews'>All Trade Reviews</a> · <a style='color:#70c7ff' href='/api/signal-reviews'>Signal Reviews</a> · <a style='color:#70c7ff' href='/api/scientific-readiness'>Scientific Readiness</a> · <a style='color:#70c7ff' href='/api/archive-health'>Archive Health</a> · <a style='color:#70c7ff' href='/api/cost-sensitivity'>Costs</a> · <a style='color:#70c7ff' href='/readyz'>Readiness</a></p>
    <div id='x'>loading…</div><script>async function g(){let r=await fetch('/api/audit'),x=await r.json();document.querySelector('#x').innerHTML='<pre>'+JSON.stringify(x,null,2)+'</pre>'};g();setInterval(g,10000)</script></body></html>"""
