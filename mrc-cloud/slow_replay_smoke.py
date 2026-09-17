import asyncio,time
import slow_engine_v2 as eng
import slow_replay_v1 as replay
from slow_app_v2 import OKX

async def main():
    now=int(time.time()*1000)
    start=((now-72*eng.HOUR)//eng.MINUTE)*eng.MINUTE
    c=OKX()
    try:
        bars,meta=await c.minute_rows_range('BTCUSDT',start,now)
        gap=replay.first_gap(bars,start,now)
        expected_last=((now-eng.MINUTE)//eng.MINUTE)*eng.MINUTE
        expected=((expected_last-start)//eng.MINUTE)+1 if expected_last>=start else 0
        assert meta['source']=='history',meta
        assert meta['pages']>=40,meta
        assert gap is None,gap
        assert len(bars)==expected,(len(bars),expected,meta)
        print('LIVE_72H_REPLAY_PASS',{'bars':len(bars),'pages':meta['pages'],'start':start,'last':bars[-1]['ot'] if bars else None})
    finally:
        await c.close()

if __name__=='__main__':asyncio.run(main())
