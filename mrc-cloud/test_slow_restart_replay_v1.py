import tempfile
from pathlib import Path
import slow_engine_v2 as eng
import slow_replay_v1 as replay
from slow_store_v3 import Store

opened=1_800_000_015_000
p=eng.Candidate('BTCUSDT','restart-position','LONG','LONG',opened,100.0,100.0,90.0,110.0,6.6666666667,101,100,99,95,0.0,25.0,2.5,'')

with tempfile.TemporaryDirectory() as td:
    path=str(Path(td)/'restart.sqlite3')
    a=Store(path,'')
    assert a.open(p,opened) is True
    t=a.open_trade();assert t and t['outcome']=='OPEN'
    first=replay.first_full_minute_open(opened)
    checked=first+5*eng.MINUTE
    a.mark_checked(t['trade_id'],checked)
    a.close_conn()

    # 1 an OPEN position survives process restart with its last causal checkpoint
    b=Store(path,'');t=b.open_trade()
    assert t and int(t['opened_ms'])==opened and int(t['last_check_ms'])==checked

    # 2 replay resumes exactly at persisted last_check, not at current time or entry
    now=checked+4*eng.MINUTE
    w=replay.replay_window(t['opened_ms'],t['last_check_ms'],now,eng.MAX_HOLD_H*eng.HOUR)
    assert w['expected_open']==checked

    # 3 contiguous replay after restart can deterministically close the position
    bars=[]
    for i in range(3):
        ot=checked+i*eng.MINUTE
        bars.append({'ot':ot,'ct':ot+eng.MINUTE,'o':100,'h':105,'l':95,'c':100})
    bars[-1]['h']=111
    assert replay.first_gap(bars,checked,checked+3*eng.MINUTE) is None
    ex=eng.exit_from_1m(t,bars,checked+3*eng.MINUTE)
    assert ex and ex[0]=='TARGET' and ex[1]==110.0
    b.close(t,ex[1],ex[0],ex[2],0.0006)
    assert b.open_trade() is None and b.trade_count()==1
    b.close_conn()

print('3/3 RESTART REPLAY PASS')
