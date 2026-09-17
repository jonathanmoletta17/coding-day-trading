from slow_execution_adapter_v1 import *

spec=InstrumentSpec('BTC-USDT-SWAP','BTC','linear','0.01','BTC','1','1','live')
intent=OrderIntent('SLOW_TREND_BREAKOUT_V1','abc123','BTCUSDT','LONG',0.057)

# 1 deterministic exchange-safe clOrdId
x=deterministic_clordid(intent.strategy,intent.signal_id)
assert x==deterministic_clordid(intent.strategy,intent.signal_id) and len(x)<=32 and x.isalnum()
# 2 real money is hard-blocked regardless of flags
assert execution_gate(mode='LIVE',explicit_enable=True,kill_switch=False,secrets_present=True,account_mode_verified=True,instrument_verified=True).reason=='REAL_MONEY_HARD_BLOCK'
# 3 demo requires explicit enable
assert execution_gate(mode='DEMO',explicit_enable=False,kill_switch=False,secrets_present=True,account_mode_verified=True,instrument_verified=True).reason=='DEMO_NOT_EXPLICITLY_ENABLED'
# 4 kill switch wins
assert execution_gate(mode='DEMO',explicit_enable=True,kill_switch=True,secrets_present=True,account_mode_verified=True,instrument_verified=True).reason=='KILL_SWITCH_ACTIVE'
# 5 missing credentials block
assert execution_gate(mode='DEMO',explicit_enable=True,kill_switch=False,secrets_present=False,account_mode_verified=True,instrument_verified=True).reason=='DEMO_SECRETS_MISSING'
# 6 fully verified demo gate can open
assert execution_gate(mode='DEMO',explicit_enable=True,kill_switch=False,secrets_present=True,account_mode_verified=True,instrument_verified=True).allowed
# 7 base quantity converts to whole contracts by ctVal/lotSz, rounded down
assert contracts_for_base_qty(.057,spec)=='5'
# 8 below-min and incompatible metadata fail closed
try:contracts_for_base_qty(.001,spec);raise AssertionError('expected min-size failure')
except ValueError as e:assert str(e)=='BELOW_MIN_CONTRACT_SIZE'
bad=InstrumentSpec('BTC-USDT-SWAP','BTC','inverse','100','USD','1','1','live')
try:contracts_for_base_qty(.1,bad);raise AssertionError('expected contract-type failure')
except ValueError as e:assert str(e)=='UNSUPPORTED_CONTRACT_TYPE'
# 9 market payload uses contracts, deterministic ID and correct side
p=build_demo_market_order(intent,spec)
assert p['instId']=='BTC-USDT-SWAP' and p['side']=='buy' and p['ordType']=='market' and p['sz']=='5' and p['clOrdId']==x
# 10 long/short account mode explicitly emits posSide
p2=build_demo_market_order(OrderIntent(intent.strategy,intent.signal_id,'BTCUSDT','SHORT',.057,position_mode='long_short'),spec)
assert p2['side']=='sell' and p2['posSide']=='short'
# 11 signing is deterministic and demo header is mandatory
body=canonical_json(p);ts='2026-09-17T14:00:00.000Z'
h=demo_headers('k','secret','pass',ts,'POST','/api/v5/trade/order',body)
assert h['OK-ACCESS-SIGN']==okx_signature(ts,'POST','/api/v5/trade/order',body,'secret') and h['x-simulated-trading']=='1'
# 12 reconciliation never retries blindly after ambiguous submission
assert reconcile_state('SUBMITTED',None)=='QUERY_BEFORE_RETRY'
assert reconcile_state('ACKNOWLEDGED','partially_filled')=='REMOTE_OPEN'
assert reconcile_state('ACKNOWLEDGED','filled')=='FILLED'
print('12/12 DEMO ADAPTER PASS')
