from __future__ import annotations
import asyncio, base64, hashlib, json, math, os, sqlite3, time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

SYMBOLS=tuple(x.strip().upper() for x in os.getenv('MRC_SYMBOLS','BTCUSDT,ETHUSDT').split(',') if x.strip())
POLL=int(os.getenv('MRC_POLL_SECONDS','15')); START_EQ=float(os.getenv('MRC_PAPER_EQUITY','10000'))
RISK_PCT=min(float(os.getenv('MRC_RISK_PCT','0.0025')),0.005); COST=float(os.getenv('MRC_ROUNDTRIP_COST','0.0006'))
TOKEN=os.getenv('MRC_DASHBOARD_TOKEN','').strip(); DB=os.getenv('MRC_DB_PATH','/data/mrc_cloud.sqlite3')
if not Path(DB).parent.exists(): DB='/tmp/mrc_cloud.sqlite3'
BASE='https://fapi.binance.com'; HOUR=3600000

def iso(ms=None): return datetime.now(timezone.utc).isoformat() if ms is None else datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat()
def f(x,d=0.0):
    try:return float(x)
    except:return d

@dataclass
class Plan:
    symbol:str; signal_id:str; event_id:str; side:str; decision:str; confidence:int; score:float
    entry:float; stop:float; target:float; risk_usdt:float; qty:float; rr:float; chase_r:float; reason:str; created_at:str

