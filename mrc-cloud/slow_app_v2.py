from __future__ import annotations
import asyncio, json, os, sqlite3, time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
import slow_engine_v2 as eng

SYMBOLS=("BTCUSDT","ETHUSDT")
INST={"BTCUSDT":"BTC-USDT-SWAP","ETHUSDT":"ETH-USDT-SWAP"}
BASE="https://www.okx.com"
POLL=max(10,int(os.getenv("MRC_POLL_SECONDS","15")))
DB_PATH=os.getenv("MRC_STAGING_DB","/tmp/mrc_slow_staging.sqlite3")
START_EQUITY=float(os.getenv("MRC_PAPER_EQUITY","10000"))
RISK_PCT=float(os.getenv("MRC_RISK_PCT","0.0025"))
COST=float(os.getenv("MRC_ROUNDTRIP_COST","0.0006"))

def iso(ms=None):
    if ms is None: return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat()

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True)
        self.c=sqlite3.connect(path,check_same_thread=False)
        self.c.row_factory=sqlite3.Row
        self.c.execute("PRAGMA journal_mode=WAL")
        self.c.executescript("""
        CREATE TABLE IF NOT EXISTS runtime_state(k TEXT PRIMARY KEY,v TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signals(
          signal_id TEXT PRIMARY KEY,symbol TEXT,side TEXT,decision TEXT,
          signal_ms INTEGER,payload TEXT,created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS trades(
          trade_id TEXT PRIMARY KEY,signal_id TEXT,symbol TEXT,side TEXT,
          entry REAL,stop REAL,target REAL,qty REAL,risk REAL,opened_ms INTEGER,
          last_check_ms INTEGER,closed_ms INTEGER,exit REAL,outcome TEXT,
          pnl REAL,r_net REAL
        );
        """); self.c.commit()
    def get(self,k):
        r=self.c.execute("SELECT v FROM runtime_state WHERE k=?",(k,)).fetchone()
        return r["v"] if r else None
    def set(self,k,v):
        self.c.execute("INSERT INTO runtime_state(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",(k,str(v))); self.c.commit()
    def open_trade(self):
        r=self.c.execute("SELECT * FROM trades WHERE outcome='OPEN' ORDER BY opened_ms LIMIT 1").fetchone()
        return dict(r) if r else None
    def record_signal(self,p):
        self.c.execute("INSERT OR IGNORE INTO signals VALUES(?,?,?,?,?,?,?)",
            (p.signal_id,p.symbol,p.side,p.decision,p.signal_ms,json.dumps(p.__dict__),iso()))
        self.c.commit()
    def open(self,p,now_ms):
        if self.open_trade(): return False
        self.c.execute("""INSERT OR IGNORE INTO trades(
          trade_id,signal_id,symbol,side,entry,stop,target,qty,risk,opened_ms,last_check_ms,outcome,pnl,r_net
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0,0)""",
          ("slow_"+p.signal_id,p.signal_id,p.symbol,p.side,p.entry,p.stop,p.target,p.qty,p.risk_usdt,now_ms,now_ms,"OPEN"))
        self.c.commit(); return True
    def mark_checked(self,trade_id,ms):
        self.c.execute("UPDATE trades SET last_check_ms=? WHERE trade_id=?",(ms,trade_id)); self.c.commit()
    def close(self,t,px,outcome,closed_ms):
        sg=1 if t["side"]=="LONG" else -1
        gross=(px-t["entry"])*sg*t["qty"]
        fees=(t["entry"]+px)*t["qty"]*(COST/2)
        pnl=gross-fees; r=pnl/t["risk"] if t["risk"] else 0
        self.c.execute("""UPDATE trades SET closed_ms=?,exit=?,outcome=?,pnl=?,r_net=?,last_check_ms=?
                          WHERE trade_id=?""",(closed_ms,px,outcome,pnl,r,closed_ms,t["trade_id"]))
        self.c.commit()
    def equity(self):
        r=self.c.execute("SELECT COALESCE(SUM(pnl),0) z FROM trades WHERE outcome!='OPEN'").fetchone()
        return START_EQUITY+float(r["z"] or 0)
    def recent(self,n=20):
        return [dict(r) for r in self.c.execute("SELECT * FROM trades ORDER BY COALESCE(closed_ms,opened_ms) DESC LIMIT ?",(n,)).fetchall()]

