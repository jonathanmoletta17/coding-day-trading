from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

MINUTE=60_000
HOUR=60*MINUTE
FOUR_HOUR=4*HOUR
OKX_BASE="https://www.okx.com"
PAPER_BASE=os.getenv("MRC_PAPER_INTERNAL_BASE","http://mrc-cockpit-public.railway.internal:8081").rstrip("/")


def fetch_json(url:str,params:dict|None=None,timeout:int=20)->dict:
    if params:url=url+"?"+urlencode(params)
    req=Request(url,headers={"User-Agent":"MRC-ReadOnly-Postmortem/1.0"})
    with urlopen(req,timeout=timeout) as response:
        return json.loads(response.read().decode())


def okx(path:str,**params)->list:
    body=fetch_json(OKX_BASE+path,params)
    if body.get("code")!="0":raise RuntimeError(f"OKX {body.get('code')} {body.get('msg')}")
    return body.get("data") or []


def normalize(rows:list[list],duration_ms:int,start_open_ms:int,cutoff_ms:int)->list[dict]:
    by_open={}
    for row in rows:
        if len(row)<9 or str(row[8])!="1":continue
        ot=int(row[0]);ct=ot+duration_ms
        if ot<int(start_open_ms) or ct>int(cutoff_ms):continue
        by_open[ot]={"ot":ot,"ct":ct,"o":float(row[1]),"h":float(row[2]),"l":float(row[3]),"c":float(row[4])}
    return [by_open[k] for k in sorted(by_open)]


def fetch_history(inst_id:str,bar:str,duration_ms:int,start_open_ms:int,cutoff_ms:int,max_pages:int=100)->tuple[list[dict],dict]:
    cursor=int(cutoff_ms)+1;pages=[];requests=0
    while cursor>int(start_open_ms):
        rows=okx("/api/v5/market/history-candles",instId=inst_id,bar=bar,after=str(cursor),limit="100")
        requests+=1
        if not rows:break
        pages.extend(rows)
        opens=[int(r[0]) for r in rows if r]
        if not opens:break
        oldest=min(opens)
        if oldest<=int(start_open_ms):break
        if oldest>=cursor:raise RuntimeError(f"OKX_CURSOR_STALLED bar={bar} cursor={cursor} oldest={oldest}")
        cursor=oldest
        if requests>=max_pages:raise RuntimeError(f"OKX_PAGE_GUARD bar={bar} pages={requests}")
        time.sleep(.11)
    bars=normalize(pages,duration_ms,start_open_ms,cutoff_ms)
    return bars,{"bar":bar,"pages":requests,"bars":len(bars),"start_open_ms":start_open_ms,"cutoff_ms":cutoff_ms}


