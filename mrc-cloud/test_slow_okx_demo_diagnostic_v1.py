import os
for k in ('OKX_DEMO_API_KEY','OKX_DEMO_SECRET_KEY','OKX_DEMO_PASSPHRASE'):
    os.environ.pop(k,None)
from slow_okx_demo_diagnostic_v1 import DemoDiagnostic
try:
    DemoDiagnostic()
    raise AssertionError('diagnostic should fail closed without demo credentials')
except RuntimeError as e:
    assert str(e)=='DEMO_CREDENTIALS_MISSING'
print('1/1 DEMO DIAGNOSTIC FAIL-CLOSED PASS')