db=Store(DB_PATH)

class OKX:
    def __init__(self):
        self.h=httpx.AsyncClient(timeout=12,headers={"User-Agent":"MRC-Slow-Staging/2.0"})
    async def g(self,path,**params):
        r=await self.h.get(BASE+path,params=params); r.raise_for_status()
        j=r.json()
        if j.get("code")!="0": raise RuntimeError(f"OKX {j.get('code')} {j.get('msg')}")
        return j.get("data") or []
    async def snapshot(self,s):
        inst=INST[s]
        h1,h4,tick=await asyncio.gather(
            self.g("/api/v5/market/candles",instId=inst,bar="1H",limit="120"),
            self.g("/api/v5/market/candles",instId=inst,bar="4H",limit="120"),
            self.g("/api/v5/market/ticker",instId=inst),
        )
        return h1,h4,tick[0] if tick else {}
    async def minute_rows(self,s):
        return await self.g("/api/v5/market/candles",instId=INST[s],bar="1m",limit="300")
    async def close(self): await self.h.aclose()

def one_minute(rows,cutoff):
    out=[]
    for r in rows:
        if len(r)<9 or str(r[8])!="1": continue
        ot=int(r[0]); ct=ot+eng.MINUTE
        if ct<=cutoff:
            out.append({"ot":ot,"ct":ct,"o":eng.f(r[1]),"h":eng.f(r[2]),"l":eng.f(r[3]),"c":eng.f(r[4])})
    return sorted(out,key=lambda x:x["ot"])

STATE={"started_at":iso(),"heartbeat":0.0,"symbols":{},"last_error":None,"strategy":eng.STRATEGY,
       "mode":"PAPER_STAGING","version":"slow-staging-v2","coverage_gap":None}
LOCK=asyncio.Lock(); TASK=None

async def manage_open(client,now_ms):
    t=db.open_trade()
    if not t:
        STATE["coverage_gap"]=None; return
    rows=one_minute(await client.minute_rows(t["symbol"]),now_ms)
    rows=[b for b in rows if b["ct"]>int(t["last_check_ms"] or t["opened_ms"])]
    if not rows:
        return
    oldest=rows[0]["ot"]
    expected=int(t["last_check_ms"] or t["opened_ms"])
    if oldest>expected+eng.MINUTE:
        STATE["coverage_gap"]=f"{t['symbol']} 1M_COVERAGE_GAP from {iso(expected)} to {iso(oldest)}"
        return
    STATE["coverage_gap"]=None
    ex=eng.exit_from_1m(t,rows,now_ms)
    if ex:
        outcome,px,closed_ms=ex; db.close(t,px,outcome,closed_ms)
    else:
        db.mark_checked(t["trade_id"],rows[-1]["ct"])

