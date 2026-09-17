import importlib.util,sys,tempfile
from pathlib import Path
engine_path=Path(__file__).with_name('slow_engine_v2.py')
spec=importlib.util.spec_from_file_location('e',engine_path);m=importlib.util.module_from_spec(spec);sys.modules['e']=m;spec.loader.exec_module(m)
store_path=Path(__file__).with_name('slow_store_v3.py')
spec2=importlib.util.spec_from_file_location('s',store_path);s=importlib.util.module_from_spec(spec2);sys.modules['s']=s;spec2.loader.exec_module(s)
def row(ot,o,h,l,c,q='1'):return [str(ot),str(o),str(h),str(l),str(c),'1','1','1',q]
now=1_800_000_000_000;H=m.HOUR;F=m.FOUR_HOUR
s1=now-45*H;h1=[row(s1+i*H,100,101,99,100) for i in range(45)]
for j in range(24,44):h1[j]=row(s1+j*H,100,105,95,100)
h1[44]=row(s1+44*H,100,107,99,106)
s4=now-60*F;h4=[row(s4+i*F,90+i*.5,91+i*.5,89+i*.5,90.2+i*.5) for i in range(60)]
h4.append(row(now-F,200,210,190,205,'0'))

# 1: causal Donchian + confirmed 4H trend
ctx,p=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert ctx['don_hi']==105 and ctx['trend']=='UP' and p and p.side=='LONG'
# 2: same-bar ambiguity is conservative
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':99,'c':106}],now+m.MINUTE)[0]=='STOP'
# 3: target-only touch works
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':101,'c':109}],now+m.MINUTE)[0]=='TARGET'
# 4: fresh boot establishes watermark only
assert m.should_process(None,100,True)==(False,100)
# 5: persisted older watermark processes exactly newer close
assert m.should_process(100,200,True)==(True,200)
# 6: deterministic signal identity
_,p2=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert p.signal_id==p2.signal_id
# 7: frozen daily lock blocks an otherwise executable breakout
ctx_lock,p_lock=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000,daily_locked=True)
assert p_lock and p_lock.decision=='NO_TRADE' and ctx_lock['state']=='DAILY_LOCKED'

with tempfile.TemporaryDirectory() as td:
    dbfile=str(Path(td)/'state.sqlite3')
    a=s.Store(dbfile,'')
    a.set('last_processed_1h_close:BTCUSDT',123456789)
    # 8: decision events are idempotent by strategy+symbol+close
    assert a.record_decision(m.STRATEGY,'BTCUSDT',123456789,'2027-01-15T08:00:00+00:00',ctx,p) is True
    assert a.record_decision(m.STRATEGY,'BTCUSDT',123456789,'2027-01-15T08:00:01+00:00',ctx,p) is False
    assert a.decision_count('BTCUSDT')==1
    # 9: trade accounting feeds prospective audit and UTC daily PnL
    assert a.record_signal(p,'2027-01-15T08:00:00+00:00') is True
    assert a.open(p,now) is True
    t=a.open_trade();assert t and t['signal_id']==p.signal_id
    a.close(t,p.stop,'STOP',now+m.MINUTE,0.0006)
    audit=a.audit_summary(0.0006,10000,now+m.MINUTE)
    assert audit['closed_trades']==1 and audit['paper_trades_total']==1 and audit['expectancy_net_R']<0
    assert a.daily_realized_pnl(now+m.MINUTE)<0
    a.close_conn()
    # 10: watermark + audit + trade history survive store restart
    b=s.Store(dbfile,'')
    assert b.get_int('last_processed_1h_close:BTCUSDT')==123456789
    assert b.decision_count('BTCUSDT')==1
    assert b.audit_summary(0.0006,10000,now+m.MINUTE)['closed_trades']==1
    b.close_conn()
print('10/10 PASS')
