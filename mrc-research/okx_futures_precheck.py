from __future__ import annotations
import base64, hashlib, hmac, json, os
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode
import httpx

BASE='https://openapi.okx.com'

def sig(ts,method,path,body,secret):
    raw=f'{ts}{method.upper()}{path}{body}'.encode()
    return base64.b64encode(hmac.new(secret.encode(),raw,hashlib.sha256).digest()).decode()

def hdr(key,secret,passphrase,ts,path):
    return {
        'Content-Type':'application/json',
        'OK-ACCESS-KEY':key,
        'OK-ACCESS-SIGN':sig(ts,'GET',path,'',secret),
        'OK-ACCESS-TIMESTAMP':ts,
        'OK-ACCESS-PASSPHRASE':passphrase,
        'x-simulated-trading':'1',
    }

key=os.getenv('OKX_DEMO_API_KEY','').strip(); secret=os.getenv('OKX_DEMO_SECRET_KEY','').strip(); pw=os.getenv('OKX_DEMO_PASSPHRASE','').strip()
if not (key and secret and pw): raise RuntimeError('DEMO_CREDENTIALS_MISSING')
qs=urlencode({'acctLv':'2'})
path='/api/v5/account/set-account-switch-precheck?'+qs
ts=datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
r=httpx.get(BASE+'/api/v5/account/set-account-switch-precheck',params={'acctLv':'2'},headers=hdr(key,secret,pw,ts,path),timeout=20)
r.raise_for_status(); j=r.json()
out={'http_status':r.status_code,'code':j.get('code'),'msg':j.get('msg'),'data':j.get('data') or [],'order_submission_performed':False,'account_mode_change_performed':False}
print('OKX_FUTURES_PRECHECK='+json.dumps(out,separators=(',',':'),ensure_ascii=False),flush=True)

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        b=json.dumps({'ok':True,'precheck_code':out['code']}).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self,*a): pass
HTTPServer(('0.0.0.0',int(os.getenv('PORT','8080'))),H).serve_forever()