async def loop():
    client=OKX()
    fresh_boot=True
    try:
        while True:
            now_ms=int(time.time()*1000); errors=[]
            try: await manage_open(client,now_ms)
            except Exception as e: errors.append(f"position: {type(e).__name__}: {e}")
            slot=db.open_trade() is not None
            for s in SYMBOLS:
                try:
                    h1,h4,t=await client.snapshot(s)
                    bid=eng.f(t.get("bidPx")); ask=eng.f(t.get("askPx"))
                    closed=eng.confirmed(h1,eng.HOUR,now_ms)
                    current_close=closed[-1]["ct"] if closed else 0
                    key="last_processed_1h_close:"+s
                    raw=db.get(key); last=int(raw) if raw is not None else None
                    process,newmark=eng.should_process(last,current_close,fresh_boot)
                    ctx,p=eng.evaluate(s,h1,h4,bid,ask,now_ms,db.equity(),RISK_PCT,slot_open=slot,daily_locked=False)
                    action="WATERMARK_ONLY"
                    if current_close:
                        db.set(key,newmark)
                    if process and p:
                        db.record_signal(p); action=p.decision
                        if p.decision in ("LONG","SHORT") and not slot and not STATE["coverage_gap"]:
                            if db.open(p,now_ms): slot=True; action="PAPER_OPEN"
                    async with LOCK:
                        STATE["symbols"][s]={"context":ctx,"candidate":p.__dict__ if p else None,
                                             "watermark":newmark if current_close else None,
                                             "processed_this_cycle":bool(process),"action":action,"error":None}
                except Exception as e:
                    msg=f"{type(e).__name__}: {e}"; errors.append(f"{s}: {msg}")
                    async with LOCK:
                        STATE["symbols"][s]={"context":{"ready":False,"state":"DATA_ERROR"},"candidate":None,"error":msg}
            fresh_boot=False
            async with LOCK:
                STATE["heartbeat"]=time.time(); STATE["last_error"]=" | ".join(errors) if errors else None
                STATE["position"]=db.open_trade(); STATE["equity"]=round(db.equity(),2); STATE["recent_trades"]=db.recent()
            await asyncio.sleep(POLL)
    finally:
        await client.close()

@asynccontextmanager
async def life(app):
    global TASK
    TASK=asyncio.create_task(loop())
    yield
    TASK.cancel()

app=FastAPI(title="MRC Slow Trend Staging",version="2.0",lifespan=life)

def checks():
    return {s:bool(STATE["symbols"].get(s,{}).get("context",{}).get("ready") and not STATE["symbols"].get(s,{}).get("error")) for s in SYMBOLS}

@app.get("/healthz")
async def health():
    age=time.time()-STATE.get("heartbeat",0); ck=checks()
    process_ok=TASK is not None and not TASK.done() and age<90
    ok=bool(process_ok and ck and all(ck.values()) and not STATE.get("coverage_gap"))
    return JSONResponse({"ok":ok,"feed_ready":bool(ck and all(ck.values())),"checks":ck,
                         "coverage_gap":STATE.get("coverage_gap"),"heartbeat_age_s":round(age,1),
                         "strategy":eng.STRATEGY,"last_error":STATE.get("last_error")},
                        status_code=200 if ok else 503)

@app.get("/readyz")
async def ready():
    ck=checks(); ok=bool(ck and all(ck.values()) and not STATE.get("coverage_gap"))
    return JSONResponse({"ready":ok,"checks":ck,"coverage_gap":STATE.get("coverage_gap"),
                         "strategy":eng.STRATEGY,"mode":"PAPER_STAGING"},
                        status_code=200 if ok else 503)

@app.get("/api/state")
async def api_state():
    async with LOCK: return json.loads(json.dumps(STATE,default=str))

@app.get("/",response_class=HTMLResponse)
async def root():
    return """<html><body style='background:#071019;color:#eaf2f8;font-family:system-ui;padding:28px'>
    <h1>MRC Slow Trend — STAGING</h1><p>4H EMA20/50 + 1H Donchian20 + ATR14 · PAPER ONLY</p>
    <p><a style='color:#70c7ff' href='/api/state'>State JSON</a> · <a style='color:#70c7ff' href='/readyz'>Readiness</a></p>
    <div id='x'>loading…</div><script>
    async function g(){let r=await fetch('/api/state'),x=await r.json();
    document.querySelector('#x').innerHTML='<pre>'+JSON.stringify(x,null,2)+'</pre>'};g();setInterval(g,10000)
    </script></body></html>"""
