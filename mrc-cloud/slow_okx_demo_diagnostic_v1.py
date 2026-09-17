from __future__ import annotations
import asyncio,json,os
from urllib.parse import urlencode
import httpx
from slow_execution_adapter_v1 import demo_headers

BASE='https://openapi.okx.com'

class DemoDiagnostic:
    def __init__(self):
        self.key=os.getenv('OKX_DEMO_API_KEY','').strip()
        self.secret=os.getenv('OKX_DEMO_SECRET_KEY','').strip()
        self.passphrase=os.getenv('OKX_DEMO_PASSPHRASE','').strip()
        if not self.key or not self.secret or not self.passphrase:
            raise RuntimeError('DEMO_CREDENTIALS_MISSING')
        self.h=httpx.AsyncClient(base_url=BASE,timeout=12,headers={'User-Agent':'MRC-Slow-Demo-Diagnostic/1.0'})

    async def public_time(self):
        r=await self.h.get('/api/v5/public/time');r.raise_for_status();j=r.json()
        if j.get('code')!='0' or not j.get('data'):raise RuntimeError('OKX_TIME_FAILED')
        return int(j['data'][0]['ts'])

    async def private_get(self,path:str,params:dict|None=None):
        params=params or {}
        qs=urlencode(params)
        request_path=path+('?' + qs if qs else '')
        # Use local UTC ISO timestamp; public_time is checked separately so clock drift
        # is surfaced before any future order path is ever enabled.
        from datetime import datetime,timezone
        ts=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
        headers=demo_headers(self.key,self.secret,self.passphrase,ts,'GET',request_path,'')
        r=await self.h.get(path,params=params,headers=headers);r.raise_for_status();j=r.json()
        if j.get('code')!='0':raise RuntimeError(f"OKX_PRIVATE_ERROR {j.get('code')} {j.get('msg')}")
        return j.get('data') or []

    async def run(self):
        server_ms=await self.public_time()
        import time
        drift_ms=abs(int(time.time()*1000)-server_ms)
        cfg=await self.private_get('/api/v5/account/config')
        if not cfg:raise RuntimeError('ACCOUNT_CONFIG_EMPTY')
        c=cfg[0]
        instruments=[]
        for inst_id in ('BTC-USDT-SWAP','ETH-USDT-SWAP'):
            rows=await self.private_get('/api/v5/account/instruments',{'instType':'SWAP','instId':inst_id})
            if len(rows)!=1:raise RuntimeError(f'INSTRUMENT_NOT_UNIQUE {inst_id} count={len(rows)}')
            x=rows[0]
            instruments.append({k:x.get(k) for k in ('instId','state','ctType','ctVal','ctValCcy','lotSz','minSz','settleCcy')})
        out={
            'demo_header_required':True,
            'clock_drift_ms':drift_ms,
            'clock_ok':drift_ms<10_000,
            'account':{'acctLv':c.get('acctLv'),'posMode':c.get('posMode')},
            'instruments':instruments,
            'order_submission_performed':False,
        }
        print('OKX_DEMO_DIAGNOSTIC='+json.dumps(out,separators=(',',':')))
        return out

    async def close(self):await self.h.aclose()

async def main():
    d=DemoDiagnostic()
    try:
        out=await d.run()
        assert out['clock_ok'],'CLOCK_DRIFT_TOO_LARGE'
        assert out['account']['posMode'] in ('net_mode','long_short_mode'),'UNSUPPORTED_POSITION_MODE'
        for x in out['instruments']:
            assert x['state']=='live','INSTRUMENT_NOT_LIVE'
            assert x['ctType']=='linear','NON_LINEAR_SWAP_BLOCKED'
            assert x['ctVal'] and x['lotSz'] and x['minSz'],'INSTRUMENT_METADATA_INCOMPLETE'
    finally:await d.close()

if __name__=='__main__':asyncio.run(main())
