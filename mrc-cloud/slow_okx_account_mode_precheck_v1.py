from __future__ import annotations
import asyncio, json, os
from urllib.parse import urlencode
from datetime import datetime, timezone
import httpx
from slow_execution_adapter_v1 import demo_headers

BASE='https://openapi.okx.com'

async def main():
    key=os.getenv('OKX_DEMO_API_KEY','').strip()
    secret=os.getenv('OKX_DEMO_SECRET_KEY','').strip()
    passphrase=os.getenv('OKX_DEMO_PASSPHRASE','').strip()
    if not key or not secret or not passphrase:
        raise RuntimeError('DEMO_CREDENTIALS_MISSING')
    path='/api/v5/account/set-account-switch-precheck'
    params={'acctLv':'2'}
    qs=urlencode(params)
    req_path=path+'?'+qs
    ts=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    headers=demo_headers(key,secret,passphrase,ts,'GET',req_path,'')
    async with httpx.AsyncClient(base_url=BASE,timeout=15,headers={'User-Agent':'MRC-Account-Mode-Precheck/1.0'}) as h:
        r=await h.get(path,params=params,headers=headers)
        j=r.json()
    out={'http_status':r.status_code,'code':j.get('code'),'msg':j.get('msg'),'data':j.get('data'),'order_submission_performed':False,'account_mode_change_performed':False}
    print('OKX_ACCOUNT_MODE_PRECHECK='+json.dumps(out,separators=(',',':'),ensure_ascii=False))

if __name__=='__main__':
    asyncio.run(main())
