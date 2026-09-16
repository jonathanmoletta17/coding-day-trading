from __future__ import annotations
import asyncio, base64, hashlib, json, math, os, sqlite3, time
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

MAP={'BTCUSDT':('BTC-USDT-SWAP','BTC'),'ETHUSDT':('ETH-USDT-SWAP','ETH')}
SYMS=tuple(s.strip().upper() for s in os.getenv('MRC_SYMBOLS','BTCUSDT,ETHUSDT').split(',') if s.strip().upper() in MAP)
POLL=max(10,int(os.getenv('MRC_POLL_SECONDS','15'))); EQ0=float(os.getenv('MRC_PAPER_EQUITY','10000'))
RISK=min(float(os.getenv('MRC_RISK_PCT','0.0025')),0.005); COST=float(os.getenv('MRC_ROUNDTRIP_COST','0.0006'))
TOKEN=os.getenv('MRC_DASHBOARD_TOKEN','').strip(); DB=os.getenv('MRC_DB_PATH','/data/mrc_cloud.sqlite3')
if not Path(DB).parent.exists(): DB='/tmp/mrc_cloud.sqlite3'
BASE='https://www.okx.com'; STRAT='TREND_BREAKOUT_V1'; M5=300000; M15=900000
STOP_ATR=1.5; TARGET_R=2.0; MAX_AGE=20; MAX_CHASE=.5; MAX_HOLD=24; DAILY_LOCK=.01

def iso(ms=None): return datetime.now(timezone.utc).isoformat() if ms is None else datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat()
def f(x,d=0.0):
    try:
        y=float(x); return y if math.isfinite(y) else d
    except: return d

def ema(xs,n):
    a=2/(n+1); z=xs[0]
    for x in xs[1:]: z=a*x+(1-a)*z
    return z

def atr(bs,n=14):
    tr=[max(bs[i]['h']-bs[i]['l'],abs(bs[i]['h']-bs[i-1]['c']),abs(bs[i]['l']-bs[i-1]['c'])) for i in range(1,len(bs))]
    if not tr:return 0
    z=sum(tr[:n])/min(n,len(tr))
    for x in tr[n:]: z=((n-1)*z+x)/n
    return z

@dataclass
class Plan:
    symbol:str; signal_id:str; side:str; decision:str; entry:float; stop:float; target:float; atr:float
    risk_usdt:float; qty:float; rr:float; signal_ms:int; age_min:float; chase_atr:float; reason:str; created_at:str

