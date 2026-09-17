import importlib.util,sys
from pathlib import Path
engine_path=Path(__file__).with_name('slow_engine_v2.py')
spec=importlib.util.spec_from_file_location('e',engine_path);m=importlib.util.module_from_spec(spec);sys.modules['e']=m;spec.loader.exec_module(m)
def row(ot,o,h,l,c,q='1'):return [str(ot),str(o),str(h),str(l),str(c),'1','1','1',q]
now=1_800_000_000_000; H=m.HOUR; F=m.FOUR_HOUR
s1=now-45*H; h1=[row(s1+i*H,100,101,99,100) for i in range(45)]
for j in range(24,44):h1[j]=row(s1+j*H,100,105,95,100)
h1[44]=row(s1+44*H,100,107,99,106)
s4=now-60*F; h4=[row(s4+i*F,90+i*.5,91+i*.5,89+i*.5,90.2+i*.5) for i in range(60)]
h4.append(row(now-F,200,210,190,205,'0'))
ctx,p=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert ctx['don_hi']==105 and ctx['trend']=='UP' and p and p.side=='LONG'
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':99,'c':106}],now+m.MINUTE)[0]=='STOP'
assert m.exit_from_1m({'side':'LONG','stop':100,'target':110,'opened_ms':now},[{'ot':now,'ct':now+m.MINUTE,'h':111,'l':101,'c':109}],now+m.MINUTE)[0]=='TARGET'
assert m.should_process(None,100,True)==(False,100)
assert m.should_process(100,200,True)==(True,200)
_,p2=m.evaluate('BTCUSDT',list(reversed(h1)),list(reversed(h4)),106,106.1,now,10000)
assert p.signal_id==p2.signal_id
print('6/6 PASS')
