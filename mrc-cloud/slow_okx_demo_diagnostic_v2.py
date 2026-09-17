from __future__ import annotations
import asyncio, json, os, time
from datetime import datetime, timezone
from urllib.parse import urlencode
import httpx
from slow_execution_adapter_v1 import demo_headers

BASE='https://openapi.okx.com'
TARGETS=('BTC-USDT-SWAP','ETH-USDT-SWAP')

class DemoDiagnosticV2:
    def __init__(self):
        self.key=os.getenv('OKX_DEMO_API_KEY','').strip()
        self.secret=os.getenv('OKX_DEMO_SECRET_KEY','').strip()
        self.passphrase=os.getenv('OKX_DEMO_PASSPHRASE','').strip()
        if not self.key or not self.secret or not self.passphrase:
            raise RuntimeError('DEMO_CREDENTIALS_MISSING')
        self.h=httpx.AsyncClient(base_url=BASE,timeout=15,headers={'User-Agent':'MRC-Slow-Demo-Diagnostic/2.0'})

    async def public_get(self,path:str,params:dict|None=None):
        r=await self.h.get(path,params=params or {})
        r.raise_for_status()
        j=r.json()
        if j.get('code')!='0':
            raise RuntimeError(f"OKX_PUBLIC_ERROR {j.get('code')} {j.get('msg')}")
        return j.get('data') or []

    async def private_get(self,path:str,params:dict|None=None):
        params=params or {}
        qs=urlencode(params)
        request_path=path+('?' + qs if qs else '')
        ts=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
        headers=demo_headers(self.key,self.secret,self.passphrase,ts,'GET',request_path,'')
        r=await self.h.get(path,params=params,headers=headers)
        r.raise_for_status()
        j=r.json()
        if j.get('code')!='0':
            raise RuntimeError(f"OKX_PRIVATE_ERROR {j.get('code')} {j.get('msg')}")
        return j.get('data') or []

    async def run(self):
        trows=await self.public_get('/api/v5/public/time')
        if not trows: raise RuntimeError('OKX_TIME_EMPTY')
        server_ms=int(trows[0]['ts'])
        drift_ms=abs(int(time.time()*1000)-server_ms)

        cfg=await self.private_get('/api/v5/account/config')
        if not cfg: raise RuntimeError('ACCOUNT_CONFIG_EMPTY')
        c=cfg[0]

        private_swaps=await self.private_get('/api/v5/account/instruments',{'instType':'SWAP'})
        private_ids={x.get('instId') for x in private_swaps}

        targets=[]
        for inst_id in TARGETS:
            pub=await self.public_get('/api/v5/public/instruments',{'instType':'SWAP','instId':inst_id})
            row=pub[0] if len(pub)==1 else None
            targets.append({
                'instId':inst_id,
                'private_available':inst_id in private_ids,
                'public_count':len(pub),
                'public':None if row is None else {k:row.get(k) for k in (
                    'instId','state','ctType','ctVal','ctValCcy','lotSz','minSz','settleCcy','baseCcy','quoteCcy','lever'
                )},
            })

        out={
            'credentials_present':True,
            'clock_drift_ms':drift_ms,
            'clock_ok':drift_ms<10_000,
            'account':{
                'acctLv':c.get('acctLv'),
                'posMode':c.get('posMode'),
            },
            'private_swap_count':len(private_swaps),
            'targets':targets,
            'order_submission_performed':False,
        }
        print('OKX_DEMO_DIAGNOSTIC_V2='+json.dumps(out,separators=(',',':')),flush=True)
        return out

    async def close(self):
        await self.h.aclose()

async def main():
    d=DemoDiagnosticV2()
    try:
        await d.run()
    finally:
        await d.close()

if __name__=='__main__':
    asyncio.run(main())