class DB:
    def __init__(self,p):
        Path(p).parent.mkdir(parents=True,exist_ok=True); self.c=sqlite3.connect(p,check_same_thread=False); self.c.row_factory=sqlite3.Row
        self.c.execute('PRAGMA journal_mode=WAL'); self.c.execute('PRAGMA synchronous=FULL'); self.c.executescript('''
        CREATE TABLE IF NOT EXISTS tb_signals(signal_id TEXT PRIMARY KEY,symbol TEXT,side TEXT,decision TEXT,entry REAL,stop REAL,target REAL,risk REAL,qty REAL,payload TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS tb_trades(trade_id TEXT PRIMARY KEY,signal_id TEXT,symbol TEXT,side TEXT,entry REAL,stop REAL,target REAL,qty REAL,risk REAL,opened_at TEXT,closed_at TEXT,exit REAL,outcome TEXT,pnl REAL,r_net REAL);
        '''); self.c.commit()
    def pos(self,s=None):
        q="SELECT * FROM tb_trades WHERE outcome='OPEN'"; a=[]
        if s:q+=' AND symbol=?';a=[s]
        q+=' ORDER BY opened_at DESC LIMIT 1'; r=self.c.execute(q,a).fetchone(); return dict(r) if r else None
    def signal(self,p):
        if self.c.execute('SELECT 1 FROM tb_signals WHERE signal_id=?',(p.signal_id,)).fetchone(): return False
        self.c.execute('INSERT INTO tb_signals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(p.signal_id,p.symbol,p.side,p.decision,p.entry,p.stop,p.target,p.risk_usdt,p.qty,json.dumps(asdict(p)),p.created_at));self.c.commit();return True
    def open(self,p):
        if self.pos():return
        self.c.execute('INSERT OR IGNORE INTO tb_trades(trade_id,signal_id,symbol,side,entry,stop,target,qty,risk,opened_at,outcome,pnl,r_net) VALUES(?,?,?,?,?,?,?,?,?,?,?,0,0)',('paper_'+p.signal_id,p.signal_id,p.symbol,p.side,p.entry,p.stop,p.target,p.qty,p.risk_usdt,iso(),'OPEN'));self.c.commit()
    def close(self,tid,px,out):
        r=self.c.execute('SELECT * FROM tb_trades WHERE trade_id=?',(tid,)).fetchone()
        if not r or r['outcome']!='OPEN':return
        d=dict(r);sg=1 if d['side']=='LONG' else -1;gross=(px-d['entry'])*sg*d['qty'];fees=(d['entry']+px)*d['qty']*(COST/2);pnl=gross-fees;rn=pnl/d['risk'] if d['risk'] else 0
        self.c.execute('UPDATE tb_trades SET closed_at=?,exit=?,outcome=?,pnl=?,r_net=? WHERE trade_id=?',(iso(),px,out,pnl,rn,tid));self.c.commit()
    def eq(self):return EQ0+f(self.c.execute("SELECT COALESCE(SUM(pnl),0) z FROM tb_trades WHERE outcome!='OPEN'").fetchone()['z'])
    def day(self):
        d=datetime.now(timezone.utc).date().isoformat();return f(self.c.execute("SELECT COALESCE(SUM(pnl),0) z FROM tb_trades WHERE outcome!='OPEN' AND substr(closed_at,1,10)=?",(d,)).fetchone()['z'])
    def recent(self,n=30):return [dict(x) for x in self.c.execute('SELECT * FROM tb_trades ORDER BY COALESCE(closed_at,opened_at) DESC LIMIT ?',(n,)).fetchall()]
    def metrics(self):
        xs=[f(x['r_net']) for x in self.c.execute("SELECT r_net FROM tb_trades WHERE outcome!='OPEN'").fetchall()]; n=len(xs);pos=sum(x for x in xs if x>0);neg=-sum(x for x in xs if x<0);eq=self.eq()
        return {'equity':round(eq,2),'trades':n,'expectancy_r':round(sum(xs)/n,4) if n else 0,'win_rate':round(sum(x>0 for x in xs)/n,4) if n else 0,'pf':round(pos/neg,3) if neg else None,'day_pnl':round(self.day(),2),'net_pnl':round(eq-EQ0,2)}
db=DB(DB)

class OKX:
    def __init__(self):self.h=httpx.AsyncClient(timeout=12,headers={'User-Agent':'MRC-TrendBreakout/1.0'})
    async def g(self,p,**q):
        r=await self.h.get(BASE+p,params=q);r.raise_for_status();j=r.json()
        if j.get('code')!='0':raise RuntimeError(f"OKX {j.get('code')} {j.get('msg')}")
        return j.get('data',[])
    async def snap(self,s):
        inst,ccy=MAP[s]
        a,b,t,fu,tk,oi,ls=await asyncio.gather(self.g('/api/v5/market/candles',instId=inst,bar='15m',limit='120'),self.g('/api/v5/market/candles',instId=inst,bar='1H',limit='120'),self.g('/api/v5/market/ticker',instId=inst),self.g('/api/v5/public/funding-rate',instId=inst),self.g('/api/v5/rubik/stat/taker-volume',ccy=ccy,instType='CONTRACTS',period='5m'),self.g('/api/v5/rubik/stat/contracts/open-interest-volume',ccy=ccy,period='5m'),self.g('/api/v5/rubik/stat/contracts/long-short-account-ratio',ccy=ccy,period='5m'))
        return {'c15':a,'c1h':b,'tick':t[0] if t else {},'fund':fu[0] if fu else {},'taker':tk,'oi':oi,'ls':ls}
    async def close(self):await self.h.aclose()

def bars(rows,mins):
    z=[]
    for r in rows:
        if len(r)<9 or str(r[8])!='1':continue
        z.append({'ot':int(r[0]),'o':f(r[1]),'h':f(r[2]),'l':f(r[3]),'c':f(r[4]),'v':f(r[5]),'ct':int(r[0])+mins*60000})
    return sorted(z,key=lambda x:x['ot'])
def done5(rows,cut):return sorted([r for r in rows if int(r[0])+M5<=cut],key=lambda r:int(r[0]))
def flow(raw,cut):
    t=done5(raw['taker'],cut);o=done5(raw['oi'],cut);l=done5(raw['ls'],cut);buy=f(t[-1][1]) if t else 0;sell=f(t[-1][2]) if t else 0;on=f(o[-1][1]) if o else 0;op=f(o[-2][1]) if len(o)>1 else on;ln=f(l[-1][1]) if l else 0;lp=f(l[-2][1]) if len(l)>1 else ln
    return {'taker_ratio':buy/sell if sell else None,'doi':on/op-1 if op else 0,'ls':ln,'dls':ln/lp-1 if lp else 0,'funding':f(raw['fund'].get('fundingRate'))}

def analyze(s,raw,now):
    b15=bars(raw['c15'],15);b1=bars(raw['c1h'],60);tick=raw['tick'];bid=f(tick.get('bidPx'));ask=f(tick.get('askPx'));last=f(tick.get('last'));px=(bid+ask)/2 if bid and ask else last
    if len(b15)<35 or len(b1)<60 or not px:return {'ready':False,'status':'WARMING','price':px or None,'reason':'waiting for enough confirmed candles'},None
    sig=b15[-1];prev=b15[-21:-1];up=max(x['h'] for x in prev);dn=min(x['l'] for x in prev);a=atr(b15[-40:]);e20=ema([x['c'] for x in b1],20);e50=ema([x['c'] for x in b1],50);trend='UP' if e20>e50 else 'DOWN' if e20<e50 else 'NEUTRAL';br='LONG' if sig['c']>up else 'SHORT' if sig['c']<dn else 'NONE';match=(br=='LONG' and trend=='UP') or (br=='SHORT' and trend=='DOWN');sm=sig['ct'];age=max(0,(now-sm)/60000);entry=ask if br=='LONG' else bid if br=='SHORT' else px;chase=abs(entry-sig['c'])/a if a and br!='NONE' else 0;of=flow(raw,sm if br!='NONE' else now)
    c={'ready':True,'status':'WAIT','price':px,'trend':trend,'ema20':e20,'ema50':e50,'don_hi':up,'don_lo':dn,'atr':a,'breakout':br,'signal_at':iso(sm),'age_min':age,'chase_atr':chase,'flow':of,'reason':'waiting for confirmed Donchian20 breakout'}
    if br=='NONE':return c,None
    if not match:c.update(status='NO_TRADE',reason=f'{br} breakout conflicts with 1H {trend} trend');return c,None
    sd=STOP_ATR*a;stop=entry-sd if br=='LONG' else entry+sd;target=entry+TARGET_R*sd if br=='LONG' else entry-TARGET_R*sd;risk=db.eq()*RISK;qty=min(risk/sd if sd else 0,db.eq()/entry if entry else 0);fresh=age<=MAX_AGE;chok=chase<=MAX_CHASE;slot=not db.pos();lock=db.day()<=-(EQ0*DAILY_LOCK);dec=br if fresh and chok and slot and not lock else 'NO_TRADE';why=[f'1H EMA20 {">" if trend=="UP" else "<"} EMA50','confirmed 15m Donchian20 breakout',f'1.5 ATR stop / {TARGET_R:.0f}R target']
    if not fresh:why.append('stale signal')
    if not chok:why.append(f'chase {chase:.2f} ATR')
    if not slot:why.append('another position open')
    if lock:why.append('daily loss lock')
    sid=hashlib.sha256(f'{STRAT}:{s}:{sm}:{br}'.encode()).hexdigest()[:24];p=Plan(s,sid,br,dec,entry,stop,target,a,risk,qty,TARGET_R,sm,age,chase,'; '.join(why),iso());c.update(status='EXECUTABLE' if dec in ('LONG','SHORT') else 'NO_TRADE',reason=p.reason);return c,p

def manage(s,raw):
    p=db.pos(s)
    if not p:return
    bid=f(raw['tick'].get('bidPx'));ask=f(raw['tick'].get('askPx'));px=bid if p['side']=='LONG' else ask
    if p['side']=='LONG':
        if bid<=p['stop']:return db.close(p['trade_id'],bid,'STOP')
        if bid>=p['target']:return db.close(p['trade_id'],bid,'TARGET')
    else:
        if ask>=p['stop']:return db.close(p['trade_id'],ask,'STOP')
        if ask<=p['target']:return db.close(p['trade_id'],ask,'TARGET')
    try:
        t=datetime.fromisoformat(p['opened_at']);t=t if t.tzinfo else t.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc)-t).total_seconds()>=MAX_HOLD*3600 and px:db.close(p['trade_id'],px,'TIME')
    except:pass