def first_full_minute_open(opened_ms:int)->int:
    return ((int(opened_ms)+MINUTE-1)//MINUTE)*MINUTE


def missing_opens(bars:list[dict],start_open_ms:int,cutoff_ms:int,duration_ms:int)->list[int]:
    last_open=((int(cutoff_ms)-duration_ms)//duration_ms)*duration_ms
    actual={int(b["ot"]) for b in bars}
    return [x for x in range(int(start_open_ms),last_open+1,duration_ms) if x not in actual]


def ema(values:list[float],period:int)->float|None:
    if not values:return None
    alpha=2/(period+1);value=float(values[0])
    for item in values[1:]:value=alpha*float(item)+(1-alpha)*value
    return value


def atr_wilder(bars:list[dict],period:int=14)->float|None:
    if len(bars)<2:return None
    tr=[max(bars[i]["h"]-bars[i]["l"],abs(bars[i]["h"]-bars[i-1]["c"]),abs(bars[i]["l"]-bars[i-1]["c"])) for i in range(1,len(bars))]
    if not tr:return None
    value=sum(tr[:period])/min(period,len(tr))
    for item in tr[period:]:value=((period-1)*value+item)/period
    return value


def iso(ms:int)->str:
    return datetime.fromtimestamp(int(ms)/1000,tz=timezone.utc).isoformat()


def excursion_report(trade:dict,bars:list[dict])->dict:
    entry=float(trade["entry"]);stop=float(trade["stop"]);target=float(trade["target"]);risk_distance=abs(entry-stop)
    side=1.0 if trade["side"]=="LONG" else -1.0
    if not bars:return {"bars":0,"available":False}
    if side>0:
        best=max(bars,key=lambda b:b["h"]);worst=min(bars,key=lambda b:b["l"]);best_px=best["h"];worst_px=worst["l"]
        mfe=(best_px-entry)/risk_distance;mae=(entry-worst_px)/risk_distance;target_progress=(best_px-entry)/(target-entry)
    else:
        best=min(bars,key=lambda b:b["l"]);worst=max(bars,key=lambda b:b["h"]);best_px=best["l"];worst_px=worst["h"]
        mfe=(entry-best_px)/risk_distance;mae=(worst_px-entry)/risk_distance;target_progress=(entry-best_px)/(entry-target)
    return {"available":True,"bars":len(bars),"best_price":best_px,"best_at":iso(best["ot"]),"worst_price_before_exit":worst_px,
        "worst_at":iso(worst["ot"]),"mfe_R":mfe,"mae_R_before_exit":mae,"target_progress_fraction":target_progress,
        "remaining_to_target":abs(target-best_px)}


def exit_mechanism(trade:dict)->dict:
    closed_ms=int(trade["closed_ms"]);aligned=(closed_ms%MINUTE)==0
    mechanism="CLOSED_1M_REPLAY" if aligned else "CURRENT_TICKER_STOP"
    return {"mechanism":mechanism,"closed_ms_aligned_to_minute":aligned,
        "evidence":"closed 1m replay returns bar-close timestamps; current ticker stop returns loop now_ms"}


def hourly_indicator_path(h1:list[dict],h4:list[dict],start_ms:int,end_ms:int)->list[dict]:
    rows=[];close=((int(start_ms)+HOUR-1)//HOUR)*HOUR
    while close<=int(end_ms):
        one=[b for b in h1 if b["ct"]<=close]
        four=[b for b in h4 if b["ct"]<=close][-120:]
        if len(one)>=40 and len(four)>=50:
            a=atr_wilder(one[-40:]);e20=ema([b["c"] for b in four],20);e50=ema([b["c"] for b in four],50)
            rows.append({"close_ms":close,"close_utc":iso(close),"atr14":a,"ema20_4h":e20,"ema50_4h":e50,
                "trend":"UP" if e20>e50 else "DOWN" if e20<e50 else "NEUTRAL"})
        close+=HOUR
    return rows


def counterfactual(signal_review:dict,now_ms:int)->dict:
    payload=signal_review.get("signal_payload") or {};decision=signal_review.get("decision") or {}
    if signal_review.get("trade") is not None or not payload:return {"available":False,"reason":"NOT_A_BLOCKED_SIGNAL"}
    decided_at=decision.get("decided_at")
    opened_ms=int(datetime.fromisoformat(decided_at).timestamp()*1000) if decided_at else int(payload["signal_ms"])
    cutoff=min(now_ms,opened_ms+72*HOUR);inst="BTC-USDT-SWAP" if payload.get("symbol")=="BTCUSDT" else "ETH-USDT-SWAP"
    start=first_full_minute_open(opened_ms);bars,source=fetch_history(inst,"1m",MINUTE,start,cutoff)
    entry=float(payload["entry"]);stop=float(payload["stop"]);target=float(payload["target"]);side=payload.get("side")
    outcome=None;exit_px=None;exit_ms=None
    for bar in bars:
        stop_hit=bar["l"]<=stop if side=="LONG" else bar["h"]>=stop
        target_hit=bar["h"]>=target if side=="LONG" else bar["l"]<=target
        if stop_hit:outcome="STOP";exit_px=stop;exit_ms=bar["ct"];break
        if target_hit:outcome="TARGET";exit_px=target;exit_ms=bar["ct"];break
    if outcome is None and cutoff>=opened_ms+72*HOUR:
        outcome="TIME";exit_px=bars[-1]["c"] if bars else None;exit_ms=cutoff
    return {"available":True,"official_result":False,"label":"COUNTERFACTUAL_ONLY","symbol":payload.get("symbol"),"side":side,
        "entry":entry,"stop":stop,"target":target,"opened_ms_assumed":opened_ms,"observed_through_ms":cutoff,"outcome":outcome or "STILL_OPEN_AT_CUTOFF",
        "exit":exit_px,"exit_ms":exit_ms,"excursion":excursion_report({"entry":entry,"stop":stop,"target":target,"side":side},bars),
        "coverage":{"missing_minutes":len(missing_opens(bars,start,cutoff,MINUTE)),"source":source}}


def build_report(now_ms:int|None=None)->dict:
    now_ms=int(now_ms or time.time()*1000)
    review_body=fetch_json(PAPER_BASE+"/api/latest-closed-trade-review")
    review=review_body.get("review") or {}
    if not review.get("available"):raise RuntimeError("NO_CLOSED_TRADE")
    trade=review["trade"];signal=review.get("signal_payload") or {}
    opened_ms=int(trade["opened_ms"]);closed_ms=int(trade["closed_ms"]);start=first_full_minute_open(opened_ms)
    minute_bars,minute_source=fetch_history("ETH-USDT-SWAP","1m",MINUTE,start,closed_ms)
    history_start=int(signal.get("signal_ms",opened_ms))-600*HOUR
    h1,h1_source=fetch_history("ETH-USDT-SWAP","1H",HOUR,history_start,closed_ms)
    h4,h4_source=fetch_history("ETH-USDT-SWAP","4H",FOUR_HOUR,history_start,closed_ms)
    indicators=hourly_indicator_path(h1,h4,int(signal.get("signal_ms",opened_ms)),closed_ms)
    try:signal_reviews_body=fetch_json(PAPER_BASE+"/api/signal-reviews");all_reviews=(signal_reviews_body.get("signal_reviews") or {}).get("items") or []
    except Exception:all_reviews=[]
    blocked=[x for x in all_reviews if x.get("trade") is None and (x.get("decision") or {}).get("state")=="BLOCKED_POSITION_OPEN"]
    return {"report_version":"FIRST_PROSPECTIVE_TRADE_POSTMORTEM_V1","generated_at":iso(now_ms),"read_only":True,
        "paper_mutation_performed":False,"private_exchange_api_used":False,"strategy_retuning_authorized":False,"real_money_promotion_authorized":False,
        "trade":trade,"signal":signal,"links":review.get("links"),"duration_ms":closed_ms-opened_ms,
        "duration_h":(closed_ms-opened_ms)/HOUR,"exit_mechanism":exit_mechanism(trade),
        "minute_path":{"source":minute_source,"first_bar":minute_bars[0] if minute_bars else None,"last_fully_closed_bar":minute_bars[-1] if minute_bars else None,
            "missing_minutes":missing_opens(minute_bars,start,closed_ms,MINUTE),"excursion":excursion_report(trade,minute_bars)},
        "indicator_path":{"h1_source":h1_source,"h4_source":h4_source,"points":indicators,
            "trend_sequence":[x["trend"] for x in indicators],"atr_min":min((x["atr14"] for x in indicators),default=None),
            "atr_max":max((x["atr14"] for x in indicators),default=None)},
        "cost_scenarios":review.get("cost_scenarios"),"blocked_signal_count":len(blocked),
        "blocked_counterfactuals":[counterfactual(x,now_ms) for x in blocked]}


def main()->None:
    report=build_report();print("FIRST_TRADE_POSTMORTEM="+json.dumps(report,separators=(",",":"),ensure_ascii=False,default=str),flush=True)


if __name__=="__main__":main()
