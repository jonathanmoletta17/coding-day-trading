from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
import base64, hashlib, hmac, json, math, re

ALNUM=re.compile(r'^[A-Za-z0-9]+$')
REAL_MONEY_ENABLED=False

@dataclass(frozen=True)
class InstrumentSpec:
    inst_id:str
    base_ccy:str
    ct_type:str
    ct_val:str
    ct_val_ccy:str
    lot_sz:str
    min_sz:str
    state:str

@dataclass(frozen=True)
class OrderIntent:
    strategy:str
    signal_id:str
    symbol:str
    side:str
    base_qty:float
    td_mode:str='cross'
    position_mode:str='net'

@dataclass(frozen=True)
class GateResult:
    allowed:bool
    reason:str


def deterministic_clordid(strategy:str,signal_id:str,purpose:str='entry')->str:
    digest=hashlib.sha256(f'{strategy}:{signal_id}:{purpose}'.encode()).hexdigest()[:24]
    prefix='STB'+('E' if purpose=='entry' else 'X')
    x=(prefix+digest)[:32]
    assert len(x)<=32 and ALNUM.match(x)
    return x


def execution_gate(*,mode:str,explicit_enable:bool,kill_switch:bool,secrets_present:bool,
                   account_mode_verified:bool,instrument_verified:bool)->GateResult:
    m=(mode or '').upper()
    if m!='DEMO':return GateResult(False,'REAL_MONEY_HARD_BLOCK')
    if not explicit_enable:return GateResult(False,'DEMO_NOT_EXPLICITLY_ENABLED')
    if kill_switch:return GateResult(False,'KILL_SWITCH_ACTIVE')
    if not secrets_present:return GateResult(False,'DEMO_SECRETS_MISSING')
    if not account_mode_verified:return GateResult(False,'ACCOUNT_MODE_UNVERIFIED')
    if not instrument_verified:return GateResult(False,'INSTRUMENT_METADATA_UNVERIFIED')
    return GateResult(True,'DEMO_ALLOWED')


def _d(x)->Decimal:return Decimal(str(x))


def contracts_for_base_qty(base_qty:float,spec:InstrumentSpec)->str:
    if not math.isfinite(float(base_qty)) or float(base_qty)<=0:raise ValueError('INVALID_BASE_QTY')
    if spec.state!='live':raise ValueError('INSTRUMENT_NOT_LIVE')
    if spec.ct_type!='linear':raise ValueError('UNSUPPORTED_CONTRACT_TYPE')
    if spec.ct_val_ccy!=spec.base_ccy:raise ValueError('CTVAL_CCY_NOT_BASE')
    ct=_d(spec.ct_val);lot=_d(spec.lot_sz);minimum=_d(spec.min_sz)
    if ct<=0 or lot<=0 or minimum<=0:raise ValueError('INVALID_INSTRUMENT_METADATA')
    raw=_d(base_qty)/ct
    units=(raw/lot).to_integral_value(rounding=ROUND_DOWN)
    qty=units*lot
    if qty<minimum:raise ValueError('BELOW_MIN_CONTRACT_SIZE')
    # Avoid exponent notation because exchange request bodies expect ordinary decimal strings.
    return format(qty.normalize(),'f')


def build_demo_market_order(intent:OrderIntent,spec:InstrumentSpec)->dict:
    expected={'BTCUSDT':'BTC-USDT-SWAP','ETHUSDT':'ETH-USDT-SWAP'}.get(intent.symbol)
    if not expected or spec.inst_id!=expected:raise ValueError('SYMBOL_INSTRUMENT_MISMATCH')
    if intent.side not in ('LONG','SHORT'):raise ValueError('INVALID_SIDE')
    if intent.position_mode not in ('net','long_short'):raise ValueError('INVALID_POSITION_MODE')
    payload={
        'instId':spec.inst_id,
        'tdMode':intent.td_mode,
        'clOrdId':deterministic_clordid(intent.strategy,intent.signal_id,'entry'),
        'side':'buy' if intent.side=='LONG' else 'sell',
        'ordType':'market',
        'sz':contracts_for_base_qty(intent.base_qty,spec),
    }
    if intent.position_mode=='long_short':payload['posSide']='long' if intent.side=='LONG' else 'short'
    return payload


def canonical_json(payload:dict)->str:
    return json.dumps(payload,separators=(',',':'),ensure_ascii=False)


def okx_signature(timestamp:str,method:str,request_path:str,body:str,secret_key:str)->str:
    if not secret_key:raise ValueError('SECRET_KEY_MISSING')
    msg=f'{timestamp}{method.upper()}{request_path}{body}'.encode()
    sig=hmac.new(secret_key.encode(),msg,hashlib.sha256).digest()
    return base64.b64encode(sig).decode()


def demo_headers(api_key:str,secret_key:str,passphrase:str,timestamp:str,method:str,request_path:str,body:str='')->dict:
    if not api_key or not passphrase:raise ValueError('DEMO_CREDENTIALS_INCOMPLETE')
    return {
        'Content-Type':'application/json',
        'OK-ACCESS-KEY':api_key,
        'OK-ACCESS-SIGN':okx_signature(timestamp,method,request_path,body,secret_key),
        'OK-ACCESS-TIMESTAMP':timestamp,
        'OK-ACCESS-PASSPHRASE':passphrase,
        'x-simulated-trading':'1',
    }


def reconcile_state(local_state:str,remote_state:str|None)->str:
    r=(remote_state or '').lower()
    if r in ('filled',):return 'FILLED'
    if r in ('canceled','mmp_canceled'):return 'CANCELED'
    if r in ('live','partially_filled'):return 'REMOTE_OPEN'
    if r:
        return 'REMOTE_UNKNOWN'
    if local_state in ('PREPARED','SUBMITTED','ACKNOWLEDGED'):return 'QUERY_BEFORE_RETRY'
    return 'NO_REMOTE_ORDER'