STATE={'started_at':iso(),'heartbeat':0,'source':'OKX public perpetual swaps','strategy':STRAT,'mode':'PAPER','symbols':{},'last_error':None};LOCK=asyncio.Lock();TASK=None
async def loop():
    c=OKX()
    try:
        while True:
            now=int(time.time()*1000);errs=[]
            for s in SYMS:
                try:
                    raw=await c.snap(s);manage(s,raw);ctx,p=analyze(s,raw,now)
                    if p and db.signal(p) and p.decision in ('LONG','SHORT'):db.open(p)
                    async with LOCK:STATE['symbols'][s]={'context':ctx,'plan':asdict(p) if p else None,'position':db.pos(s),'error':None}
                except Exception as e:
                    msg=f'{type(e).__name__}: {e}';errs.append(f'{s}: {msg}')
                    async with LOCK:STATE['symbols'][s]={'context':{'ready':False,'status':'DATA_ERROR','reason':msg},'plan':None,'position':db.pos(s),'error':msg}
            async with LOCK:STATE['heartbeat']=time.time();STATE['last_error']=' | '.join(errs) if errs else None;STATE['metrics']=db.metrics()
            await asyncio.sleep(POLL)
    finally:await c.close()
@asynccontextmanager
async def life(app):
    global TASK;TASK=asyncio.create_task(loop());yield;TASK.cancel()
