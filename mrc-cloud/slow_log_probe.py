from __future__ import annotations

import asyncio
import json
import httpx

URL='http://127.0.0.1:8081'

async def main():
    async with httpx.AsyncClient(timeout=8.0) as client:
        while True:
            try:
                ready=(await client.get(URL+'/readyz')).json()
                ev=(await client.get(URL+'/api/evidence')).json()
                aq=(await client.get(URL+'/api/audit')).json()
                q=ev.get('evidence_quality') or {}
                p=aq.get('prospective') or {}
                latest=aq.get('latest_closed_trade_review') or {}
                out={
                    'ready':ready.get('ready'),
                    'integrity_pass':q.get('integrity_pass'),
                    'decision_events_total':q.get('decision_events_total'),
                    'distinct_decision_closes':q.get('distinct_decision_closes'),
                    'signals_total':q.get('signals_total'),
                    'paper_trades_total':q.get('paper_trades_total'),
                    'closed_paper_trades':q.get('closed_paper_trades'),
                    'open_paper_trades':q.get('open_paper_trades'),
                    'per_symbol':q.get('per_symbol'),
                    'trade_outcome_counts':q.get('trade_outcome_counts'),
                    'prospective':p,
                    'latest_closed_trade_available':latest.get('available'),
                    'latest_closed_trade_links':latest.get('links'),
                }
                print('SLOW_EVIDENCE_SNAPSHOT='+json.dumps(out,separators=(',',':'),default=str),flush=True)
            except Exception as exc:
                print(f'SLOW_EVIDENCE_PROBE_ERROR={type(exc).__name__}:{exc}',flush=True)
            await asyncio.sleep(300)

if __name__=='__main__':
    asyncio.run(main())
