import importlib.util,sys,tempfile
from dataclasses import replace
from pathlib import Path
engine_path=Path(__file__).with_name('slow_engine_v2.py')
spec=importlib.util.spec_from_file_location('e',engine_path);m=importlib.util.module_from_spec(spec);sys.modules['e']=m;spec.loader.exec_module(m)
store_path=Path(__file__).with_name('slow_store_v3.py')
spec2=importlib.util.spec_from_file_location('s',store_path);s=importlib.util.module_from_spec(spec2);sys.modules['s']=s;spec2.loader.exec_module(s)
replay_path=Path(__file__).with_name('slow_replay_v1.py')
spec3=importlib.util.spec_from_file_location('rp',replay_path);rp=importlib.util.module_from_spec(spec3);sys.modules['rp']=rp;spec3.loader.exec_module(rp)
def row(ot,o,h,l,c,q='1'):return [str(ot),str(o),str(h),str(l),str(c),'1','1','1',q]
now=1_800_000_000_000;H=m.HOUR;F=m.FOUR_HOUR
s1=now-45*H;h1=[row(s1+i*H,100,101,99,100) for i in range(45)]
for j in range(24,44):h1[j]=row(s1+j*H,100,105,95,100)
h1[44]=row(s1+44*H,100,107,99,106)
s4=now-60*F;h4=[row(s4+i*F,90+i*.5,91+i*.5,89+i*.5,90.2+i*.5) for i in range(60)]
h4.append(row(now-F,200,210,190,205,'0'))

# 1 causal Donchian + confirmed 4H trend
ctx,p=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert ctx['don_hi']==105 and ctx['trend']=='UP' and p and p.side=='LONG'
# 2 same-bar ambiguity is conservative
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':99,'c':106}],now+m.MINUTE)[0]=='STOP'
# 3 target-only touch
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':101,'c':109}],now+m.MINUTE)[0]=='TARGET'
# 4 first-ever observation for a symbol is watermark-only
assert m.should_process(None,100,True)==(False,100)
# 5 persisted older watermark processes newer close
assert m.should_process(100,200,True)==(True,200)
# 6 deterministic signal identity
_,p2=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert p.signal_id==p2.signal_id
# 7 daily lock blocks executable breakout
ctx_lock,p_lock=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000,daily_locked=True)
assert p_lock and p_lock.decision=='NO_TRADE' and ctx_lock['state']=='DAILY_LOCKED'
# 8 strict research reentry rule is explicit
ctx_re,p_re=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000,reentry_blocked=True)
assert p_re and p_re.decision=='NO_TRADE' and ctx_re['state']=='BLOCKED_REENTRY_TIME'
# 9 first monitored 1m bar cannot contain pre-entry seconds
assert m.first_full_minute_open(now)==now
assert m.first_full_minute_open(now+15_000)==now+m.MINUTE
# 10 incomplete-minute ticker can trigger STOP but never TARGET
pos={'side':'LONG','stop':100,'target':110,'opened_ms':now}
assert m.current_stop_from_ticker(pos,99.9,100.0,now+20_000)[0]=='STOP'
assert m.current_stop_from_ticker(pos,111.0,111.1,now+20_000) is None
# 11 EMA ignores confirmed 4H history older than max-120 research window
start4=now-130*F;h4_long=[]
for i in range(130):
    c=1_000_000_000.0 if i<10 else 100.0+(i-10)*0.5
    h4_long.append(row(start4+i*F,c,c+1,c-1,c))
ctx_long,_=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4_long)),106,106.1,now,10000)
ctx_tail,_=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4_long[-120:])),106,106.1,now,10000)
assert abs(ctx_long['ema20_4h']-ctx_tail['ema20_4h'])<1e-12 and abs(ctx_long['ema50_4h']-ctx_tail['ema50_4h'])<1e-12