app=FastAPI(title='MRC Quant Desk',version='4.0',lifespan=life)
@app.middleware('http')
async def auth(req:Request,call_next):
    if not TOKEN or req.url.path in ('/healthz','/readyz'):return await call_next(req)
    h=req.headers.get('authorization','');ok=False
    if h.startswith('Basic '):
        try:u,p=base64.b64decode(h[6:]).decode().split(':',1);ok=(u=='mrc' and p==TOKEN)
        except:pass
    if not ok:return PlainTextResponse('Authentication required',401,headers={'WWW-Authenticate':'Basic realm=MRC'})
    return await call_next(req)
def checks():return {s:bool(STATE['symbols'].get(s,{}).get('context',{}).get('ready') and not STATE['symbols'].get(s,{}).get('error')) for s in SYMS}
@app.get('/healthz')
async def health():
    age=time.time()-STATE.get('heartbeat',0);ck=checks();ok=TASK is not None and not TASK.done() and age<90 and ck and all(ck.values());return JSONResponse({'ok':bool(ok),'feed_ready':bool(ck and all(ck.values())),'strategy':STRAT,'heartbeat_age_s':round(age,1),'last_error':STATE.get('last_error')},status_code=200 if ok else 503)
@app.get('/readyz')
async def ready():
    ck=checks();ok=bool(ck and all(ck.values()));return JSONResponse({'ready':ok,'strategy':STRAT,'checks':ck,'last_error':STATE.get('last_error')},status_code=200 if ok else 503)
@app.get('/api/state')
async def state():
    async with LOCK:x=json.loads(json.dumps(STATE,default=str))
    x['metrics']=db.metrics();x['trades']=db.recent();x['checks']=checks();x['spec']={'trend':'1H EMA20 vs EMA50','trigger':'confirmed 15m close beyond prior Donchian20','stop':'1.5 x ATR14','target':'2R','risk':f'{RISK*100:.2f}% paper equity','max chase':'0.50 ATR','max age':'20m','time stop':'24h','daily loss lock':'1%','order-flow':'context only'};return x
