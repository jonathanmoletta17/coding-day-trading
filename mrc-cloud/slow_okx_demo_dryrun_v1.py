from __future__ import annotations
import asyncio, json, os
from slow_execution_adapter_v1 import InstrumentSpec, OrderIntent, build_demo_market_order, execution_gate
from slow_okx_demo_diagnostic_v2 import DemoDiagnosticV2

TARGETS=(
    ('BTCUSDT','BTC-USDT-SWAP','LONG',0.001),
    ('ETHUSDT','ETH-USDT-SWAP','SHORT',0.01),
)

async def main():
    d=DemoDiagnosticV2()
    try:
        cfg=await d.private_get('/api/v5/account/config')
        if not cfg: raise RuntimeError('ACCOUNT_CONFIG_EMPTY')
        c=cfg[0]
        private_swaps=await d.private_get('/api/v5/account/instruments',{'instType':'SWAP'})
        private_ids={x.get('instId') for x in private_swaps}

        payloads=[]
        public_verified=True
        for symbol,inst_id,side,base_qty in TARGETS:
            rows=await d.public_get('/api/v5/public/instruments',{'instType':'SWAP','instId':inst_id})
            if len(rows)!=1:
                public_verified=False
                payloads.append({'instId':inst_id,'error':'PUBLIC_INSTRUMENT_NOT_UNIQUE'})
                continue
            x=rows[0]
            spec=InstrumentSpec(
                inst_id=x.get('instId',''),
                base_ccy=x.get('ctValCcy',''),
                ct_type=x.get('ctType',''),
                ct_val=x.get('ctVal',''),
                ct_val_ccy=x.get('ctValCcy',''),
                lot_sz=x.get('lotSz',''),
                min_sz=x.get('minSz',''),
                state=x.get('state',''),
            )
            intent=OrderIntent(
                strategy='SLOW_TREND_BREAKOUT_V1',
                signal_id=f'DRYRUN{symbol}001',
                symbol=symbol,
                side=side,
                base_qty=base_qty,
                position_mode='net' if c.get('posMode')=='net_mode' else 'long_short',
            )
            payload=build_demo_market_order(intent,spec)
            payloads.append({'instId':inst_id,'base_qty':base_qty,'payload':payload})

        acct_lv=c.get('acctLv')
        account_mode_verified=acct_lv in ('2','3','4')
        targets_private_available=all(inst_id in private_ids for _,inst_id,_,_ in TARGETS)
        explicit_enable=os.getenv('MRC_DEMO_EXECUTION_ENABLED','0')=='1'
        kill_switch=os.getenv('MRC_KILL_SWITCH','1')!='0'
        mode=os.getenv('MRC_EXECUTION_MODE','DEMO')
        secrets_present=all(os.getenv(n,'').strip() for n in ('OKX_DEMO_API_KEY','OKX_DEMO_SECRET_KEY','OKX_DEMO_PASSPHRASE'))
        gate=execution_gate(
            mode=mode,
            explicit_enable=explicit_enable,
            kill_switch=kill_switch,
            secrets_present=secrets_present,
            account_mode_verified=account_mode_verified,
            instrument_verified=targets_private_available,
        )
        out={
            'account':{'acctLv':acct_lv,'posMode':c.get('posMode')},
            'private_swap_count':len(private_swaps),
            'account_mode_verified':account_mode_verified,
            'targets_private_available':targets_private_available,
            'public_metadata_verified':public_verified,
            'dry_run_payloads':payloads,
            'execution_gate':{'allowed':gate.allowed,'reason':gate.reason},
            'kill_switch':kill_switch,
            'explicit_demo_execution_enabled':explicit_enable,
            'order_submission_performed':False,
        }
        print('OKX_DEMO_DRYRUN='+json.dumps(out,separators=(',',':')),flush=True)
    finally:
        await d.close()

if __name__=='__main__':
    asyncio.run(main())
