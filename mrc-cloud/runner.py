import hashlib
import math
import os

import uvicorn
import app as core


def _available(rows, cutoff_ms):
    if cutoff_ms is None:
        return list(rows or [])
    out = []
    for row in rows or []:
        try:
            if int(row.get('timestamp', 0)) <= int(cutoff_ms):
                out.append(row)
        except Exception:
            continue
    return out


def causal_flow(raw, side, cutoff_ms=None):
    direction = 1 if side == 'LONG' else -1
    taker = _available(raw.get('t') or [], cutoff_ms)
    oi = _available(raw.get('o') or [], cutoff_ms)
    top = _available(raw.get('l') or [], cutoff_ms)

    ratio = core.f(taker[-1].get('buySellRatio'), 1) if taker else 1.0
    aligned_taker_log = math.log(max(ratio, 1e-9)) * direction

    oi_now = core.f(oi[-1].get('sumOpenInterest')) if oi else 0.0
    oi_prev = core.f(oi[-2].get('sumOpenInterest')) if len(oi) > 1 else oi_now
    doi = oi_now / oi_prev - 1 if oi_prev else 0.0

    ls_now = core.f(top[-1].get('longShortRatio'), 1) if top else 1.0
    ls_prev = core.f(top[-2].get('longShortRatio'), ls_now) if len(top) > 1 else ls_now
    aligned_dls = ((ls_now / ls_prev - 1) if ls_prev else 0.0) * direction

    funding = core.f((raw.get('p') or {}).get('lastFundingRate'))
    return {
        'taker_ratio': ratio,
        'aligned_taker_log': aligned_taker_log,
        'doi': doi,
        'top_ls': ls_now,
        'aligned_dls': aligned_dls,
        'funding': funding,
        'aligned_funding': funding * direction,
        'causal_cutoff_ms': cutoff_ms,
    }


def causal_plan(e, raw, eq, now):
    side = e['side']
    fl = causal_flow(raw, side, e['signal_ms'])
    score = 0.75
    why = ['acceptance outside previous UTC-hour boundary']

    if fl['aligned_taker_log'] > math.log(1.10):
        score += 1.0
        why.append('aggressive taker flow aligned at signal close')
    elif fl['aligned_taker_log'] > 0:
        score += 0.4
        why.append('taker flow mildly aligned at signal close')
    else:
        score -= 0.5
        why.append('taker flow opposed at signal close')

    if fl['doi'] > 0:
        score += 0.75
        why.append('open interest expanding at signal close')
    else:
        score -= 0.25
        why.append('open interest not expanding at signal close')

    if fl['aligned_dls'] > 0:
        score += 0.4
        why.append('top-trader positioning change aligned at signal close')
    elif fl['aligned_dls'] < 0:
        score -= 0.2
        why.append('top-trader positioning change opposed at signal close')

    # Funding is displayed as current context but deliberately excluded from
    # the score here because premiumIndex is not an event-time historical snapshot.
    bid = core.f(raw['b']['bidPrice'])
    ask = core.f(raw['b']['askPrice'])
    entry = ask if side == 'LONG' else bid
    R = e['R']
    boundary = e['boundary']
    chase = (entry - boundary) / R if side == 'LONG' else (boundary - entry) / R
    age_min = (now - e['signal_ms']) / 60000

    decision = side if score >= 1.75 and chase <= 0.20 and age_min <= 20 else 'NO_TRADE'
    if chase > 0.20:
        why.append('entry too extended from boundary')
    if age_min > 20:
        why.append('stale event')
    if score < 1.75:
        why.append('order-flow score below threshold')

    stop = boundary - 0.25 * R if side == 'LONG' else boundary + 0.25 * R
    risk = eq * core.RISK_PCT
    per_unit = abs(entry - stop)
    qty = min(risk / per_unit if per_unit else 0, eq / entry if entry else 0)
    target = entry + 1.5 * per_unit if side == 'LONG' else entry - 1.5 * per_unit
    signal_id = hashlib.sha256((e['event_id'] + str(e['signal_ms']) + ':causal-v2').encode()).hexdigest()[:24]
    confidence = max(1, min(99, int(50 + 15 * (score - 1.5))))
    why.append(f"TI={fl['taker_ratio']:.3f} dOI={fl['doi']*100:.3f}% dLS={fl['aligned_dls']*100:.3f}%")

    return core.Plan(
        e['symbol'], signal_id, e['event_id'], side, decision, confidence,
        round(score, 3), entry, stop, target, risk, qty, 1.5, chase,
        '; '.join(why), core.iso(),
    )


core.flow = causal_flow
core.plan = causal_plan
core.STATE['strategy'] = 'OF-BOUNDARY-causal-v2'

if __name__ == '__main__':
    uvicorn.run(core.app, host='0.0.0.0', port=int(os.getenv('PORT', '8080')))
