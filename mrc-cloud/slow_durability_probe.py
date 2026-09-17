from __future__ import annotations
import json, os, uuid
from slow_store_v3 import Store

path=os.getenv('MRC_STAGING_DB','/tmp/mrc_slow_staging.sqlite3')
url=os.getenv('DATABASE_URL','').strip()
s=Store(path,url)
try:
    probe=s.get('ops:durability_probe_id')
    if not probe:
        probe=str(uuid.uuid4())
        s.set('ops:durability_probe_id',probe)
    boot=s.get_int('ops:durability_boot_count',0)+1
    s.set('ops:durability_boot_count',boot)
    print('SLOW_DURABILITY_PROBE='+json.dumps({'backend':s.backend,'path':path if s.backend=='sqlite' else None,'probe_id':probe,'boot_count':boot},sort_keys=True),flush=True)
finally:
    s.close_conn()