HTML='''<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>MRC Quant Desk</title><style>body{margin:0;background:#06111a;color:#eef7ff;font:14px system-ui}header{padding:20px;border-bottom:1px solid #203648;display:flex;justify-content:space-between;flex-wrap:wrap}.w{max-width:1450px;margin:auto;padding:20px}.g{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}.s{grid-template-columns:repeat(auto-fit,minmax(430px,1fr))}.c{background:#0d1c29;border:1px solid #203648;border-radius:14px;padding:16px}.b{font-size:27px;font-weight:800}.r{display:flex;justify-content:space-between;gap:12px;margin:7px 0}.m{color:#8da9bc}.L{color:#39df84}.S{color:#ff6577}.W{color:#ffc857}.e{background:#35151a}.p{background:#091722;border:1px solid #29485e;border-radius:10px;padding:11px;margin-top:12px}table{width:100%;border-collapse:collapse}.c td,.c th{padding:8px;border-bottom:1px solid #203648;text-align:left;font-size:12px}</style></head><body><header><div><b style="font-size:23px">MRC Quant Desk</b><div class=m>Simple System v1 · Trend + Breakout + ATR · PAPER</div></div><b id=f class=W>CONNECTING</b></header><main class=w><div id=a></div><div id=k class=g></div><h3>Operação agora</h3><div id=s class="g s"></div><h3>Regras congeladas</h3><div id=sp class=c></div><h3>Paper trades</h3><div id=t class=c></div></main><script>const N=(x,d=2)=>Number.isFinite(Number(x))?Number(x).toLocaleString('en-US',{maximumFractionDigits:d}):'—';const P=(x,d=2)=>Number.isFinite(Number(x))?(Number(x)*100).toFixed(d)+'%':'—';const C=x=>x==='LONG'||x==='EXECUTABLE'?'L':x==='SHORT'?'S':'W';async function G(){try{let r=await fetch('/api/state'),x=await r.json(),m=x.metrics||{},ok=Object.values(x.checks||{}).length&&Object.values(x.checks||{}).every(Boolean);f.textContent=ok?'FEED READY':'FEED NOT READY';f.className=ok?'L':'W';a.innerHTML=x.last_error?`<div class="c e">${x.last_error}</div>`:'';k.innerHTML=`<div class=c><span class=m>Equity</span><div class=b>$${N(m.equity)}</div></div><div class=c><span class=m>Trades</span><div class=b>${m.trades||0}</div></div><div class=c><span class=m>Expectancy</span><div class=b>${N(m.expectancy_r,3)}R</div></div><div class=c><span class=m>P&L hoje</span><div class=b>$${N(m.day_pnl)}</div></div>`;let h='';for(let [z,v] of Object.entries(x.symbols||{})){let q=v.context||{},p=v.plan||{},o=q.flow||{},d=p.decision||q.status||'WAIT';h+=`<div class="c ${v.error?'e':''}"><div class=r><b>${z}</b><b class=${C(d)}>${d}</b></div><div class=b>${N(q.price)}</div><div class=r><span>Trend 1H</span><b class=${q.trend==='UP'?'L':q.trend==='DOWN'?'S':'W'}>${q.trend||'—'}</b></div><div class=r><span>EMA20 / EMA50</span><span>${N(q.ema20)} / ${N(q.ema50)}</span></div><div class=r><span>Donchian20</span><span>${N(q.don_lo)} → ${N(q.don_hi)}</span></div><div class=r><span>Breakout</span><b>${q.breakout||'—'}</b></div><div class=r><span>ATR14</span><span>${N(q.atr)}</span></div><div class=r><span>Taker B/S</span><span>${N(o.taker_ratio,3)}</span></div><div class=r><span>ΔOI 5m</span><span>${P(o.doi,3)}</span></div><div class=r><span>Long/Short</span><span>${N(o.ls,3)}</span></div><div class=r><span>Funding</span><span>${P(o.funding,4)}</span></div><div class=m>${q.reason||''}</div>${p.entry?`<div class=p><div class=r><span>Plano</span><b class=${C(p.decision)}>${p.decision}</b></div><div class=r><span>Entry</span><b>${N(p.entry)}</b></div><div class=r><span>Stop</span><b>${N(p.stop)}</b></div><div class=r><span>Target</span><b>${N(p.target)}</b></div><div class=r><span>Risk</span><b>$${N(p.risk_usdt)}</b></div><div class=r><span>Qty</span><b>${N(p.qty,6)}</b></div><div class=r><span>Age / chase</span><span>${N(p.age_min,1)}m / ${N(p.chase_atr,2)} ATR</span></div></div>`:''}</div>`}s.innerHTML=h;sp.innerHTML=Object.entries(x.spec||{}).map(([u,v])=>`<div class=r><span class=m>${u}</span><b>${v}</b></div>`).join('');let tr=x.trades||[];t.innerHTML=tr.length?'<table><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Outcome</th><th>P&L</th><th>R</th></tr>'+tr.map(z=>`<tr><td>${z.closed_at||z.opened_at}</td><td>${z.symbol}</td><td>${z.side}</td><td>${z.outcome}</td><td>$${N(z.pnl)}</td><td>${N(z.r_net,3)}</td></tr>`).join('')+'</table>':'<span class=m>Ainda não há trades PAPER deste baseline.</span>'}catch(e){a.innerHTML=`<div class="c e">${e}</div>`}}G();setInterval(G,10000)</script></body></html>'''
@app.get('/',response_class=HTMLResponse)
async def root():return HTML
