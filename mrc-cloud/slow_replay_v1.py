from __future__ import annotations
from typing import Any

MINUTE=60_000


def f(x:Any,d=0.0)->float:
    try:return float(x)
    except Exception:return d


def confirmed_1m(rows:list[list[Any]],cutoff_ms:int,start_open_ms:int|None=None)->list[dict]:
    """Normalize confirmed OKX 1m rows, dedupe by open timestamp, and clip to range."""
    by_open={}
    for r in rows:
        if len(r)<9 or str(r[8])!='1':continue
        ot=int(r[0]);ct=ot+MINUTE
        if ct>int(cutoff_ms):continue
        if start_open_ms is not None and ot<int(start_open_ms):continue
        by_open[ot]={'ot':ot,'ct':ct,'o':f(r[1]),'h':f(r[2]),'l':f(r[3]),'c':f(r[4])}
    return [by_open[k] for k in sorted(by_open)]


def first_full_minute_open(opened_ms:int)->int:
    x=int(opened_ms)
    return ((x+MINUTE-1)//MINUTE)*MINUTE


def replay_window(opened_ms:int,last_check_ms:int|None,now_ms:int,max_hold_ms:int)->dict:
    """Return exact replay boundaries.

    expected_open is the first bar open that must exist. cutoff_ms is capped at the
    first full-minute close that can represent the max-hold deadline, so replay never
    scans indefinitely after a position should already have been closed.
    """
    opened=int(opened_ms);now=int(now_ms);deadline=opened+int(max_hold_ms)
    monitor_start=first_full_minute_open(opened)
    expected_open=max(monitor_start,int(last_check_ms or opened))
    deadline_bar_close=((deadline+MINUTE-1)//MINUTE)*MINUTE
    cutoff=min(now,deadline_bar_close if now>=deadline else now)
    return {'monitor_start':monitor_start,'expected_open':expected_open,'deadline_ms':deadline,'cutoff_ms':cutoff}


def first_gap(bars:list[dict],expected_open_ms:int,cutoff_ms:int)->dict|None:
    """Find the first missing fully-closed 1m bar from expected_open through cutoff."""
    expected=int(expected_open_ms)
    last_open=((int(cutoff_ms)-MINUTE)//MINUTE)*MINUTE
    if last_open<expected:return None
    opens={int(b['ot']) for b in bars if int(b['ct'])<=int(cutoff_ms)}
    x=expected
    while x<=last_open:
        if x not in opens:return {'missing_open_ms':x,'expected_through_open_ms':last_open}
        x+=MINUTE
    return None


def merge_pages(pages:list[list[list[Any]]],cutoff_ms:int,start_open_ms:int)->list[dict]:
    rows=[]
    for p in pages:rows.extend(p)
    return confirmed_1m(rows,cutoff_ms,start_open_ms)