with tempfile.TemporaryDirectory() as td:
    dbfile=str(Path(td)/'state.sqlite3');a=s.Store(dbfile,'');a.set('last_processed_1h_close:BTCUSDT',123456789)
    # 12 decision events idempotent by strategy+symbol+close
    assert a.record_decision(m.STRATEGY,'BTCUSDT',123456789,'2027-01-15T08:00:00+00:00',ctx,p) is True
    assert a.record_decision(m.STRATEGY,'BTCUSDT',123456789,'2027-01-15T08:00:01+00:00',ctx,p) is False
    assert a.decision_count('BTCUSDT')==1
    # 13 trade accounting feeds prospective audit + UTC daily PnL
    assert a.record_signal(p,'2027-01-15T08:00:00+00:00') is True and a.open(p,now) is True
    t=a.open_trade();assert t and t['signal_id']==p.signal_id
    a.close(t,p.stop,'STOP',now+m.MINUTE,0.0006)
    audit=a.audit_summary(0.0006,10000,now+m.MINUTE)
    assert audit['closed_trades']==1 and audit['paper_trades_total']==1 and audit['expectancy_net_R']<0 and a.daily_realized_pnl(now+m.MINUTE)<0
    a.close_conn()
    # 14 watermark + audit + trade history survive restart
    b=s.Store(dbfile,'')
    assert b.get_int('last_processed_1h_close:BTCUSDT')==123456789 and b.decision_count('BTCUSDT')==1
    assert b.audit_summary(0.0006,10000,now+m.MINUTE)['closed_trades']==1
    b.close_conn()

with tempfile.TemporaryDirectory() as td:
    dbfile=str(Path(td)/'slot.sqlite3');a=s.Store(dbfile,'')
    # 15 database physically enforces one global OPEN position
    assert a.open(p,now) is True
    other=replace(p,signal_id='other-signal-id',symbol='ETHUSDT')
    assert a.open(other,now+1) is False and a.trade_count()==1
    t=a.open_trade();a.close(t,p.stop,'STOP',now+m.MINUTE,0.0006)
    # 16 strict next entry > prior exit: equality rejected, later timestamp allowed
    equal=replace(p,signal_id='equal-exit-signal',signal_ms=now+m.MINUTE)
    later=replace(p,signal_id='later-signal',signal_ms=now+2*m.MINUTE)
    assert a.open(equal,now+2*m.MINUTE) is False
    assert a.open(later,now+2*m.MINUTE) is True
    a.close_conn()

# 17 sizing is pure stop-risk parity with research; no implicit 1x notional cap
_,p_hi=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000,risk_pct=.5)
assert p_hi and abs(p_hi.qty-(p_hi.risk_usdt/(m.STOP_ATR*p_hi.atr)))<1e-12
assert p_hi.qty*p_hi.entry>10000
# 18 delayed first successful feed cycle with no persisted watermark is still bootstrap-only
assert m.should_process(None,200,False)==(False,200)
# 19 page merge is chronological, deduplicated and ignores unconfirmed rows
base=1_700_000_000_000
pg1=[row(base+2*m.MINUTE,1,2,.5,1.5),row(base+m.MINUTE,1,2,.5,1.4)]
pg2=[row(base+m.MINUTE,1,2,.5,1.4),row(base,1,2,.5,1.3),row(base-m.MINUTE,1,2,.5,1.2,'0')]
merged=rp.merge_pages([pg1,pg2],base+3*m.MINUTE,base)
assert [x['ot'] for x in merged]==[base,base+m.MINUTE,base+2*m.MINUTE]
# 20 internal coverage gaps are detected, not just a missing first bar
gappy=[{'ot':base,'ct':base+m.MINUTE},{'ot':base+2*m.MINUTE,'ct':base+3*m.MINUTE}]
gap=rp.first_gap(gappy,base,base+3*m.MINUTE)
assert gap and gap['missing_open_ms']==base+m.MINUTE
# 21 full 72h minute sequence passes continuity check
bars72=[{'ot':base+i*m.MINUTE,'ct':base+(i+1)*m.MINUTE} for i in range(72*60)]
assert rp.first_gap(bars72,base,base+72*m.HOUR) is None
# 22 replay window caps at first minute close representing the 72h deadline
opened=base+15_000;deadline=opened+72*m.HOUR
w=rp.replay_window(opened,opened,deadline+8*m.HOUR,72*m.HOUR)
assert w['deadline_ms']==deadline and w['cutoff_ms']==((deadline+m.MINUTE-1)//m.MINUTE)*m.MINUTE
# 23 target in a deadline-straddling minute cannot beat TIME
cross_open=(deadline//m.MINUTE)*m.MINUTE
cross={'ot':cross_open,'ct':cross_open+m.MINUTE,'h':120,'l':95,'c':105}
time_pos={'side':'LONG','stop':90,'target':110,'opened_ms':opened}
assert m.exit_from_1m(time_pos,[cross],cross['ct'])[0]=='TIME'
# 24 STOP remains conservative winner in a deadline-straddling minute
cross_bad={'ot':cross_open,'ct':cross_open+m.MINUTE,'h':120,'l':80,'c':100}
assert m.exit_from_1m(time_pos,[cross_bad],cross_bad['ct'])[0]=='STOP'
print('24/24 PASS')
