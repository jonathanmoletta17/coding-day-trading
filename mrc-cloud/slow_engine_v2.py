from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import hashlib, math

STRATEGY='SLOW_TREND_BREAKOUT_V1'
STOP_ATR=1.5; TARGET_R=2.0; MAX_CHASE_ATR=.5; MAX_AGE_MIN=20; MAX_HOLD_H=72
MINUTE=60_000; HOUR=60*MINUTE; FOUR_HOUR=4*HOUR


def f(x:Any,d=0.0)->float:
    try:
        y=float(x); return y if math.isfinite(y) else d
    except Exception:return d


def ema(xs:list[float],n:int)->float:
    if not xs:return 0.0
    a=2/(n+1); z=xs[0]
    for x in xs[1:]:z=a*x+(1-a)*z
    return z


def atr_wilder(bs:list[dict],n:int=14)->float:
    if len(bs)<2:return 0.0
    tr=[max(bs[i]['h']-bs[i]['l'],abs(bs[i]['h']-bs[i-1]['c']),abs(bs[i]['l']-bs[i-1]['c'])) for i in range(1,len(bs))]
    if not tr:return 0.0
    z=sum(tr[:n])/min(n,len(tr))
    for x in tr[n:]:z=((n-1)*z+x)/n
    return z


def confirmed(rows:list[list[Any]],duration_ms:int,cutoff_ms:int)->list[dict]:
    out=[]
    for r in rows:
        if len(r)<9 or str(r[8])!='1':continue
        ot=int(r[0]); ct=ot+duration_ms
        if ct>cutoff_ms:continue
        out.append({'ot':ot,'ct':ct,'o':f(r[1]),'h':f(r[2]),'l':f(r[3]),'c':f(r[4])})
    return sorted(out,key=lambda x:x['ot'])


def first_full_minute_open(opened_ms:int)->int:
    """First 1m bar open that is not contaminated by time before the PAPER entry."""
    x=int(opened_ms)
    return ((x+MINUTE-1)//MINUTE)*MINUTE


def current_stop_from_ticker(position:dict,bid:float,ask:float,now_ms:int):
    """Current-price STOP safety check only; TARGET waits for a closed causal 1m bar.

    This intentionally avoids declaring a target from an incomplete minute where a
    later stop touch could make STOP win under the conservative ambiguity rule.
    """
    side=position['side']; stop=f(position['stop'])
    if side=='LONG' and bid and bid<=stop:return 'STOP',stop,int(now_ms)
    if side=='SHORT' and ask and ask>=stop:return 'STOP',stop,int(now_ms)
    return None


@dataclass(frozen=True)
class Candidate:
    symbol:str; signal_id:str; side:str; decision:str; signal_ms:int; breakout_close:float
    entry:float; stop:float; target:float; atr:float; ema20_4h:float; ema50_4h:float
    don_hi:float; don_lo:float; chase_atr:float; risk_usdt:float; qty:float; reason:str


def evaluate(symbol:str,h1_rows:list,h4_rows:list,bid:float,ask:float,now_ms:int,equity:float,risk_pct:float=.0025,
             slot_open:bool=False,reentry_blocked:bool=False,daily_locked:bool=False):
    h1=confirmed(h1_rows,HOUR,now_ms);h4=confirmed(h4_rows,FOUR_HOUR,now_ms)[-120:]
    if len(h1)<40 or len(h4)<50:return {'state':'DATA_ERROR','ready':False},None
    sig=h1[-1];prev=h1[-21:-1];hi=max(x['h'] for x in prev);lo=min(x['l'] for x in prev);a=atr_wilder(h1[-40:])
    e20=ema([x['c'] for x in h4],20);e50=ema([x['c'] for x in h4],50);trend='UP' if e20>e50 else 'DOWN' if e20<e50 else 'NEUTRAL'
    side='LONG' if sig['c']>hi else 'SHORT' if sig['c']<lo else 'NONE';price=(bid+ask)/2 if bid and ask else 0.0
    ctx={'ready':True,'state':'WAIT_BREAKOUT','signal_ms':sig['ct'],'trend':trend,'ema20_4h':e20,'ema50_4h':e50,'don_hi':hi,'don_lo':lo,'atr':a,'breakout':side,'price':price}
    if side=='NONE':return ctx,None
    if (side=='LONG' and trend!='UP') or (side=='SHORT' and trend!='DOWN'):
        ctx['state']='BREAKOUT_WRONG_DIRECTION';return ctx,None
    entry=ask if side=='LONG' else bid
    if not entry or not a:ctx['state']='DATA_ERROR';return ctx,None
    age=max(0,(now_ms-sig['ct'])/MINUTE);chase=abs(entry-sig['c'])/a;sd=STOP_ATR*a
    stop=entry-sd if side=='LONG' else entry+sd;target=entry+TARGET_R*sd if side=='LONG' else entry-TARGET_R*sd
    risk=equity*risk_pct;qty=risk/sd if sd else 0.0;decision=side;state='EXECUTABLE';why=[]
    if age>MAX_AGE_MIN:decision='NO_TRADE';state='TOO_EXTENDED';why.append('stale')
    if chase>MAX_CHASE_ATR:decision='NO_TRADE';state='TOO_EXTENDED';why.append('chase')
    if slot_open:decision='NO_TRADE';state='BLOCKED_POSITION_OPEN';why.append('slot')
    if reentry_blocked:decision='NO_TRADE';state='BLOCKED_REENTRY_TIME';why.append('strict_next_entry_gt_prior_exit')
    if daily_locked:decision='NO_TRADE';state='DAILY_LOCKED';why.append('daily_lock')
    sid=hashlib.sha256(f'{STRATEGY}:{symbol}:{sig["ct"]}:{side}'.encode()).hexdigest()[:24]
    p=Candidate(symbol,sid,side,decision,int(sig['ct']),sig['c'],entry,stop,target,a,e20,e50,hi,lo,chase,risk,qty,';'.join(why))
    ctx.update(state=state,age_min=age,chase_atr=chase);return ctx,p


def exit_from_1m(position:dict,bars:list[dict],now_ms:int):
    """STOP wins when stop and target are both touched inside the same closed 1m bar."""
    side=position['side'];stop=f(position['stop']);target=f(position['target'])
    for b in sorted(bars,key=lambda x:x['ot']):
        stop_hit=(b['l']<=stop if side=='LONG' else b['h']>=stop);target_hit=(b['h']>=target if side=='LONG' else b['l']<=target)
        if stop_hit:return 'STOP',stop,int(b['ct'])
        if target_hit:return 'TARGET',target,int(b['ct'])
    if now_ms>=int(position['opened_ms'])+MAX_HOLD_H*HOUR and bars:return 'TIME',f(bars[-1]['c']),int(bars[-1]['ct'])
    return None


def should_process(last_processed:int|None,current_close:int,fresh_boot:bool)->tuple[bool,int]:
    if last_processed is None and fresh_boot:return False,current_close
    if last_processed is None:return True,current_close
    return current_close>last_processed,max(last_processed,current_close)