class Store:
    def __init__(self,path):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.c=sqlite3.connect(path,check_same_thread=False); self.c.row_factory=sqlite3.Row
        self.c.execute('PRAGMA journal_mode=WAL'); self.c.executescript('''
        CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY,symbol TEXT,kind TEXT,side TEXT,payload TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS signals(signal_id TEXT PRIMARY KEY,event_id TEXT,symbol TEXT,side TEXT,decision TEXT,score REAL,confidence INTEGER,entry REAL,stop REAL,target REAL,risk_usdt REAL,qty REAL,payload TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS trades(trade_id TEXT PRIMARY KEY,signal_id TEXT,symbol TEXT,side TEXT,entry REAL,stop REAL,target REAL,qty REAL,risk_usdt REAL,opened_at TEXT,closed_at TEXT,exit REAL,outcome TEXT,pnl_usdt REAL,r_net REAL);
        '''); self.c.commit()
    def event(self,e):
        fresh=not self.c.execute('SELECT 1 FROM events WHERE event_id=?',(e['event_id'],)).fetchone(); self.c.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?)',(e['event_id'],e['symbol'],e['kind'],e.get('side',''),json.dumps(e),iso())); self.c.commit(); return fresh
    def signal(self,p):
        if self.c.execute('SELECT 1 FROM signals WHERE signal_id=?',(p.signal_id,)).fetchone(): return False
        self.c.execute('INSERT INTO signals VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(p.signal_id,p.event_id,p.symbol,p.side,p.decision,p.score,p.confidence,p.entry,p.stop,p.target,p.risk_usdt,p.qty,json.dumps(asdict(p)),p.created_at)); self.c.commit(); return True
    def openpos(self,s):
        r=self.c.execute("SELECT * FROM trades WHERE symbol=? AND outcome='OPEN' ORDER BY opened_at DESC LIMIT 1",(s,)).fetchone(); return dict(r) if r else None
    def open(self,p):
        if self.openpos(p.symbol): return
        tid='paper_'+p.signal_id; self.c.execute('INSERT OR IGNORE INTO trades(trade_id,signal_id,symbol,side,entry,stop,target,qty,risk_usdt,opened_at,outcome,pnl_usdt,r_net) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0)',(tid,p.signal_id,p.symbol,p.side,p.entry,p.stop,p.target,p.qty,p.risk_usdt,iso(),'OPEN')); self.c.commit()
    def close(self,tid,px,out):
        r=self.c.execute('SELECT * FROM trades WHERE trade_id=?',(tid,)).fetchone();
        if not r or r['outcome']!='OPEN': return
        d=dict(r); sg=1 if d['side']=='LONG' else -1; gross=(px-d['entry'])*sg*d['qty']; fees=(d['entry']+px)*d['qty']*(COST/2); pnl=gross-fees; rr=pnl/d['risk_usdt'] if d['risk_usdt'] else 0
        self.c.execute('UPDATE trades SET closed_at=?,exit=?,outcome=?,pnl_usdt=?,r_net=? WHERE trade_id=?',(iso(),px,out,pnl,rr,tid)); self.c.commit()
    def eq(self): return START_EQ+float(self.c.execute("SELECT COALESCE(SUM(pnl_usdt),0) z FROM trades WHERE outcome!='OPEN'").fetchone()['z'])
    def recent(self,t,n=20):
        order='created_at' if t in ('events','signals') else 'COALESCE(closed_at,opened_at)'; return [dict(x) for x in self.c.execute(f'SELECT * FROM {t} ORDER BY {order} DESC LIMIT ?',(n,)).fetchall()]
    def metrics(self):
        rs=[dict(x) for x in self.c.execute("SELECT * FROM trades WHERE outcome!='OPEN'").fetchall()]; vals=[f(x['r_net']) for x in rs]; n=len(vals); pos=sum(x for x in vals if x>0); neg=-sum(x for x in vals if x<0)
        return {'closed_trades':n,'paper_equity':round(self.eq(),2),'net_pnl_usdt':round(self.eq()-START_EQ,2),'expectancy_r':round(sum(vals)/n,4) if n else 0,'win_rate':round(sum(x>0 for x in vals)/n,4) if n else 0,'profit_factor':round(pos/neg,3) if neg else None}
store=Store(DB)
STATE={'started_at':iso(),'heartbeat':0.0,'symbols':{},'last_error':None,'mode':'PAPER','strategy':'OF-BOUNDARY-v1'}; LOCK=asyncio.Lock()

class Binance:
    def __init__(self): self.h=httpx.AsyncClient(timeout=10,headers={'User-Agent':'MRC-Cloud/1.0'})
    async def g(self,p,**q):
        r=await self.h.get(BASE+p,params=q); r.raise_for_status(); return r.json()
    async def snap(self,s):
        k,b,t,o,l,p=await asyncio.gather(self.g('/fapi/v1/klines',symbol=s,interval='15m',limit=20),self.g('/fapi/v1/ticker/bookTicker',symbol=s),self.g('/futures/data/takerlongshortRatio',symbol=s,period='15m',limit=3),self.g('/futures/data/openInterestHist',symbol=s,period='15m',limit=3),self.g('/futures/data/topLongShortPositionRatio',symbol=s,period='15m',limit=3),self.g('/fapi/v1/premiumIndex',symbol=s)); return {'k':k,'b':b,'t':t,'o':o,'l':l,'p':p}
    async def close(self): await self.h.aclose()

def bar(x): return {'ot':int(x[0]),'o':f(x[1]),'h':f(x[2]),'l':f(x[3]),'c':f(x[4]),'ct':int(x[6])}
def event(s,raw,now):
    bs=[bar(x) for x in raw['k'] if int(x[6])<=now]; ch=(now//HOUR)*HOUR; ph=ch-HOUR; prev=[x for x in bs if ph<=x['ot']<ch]; cur=[x for x in bs if ch<=x['ot']<ch+HOUR]
    ctx={'current_hour':iso(ch),'previous_hour':iso(ph),'closed_current_bars':len(cur)}
    if len(prev)!=4:return None,{**ctx,'status':'WARMING'}
    hi=max(x['h'] for x in prev); lo=min(x['l'] for x in prev); R=hi-lo; ctx|={'prev_high':hi,'prev_low':lo,'range_r':R}
    for x in cur:
        up=x['h']>hi; dn=x['l']<lo
        if not(up or dn):continue
        eid=f'{s}:{ch}'
        if up and dn:return {'event_id':eid,'symbol':s,'kind':'AMBIGUOUS','side':'','R':R,'signal_ms':x['ct'],'bar':x},ctx|{'status':'AMBIGUOUS'}
        if up: kind='ACCEPTANCE' if x['c']>hi else 'REJECTION'; side='LONG'; bd=hi
        else: kind='ACCEPTANCE' if x['c']<lo else 'REJECTION'; side='SHORT'; bd=lo
        e={'event_id':eid,'symbol':s,'kind':kind,'side':side,'R':R,'boundary':bd,'signal_ms':x['ct'],'bar':x,'prev_high':hi,'prev_low':lo}; return e,ctx|{'status':kind,'side':side,'signal_at':iso(x['ct'])}
    return None,ctx|{'status':'WAIT_BOUNDARY_TEST'}

def flow(raw,side):
    d=1 if side=='LONG' else -1; t=raw['t']; o=raw['o']; l=raw['l']; ratio=f(t[-1].get('buySellRatio'),1) if t else 1; ti=math.log(max(ratio,1e-9))*d; on=f(o[-1].get('sumOpenInterest')) if o else 0; op=f(o[-2].get('sumOpenInterest')) if len(o)>1 else on; doi=on/op-1 if op else 0; ln=f(l[-1].get('longShortRatio'),1) if l else 1; lp=f(l[-2].get('longShortRatio'),ln) if len(l)>1 else ln; dls=(ln/lp-1 if lp else 0)*d; fund=f(raw['p'].get('lastFundingRate')); return {'taker_ratio':ratio,'aligned_taker_log':ti,'doi':doi,'top_ls':ln,'aligned_dls':dls,'funding':fund,'aligned_funding':fund*d}
def plan(e,raw,eq,now):
    fl=flow(raw,e['side']); sc=.75; why=['acceptance outside previous UTC-hour boundary']
    if fl['aligned_taker_log']>math.log(1.10):sc+=1;why+=['aggressive taker flow aligned']
    elif fl['aligned_taker_log']>0:sc+=.4;why+=['taker flow mildly aligned']
    else:sc-=.5;why+=['taker flow opposed']
    if fl['doi']>0:sc+=.75;why+=['open interest expanding']
    else:sc-=.25;why+=['open interest not expanding']
    if fl['aligned_dls']>0:sc+=.4;why+=['top-trader change aligned']
    elif fl['aligned_dls']<0:sc-=.2;why+=['top-trader change opposed']
    if fl['aligned_funding']>.0005:sc-=.25;why+=['funding crowding penalty']
    bid=f(raw['b']['bidPrice']); ask=f(raw['b']['askPrice']); en=ask if e['side']=='LONG' else bid; R=e['R']; bd=e['boundary']; chase=(en-bd)/R if e['side']=='LONG' else (bd-en)/R; age=(now-e['signal_ms'])/60000; decision=e['side'] if sc>=1.75 and chase<=.20 and age<=20 else 'NO_TRADE'
    if chase>.20:why+=['too extended'];
    if age>20:why+=['stale event'];
    if sc<1.75:why+=['score below threshold']
    st=bd-.25*R if e['side']=='LONG' else bd+.25*R; risk=eq*RISK_PCT; per=abs(en-st); qty=min(risk/per if per else 0,eq/en if en else 0); tg=en+1.5*per if e['side']=='LONG' else en-1.5*per; sid=hashlib.sha256((e['event_id']+str(e['signal_ms'])).encode()).hexdigest()[:24]; conf=max(1,min(99,int(50+15*(sc-1.5)))); why+=[f"TI={fl['taker_ratio']:.3f} dOI={fl['doi']*100:.3f}%"]
    return Plan(e['symbol'],sid,e['event_id'],e['side'],decision,conf,round(sc,3),en,st,tg,risk,qty,1.5,chase,'; '.join(why),iso())
def manage(s,raw):
    p=store.openpos(s)
    if not p:return
    bid=f(raw['b']['bidPrice']); ask=f(raw['b']['askPrice'])
    if p['side']=='LONG':
        if bid<=p['stop']:store.close(p['trade_id'],bid,'STOP')
        elif bid>=p['target']:store.close(p['trade_id'],bid,'TARGET')
    else:
        if ask>=p['stop']:store.close(p['trade_id'],ask,'STOP')
        elif ask<=p['target']:store.close(p['trade_id'],ask,'TARGET')
async def loop():
    c=Binance()
    try:
        while True:
            now=int(time.time()*1000)
            for s in SYMBOLS:
                try:
                    raw=await c.snap(s); manage(s,raw); e,ctx=event(s,raw,now); pd=None
                    if e:
                        store.event(e)
                        if e['kind']=='ACCEPTANCE':
                            p=plan(e,raw,store.eq(),now); pd=asdict(p)
                            if store.signal(p) and p.decision in ('LONG','SHORT'):store.open(p)
                        elif e['kind']=='REJECTION':pd={'decision':'NO_TRADE','reason':'rejection recorded for research'}
                    async with LOCK:STATE['symbols'][s]={'context':ctx,'event':e,'plan':pd,'flow':flow(raw,e['side']) if e and e.get('side') else {},'book':{'bid':f(raw['b']['bidPrice']),'ask':f(raw['b']['askPrice'])},'position':store.openpos(s)};STATE['last_error']=None
                except Exception as ex:
                    async with LOCK:STATE['symbols'].setdefault(s,{})['error']=f'{type(ex).__name__}: {ex}';STATE['last_error']=f'{s}: {type(ex).__name__}: {ex}'
            async with LOCK:STATE['heartbeat']=time.time();STATE['metrics']=store.metrics()
            await asyncio.sleep(POLL)
    finally:await c.close()
TASK=None
@asynccontextmanager
async def life(app):
    global TASK;TASK=asyncio.create_task(loop());yield;TASK.cancel()
app=FastAPI(title='MRC Cloud Cockpit',version='1.0',lifespan=life)
@app.middleware('http')
async def auth(req:Request,call_next):
    if not TOKEN or req.url.path in ('/healthz','/readyz'):return await call_next(req)
    h=req.headers.get('authorization','');ok=False
    if h.startswith('Basic '):
        try:u,p=base64.b64decode(h[6:]).decode().split(':',1);ok=(u=='mrc' and p==TOKEN)
        except:pass
    if not ok:return PlainTextResponse('Authentication required',401,headers={'WWW-Authenticate':'Basic realm=MRC'})
    return await call_next(req)
@app.get('/healthz')
async def health():
    age=time.time()-STATE.get('heartbeat',0);ok=TASK is not None and not TASK.done() and age<max(90,POLL*4);return JSONResponse({'ok':ok,'heartbeat_age_s':round(age,1),'last_error':STATE.get('last_error')},status_code=200 if ok else 503)
@app.get('/readyz')
async def ready():
    ok=bool(STATE.get('symbols')) and STATE.get('heartbeat',0)>0;return JSONResponse({'ready':ok,'symbols':list(STATE.get('symbols',{}))},status_code=200 if ok else 503)
@app.get('/api/state')
async def state():
    async with LOCK:x=json.loads(json.dumps(STATE,default=str))
    x['recent_signals']=store.recent('signals');x['recent_trades']=store.recent('trades');x['recent_events']=store.recent('events');x['metrics']=store.metrics();return x
HTML='''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>MRC Cloud Cockpit</title><style>body{margin:0;background:#071019;color:#eaf2f8;font:14px system-ui}header{padding:22px;border-bottom:1px solid #203347}.wrap{max-width:1400px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:14px}.card{background:#0e1a26;border:1px solid #203347;border-radius:14px;padding:16px}.big{font-size:28px;font-weight:800}.row{display:flex;justify-content:space-between;margin:7px 0}.muted{color:#86a1b8}.long{color:#37d67a}.short{color:#ff5d73}.warn{color:#ffc857}table{width:100%;border-collapse:collapse;background:#0e1a26}td,th{padding:9px;border-bottom:1px solid #203347;text-align:left;font-size:12px}</style></head><body><header><b style="font-size:22px">MRC Cloud Cockpit</b><div class=muted>Real Binance data • PAPER ONLY</div></header><main class=wrap><div id=m class=grid></div><h3>Live decisions</h3><div id=s class=grid></div><h3>Paper trades</h3><div id=t></div></main><script>const n=(x,d=2)=>x==null?'—':Number(x).toLocaleString('en-US',{maximumFractionDigits:d});async function go(){let r=await fetch('/api/state'),x=await r.json(),m=x.metrics||{};document.querySelector('#m').innerHTML=`<div class=card><span class=muted>Equity</span><div class=big>$${n(m.paper_equity)}</div></div><div class=card><span class=muted>Trades</span><div class=big>${m.closed_trades||0}</div></div><div class=card><span class=muted>Expectancy</span><div class=big>${n(m.expectancy_r,3)}R</div></div>`;let h='';for(let [k,v] of Object.entries(x.symbols||{})){let c=v.context||{},p=v.plan||{},q=v.flow||{},b=v.book||{},d=p.decision||c.status||'WAIT';h+=`<div class=card><div class=row><b>${k}</b><b class=${d==='LONG'?'long':d==='SHORT'?'short':'warn'}>${d}</b></div><div class=big>${n((b.bid+b.ask)/2)}</div><div class=row><span>Event</span><span>${c.status||'—'}</span></div><div class=row><span>Range</span><span>${n(c.prev_low)} → ${n(c.prev_high)}</span></div><div class=row><span>Score</span><span>${n(p.score,2)} / ${p.confidence||'—'}%</span></div><div class=row><span>Taker B/S</span><span>${n(q.taker_ratio,3)}</span></div><div class=row><span>ΔOI</span><span>${n((q.doi||0)*100,3)}%</span></div>${p.entry?`<hr><div class=row><span>Entry</span><b>${n(p.entry)}</b></div><div class=row><span>Stop</span><b>${n(p.stop)}</b></div><div class=row><span>Target</span><b>${n(p.target)}</b></div><div class=muted>${p.reason}</div>`:''}</div>`}document.querySelector('#s').innerHTML=h;let a=x.recent_trades||[];document.querySelector('#t').innerHTML=a.length?'<table><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Outcome</th><th>P&L</th><th>R</th></tr>'+a.map(z=>`<tr><td>${z.closed_at||z.opened_at}</td><td>${z.symbol}</td><td>${z.side}</td><td>${z.outcome}</td><td>$${n(z.pnl_usdt)}</td><td>${n(z.r_net,3)}</td></tr>`).join('')+'</table>':'<div class=muted>No paper trades yet.</div>'}go();setInterval(go,10000)</script></body></html>'''
@app.get('/',response_class=HTMLResponse)
async def root():return HTML
