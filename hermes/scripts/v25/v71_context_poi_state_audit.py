#!/usr/bin/env python3
"""V71 Context→Event→POI state audit.

Purpose: stop treating a single-stock POI as valid in isolation.  This audit
classifies every V68 trade into an explicit SMC story before entry:

1. Market context: up continuation, down reversal, range/transition, down continuation.
2. Event: SSL sweep + CHOCH/MSS reversal, or BOS/MSS continuation.
3. Position: whether price actually retraced into a live Demand POI in discount/OTE.
4. Risk/exit semantics: whether SL should be POI break, structure break, or normal pullback.

No production writes.  Uses only bars available at or before entry.
"""
from __future__ import annotations

import json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path('/root/.hermes')
TRADES = ROOT/'smc_opt_v68_strict_ld'/'v68_trades.json'
KLINE = ROOT/'kline_cache'
OUT_DIR = ROOT/'smc_opt_v71_context_poi'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR/'v71_context_poi_state_audit.json'
OUT_MD = OUT_DIR/'v71_context_poi_state_audit.md'


def f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        y = float(x)
        return y if math.isfinite(y) else default
    except Exception:
        return default


def ds(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '')[:8]


def load_ks(symbol: str) -> List[Dict[str, Any]] | None:
    p = KLINE/(symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_750.json')
    if not p.exists():
        return None
    try:
        ks = json.loads(p.read_text())
    except Exception:
        return None
    out = []
    for b in ks:
        nb = dict(b)
        for k in ('o','h','l','c','v'):
            nb[k] = f(nb.get(k))
        out.append(nb)
    return out


def atr(ks: List[Dict[str, Any]], idx: int, n: int = 14) -> float:
    vals = []
    for i in range(max(1, idx-n+1), idx+1):
        b, p = ks[i], ks[i-1]
        vals.append(max(b['h']-b['l'], abs(b['h']-p['c']), abs(b['l']-p['c'])))
    return sum(vals)/len(vals) if vals else max(ks[idx]['c']*0.02, 0.01)


def swing_high(ks: List[Dict[str, Any]], i: int, L: int = 3, R: int = 3) -> bool:
    if i-L < 0 or i+R >= len(ks):
        return False
    h = ks[i]['h']
    return h > 0 and all(ks[j]['h'] < h for j in range(i-L, i)) and all(ks[j]['h'] <= h for j in range(i+1, i+R+1))


def swing_low(ks: List[Dict[str, Any]], i: int, L: int = 3, R: int = 3) -> bool:
    if i-L < 0 or i+R >= len(ks):
        return False
    l = ks[i]['l']
    return l > 0 and all(ks[j]['l'] > l for j in range(i-L, i)) and all(ks[j]['l'] >= l for j in range(i+1, i+R+1))


def swings_before(ks: List[Dict[str, Any]], idx: int, lookback: int = 140, L: int = 3, R: int = 3) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    highs, lows = [], []
    # Only swings confirmed before idx are allowed.
    start = max(L, idx-lookback)
    end = min(idx-R, len(ks)-R-1)
    for i in range(start, end+1):
        if swing_high(ks, i, L, R):
            highs.append({'idx': i, 'price': ks[i]['h'], 'confirm_idx': i+R, 'date': ds(ks[i])})
        if swing_low(ks, i, L, R):
            lows.append({'idx': i, 'price': ks[i]['l'], 'confirm_idx': i+R, 'date': ds(ks[i])})
    return highs, lows


def market_context(ks: List[Dict[str, Any]], idx: int) -> Dict[str, Any]:
    highs, lows = swings_before(ks, idx, 180)
    last_highs, last_lows = highs[-3:], lows[-3:]
    close = ks[idx]['c']
    ret20 = (close/ks[idx-20]['c']-1)*100 if idx >= 20 and ks[idx-20]['c'] else 0.0
    ret60 = (close/ks[idx-60]['c']-1)*100 if idx >= 60 and ks[idx-60]['c'] else 0.0

    hh = len(last_highs) >= 2 and last_highs[-1]['price'] > last_highs[-2]['price']
    hl = len(last_lows) >= 2 and last_lows[-1]['price'] > last_lows[-2]['price']
    lh = len(last_highs) >= 2 and last_highs[-1]['price'] < last_highs[-2]['price']
    ll = len(last_lows) >= 2 and last_lows[-1]['price'] < last_lows[-2]['price']

    last_high = last_highs[-1] if last_highs else None
    last_low = last_lows[-1] if last_lows else None
    broke_last_high = bool(last_high and close > last_high['price'] * 1.001)
    broke_last_low = bool(last_low and close < last_low['price'] / 1.001)

    if hh and hl and ret20 >= -2:
        state = 'UP_CONTINUATION_CONTEXT'
    elif lh and ll and ret20 <= 3:
        state = 'DOWN_REVERSAL_NEEDED_CONTEXT'
    elif broke_last_high and not broke_last_low and ret20 >= 0:
        state = 'BULL_TRANSITION_CONTEXT'
    elif ret60 < -10 and ret20 < 0:
        state = 'DOWN_CONTINUATION_DANGER'
    else:
        state = 'RANGE_OR_TRANSITION_CONTEXT'

    return {
        'market_context': state,
        'hh': hh, 'hl': hl, 'lh': lh, 'll': ll,
        'ret20': round(ret20, 2), 'ret60': round(ret60, 2),
        'last_high': last_high, 'last_low': last_low,
        'broke_last_high': broke_last_high,
        'broke_last_low': broke_last_low,
    }


def detect_ssl_sweep(ks: List[Dict[str, Any]], liq_idx: int) -> Dict[str, Any]:
    if liq_idx < 10 or liq_idx >= len(ks):
        return {'ssl_sweep': False}
    highs, lows = swings_before(ks, liq_idx, 90)
    prior_lows = [x for x in lows if x['idx'] < liq_idx]
    if not prior_lows:
        return {'ssl_sweep': False}
    pool = min(prior_lows[-4:], key=lambda x: x['price'])
    b = ks[liq_idx]
    pierce = (pool['price'] - b['l']) / max(atr(ks, liq_idx), 1e-9)
    reclaim = b['c'] > pool['price'] or (b['c'] > b['o'] and b['l'] < pool['price'])
    return {
        'ssl_sweep': b['l'] < pool['price'] * 0.998 and reclaim,
        'ssl_pool_price': round(pool['price'], 4),
        'ssl_pool_idx': pool['idx'],
        'ssl_pierce_atr': round(pierce, 3),
        'ssl_reclaim_same_bar': reclaim,
    }


def structure_event_between(ks: List[Dict[str, Any]], start: int, end: int) -> Dict[str, Any]:
    # Determine whether the move into confirm bar broke a pre-existing swing high.
    ref_idx = max(0, start-1)
    highs, lows = swings_before(ks, ref_idx, 140)
    last_high = highs[-1] if highs else None
    last_low = lows[-1] if lows else None
    if not last_high:
        return {'struct_event': 'NO_PRIOR_SWING_HIGH'}
    break_idx = None
    for i in range(max(start, 0), min(end, len(ks)-1)+1):
        if ks[i]['c'] > last_high['price'] * 1.001:
            break_idx = i
            break
    if break_idx is None:
        return {'struct_event': 'NO_BULLISH_STRUCTURE_BREAK', 'break_ref_high': last_high}
    pre = market_context(ks, max(start-1, 0))['market_context']
    ev = 'BOS_CONTINUATION' if pre in ('UP_CONTINUATION_CONTEXT','BULL_TRANSITION_CONTEXT') else 'CHOCH_REVERSAL'
    return {
        'struct_event': ev,
        'break_idx': break_idx,
        'break_date': ds(ks[break_idx]),
        'break_ref_high': last_high,
        'break_ref_low': last_low,
    }


def poi_position_and_health(ks: List[Dict[str, Any]], t: Dict[str, Any]) -> Dict[str, Any]:
    liq, conf, entry = int(t.get('liq_bar', 0)), int(t.get('confirm_bar', 0)), int(t.get('entry_idx', 0))
    zl, zh, ep = f(t.get('zone_low')), f(t.get('zone_high')), f(t.get('entry_price'))
    impulse_low = min(ks[i]['l'] for i in range(max(0, liq), min(conf, len(ks)-1)+1)) if 0 <= liq <= conf < len(ks) else zl
    impulse_high = max(ks[i]['h'] for i in range(max(0, liq), min(conf, len(ks)-1)+1)) if 0 <= liq <= conf < len(ks) else zh
    rng = max(impulse_high-impulse_low, 1e-9)
    ep_pos = (ep-impulse_low)/rng*100
    zone_mid = (zl+zh)/2
    zone_pos = (zone_mid-impulse_low)/rng*100
    if zone_pos <= 21:
        pd = 'DEEP_DISCOUNT_BREAK_RISK'
    elif zone_pos <= 38.2:
        pd = 'OTE_DISCOUNT'
    elif zone_pos <= 50:
        pd = 'DISCOUNT'
    elif zone_pos <= 61.8:
        pd = 'EQ_EDGE'
    else:
        pd = 'PREMIUM_INVALID'

    touch = None; reclaim = False; closed_below = False; max_bounce = 0.0
    for i in range(max(conf+1, 0), min(entry, len(ks)-1)+1):
        b = ks[i]
        if touch is None and b['l'] <= zh and b['h'] >= zl:
            touch = i
        if touch is not None:
            closed_below = closed_below or b['c'] < zl
            reclaim = reclaim or (i < entry and b['c'] > zh and b['c'] > b['o'])
            max_bounce = max(max_bounce, (b['h']/max(zl, 1e-9)-1)*100)
    # Entry bar itself can be the touch but not the reaction confirmation; reaction must precede buy.
    return {
        'impulse_low': round(impulse_low, 4), 'impulse_high': round(impulse_high, 4),
        'entry_pos_pct': round(ep_pos, 2), 'zone_pos_pct': round(zone_pos, 2), 'pd_zone': pd,
        'poi_touched_before_entry': touch is not None,
        'poi_touch_idx': touch,
        'poi_reclaim_before_entry': reclaim,
        'poi_closed_below_before_entry': closed_below,
        'pre_entry_bounce_pct': round(max_bounce, 2),
    }


def classify_story(ctx: Dict[str, Any], sweep: Dict[str, Any], struct: Dict[str, Any], poi: Dict[str, Any]) -> Tuple[str, List[str], str, str]:
    fails = []
    context = ctx['market_context']
    struct_ev = struct['struct_event']
    if poi['pd_zone'] in ('PREMIUM_INVALID','EQ_EDGE'):
        fails.append('PRICE_NOT_IN_DISCOUNT_POI')
    if poi['pd_zone'] == 'DEEP_DISCOUNT_BREAK_RISK':
        fails.append('TOO_DEEP_POSSIBLE_STRUCTURE_BREAK')
    if not poi['poi_touched_before_entry']:
        fails.append('NO_POI_TOUCH_BEFORE_ENTRY')
    if not poi['poi_reclaim_before_entry']:
        fails.append('NO_POI_REACTION_BEFORE_ENTRY')
    if poi['poi_closed_below_before_entry']:
        fails.append('POI_ALREADY_CLOSED_BROKEN')

    if sweep.get('ssl_sweep') and struct_ev == 'CHOCH_REVERSAL':
        model = 'REVERSAL_SSL_CHOCH_TO_DEMAND'
        if context == 'DOWN_CONTINUATION_DANGER':
            fails.append('REVERSAL_AGAINST_STRONG_DOWN_CONTEXT')
    elif struct_ev == 'BOS_CONTINUATION' and context in ('UP_CONTINUATION_CONTEXT','BULL_TRANSITION_CONTEXT'):
        model = 'CONTINUATION_BOS_PULLBACK_TO_DEMAND'
    elif sweep.get('ssl_sweep') and struct_ev != 'CHOCH_REVERSAL':
        model = 'SWEEP_WITHOUT_CHOCH_INVALID'
        fails.append('SWEEP_NOT_CONFIRMED_BY_CHOCH')
    elif struct_ev in ('BOS_CONTINUATION','CHOCH_REVERSAL'):
        model = 'STRUCTURE_BREAK_WITHOUT_LIQUIDITY_CONTEXT'
        if context.startswith('DOWN') and struct_ev != 'CHOCH_REVERSAL':
            fails.append('WRONG_STRUCTURE_FOR_CONTEXT')
    else:
        model = 'NO_VALID_SMC_STORY'
        fails.append('NO_VALID_LIQ_OR_STRUCTURE_EVENT')

    if not fails and model == 'REVERSAL_SSL_CHOCH_TO_DEMAND':
        exit_rule = 'SL_POI_CLOSE_BREAK_OR_LAST_SSL_LOW; TP_NEXT_BSL_POOL'
        entry_rule = 'BUY_AFTER_POI_TOUCH_AND_RECLAIM'
    elif not fails and model == 'CONTINUATION_BOS_PULLBACK_TO_DEMAND':
        exit_rule = 'SL_LAST_HL_OR_POI_CLOSE_BREAK; TP_PRIOR_HH_OR_NEXT_BSL'
        entry_rule = 'BUY_AFTER_BOS_PULLBACK_TO_OB_FVG_OTE'
    else:
        exit_rule = 'NO_TRADE'
        entry_rule = 'NO_TRADE'
    return model, fails, entry_rule, exit_rule


def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    wins = sum(1 for r in rows if r['won'])
    sl = sum(1 for r in rows if r['exit_reason'] == 'SL_HIT')
    return {
        'n': len(rows), 'wr': round(wins/len(rows)*100, 2),
        'avg_pnl': round(sum(r['pnl_pct'] for r in rows)/len(rows), 4),
        'sl_rate': round(sl/len(rows)*100, 2),
        'median_pnl': round(statistics.median([r['pnl_pct'] for r in rows]), 4),
    }


def bucket(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    g = defaultdict(list)
    for r in rows:
        g[str(r.get(key))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0]))}


def audit_trade(t: Dict[str, Any]) -> Dict[str, Any] | None:
    ks = load_ks(t['symbol'])
    if not ks:
        return None
    entry = int(t.get('entry_idx', 0)); liq = int(t.get('liq_bar', 0)); conf = int(t.get('confirm_bar', 0))
    if entry <= 0 or entry >= len(ks):
        return None
    ctx = market_context(ks, max(liq-1, 0))
    sweep = detect_ssl_sweep(ks, liq)
    struct = structure_event_between(ks, liq, conf)
    poi = poi_position_and_health(ks, t)
    story, fails, entry_rule, exit_rule = classify_story(ctx, sweep, struct, poi)
    return {
        'symbol': t['symbol'], 'entry_date': t.get('entry_date'), 'exit_date': t.get('exit_date'),
        'entry_idx': entry, 'liq_idx': liq, 'confirm_idx': conf,
        'zone_type': t.get('zone_type'), 'zone_low': f(t.get('zone_low')), 'zone_high': f(t.get('zone_high')),
        'entry_price': f(t.get('entry_price')), 'exit_reason': t.get('exit_reason'), 'pnl_pct': f(t.get('pnl_pct')),
        'won': f(t.get('pnl_pct')) > 0,
        **{k: v for k, v in ctx.items() if k not in ('last_high','last_low')},
        'last_high_price': round(f((ctx.get('last_high') or {}).get('price')), 4),
        'last_low_price': round(f((ctx.get('last_low') or {}).get('price')), 4),
        **sweep,
        'struct_event': struct.get('struct_event'),
        'break_idx': struct.get('break_idx'),
        'break_date': struct.get('break_date'),
        'break_ref_high': round(f((struct.get('break_ref_high') or {}).get('price')), 4),
        **poi,
        'smc_story': story,
        'story_valid': not fails,
        'fail_reasons': fails,
        'primary_fail': 'VALID' if not fails else fails[0],
        'entry_rule': entry_rule,
        'exit_rule': exit_rule,
    }


def main() -> None:
    trades = json.loads(TRADES.read_text())
    rows = []
    for i, t in enumerate(trades, 1):
        r = audit_trade(t)
        if r:
            rows.append(r)
        if i % 1000 == 0:
            print('audited', i, flush=True)
    valid = [r for r in rows if r['story_valid']]
    invalid = [r for r in rows if not r['story_valid']]
    fail_counts = Counter(x for r in invalid for x in r['fail_reasons'])
    report = {
        'generated_at': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'source': str(TRADES),
        'overall': metrics(rows),
        'valid_story': metrics(valid),
        'invalid_story': metrics(invalid),
        'valid_pct': round(len(valid)/max(len(rows),1)*100, 2),
        'fail_reason_counts': dict(fail_counts.most_common()),
        'buckets': {
            'market_context': bucket(rows, 'market_context'),
            'smc_story': bucket(rows, 'smc_story'),
            'struct_event': bucket(rows, 'struct_event'),
            'pd_zone': bucket(rows, 'pd_zone'),
            'primary_fail': bucket(rows, 'primary_fail'),
            'story_valid': bucket(rows, 'story_valid'),
        },
        'rows': rows,
        'valid_samples': valid[:120],
        'invalid_samples': invalid[:120],
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    lines = ['# V71 Context→Event→POI State Audit', '', '## 总览', '| scope | n | WR | avg | SL率 | median |', '|---|---:|---:|---:|---:|---:|']
    for name in ['overall','valid_story','invalid_story']:
        m = report[name]
        lines.append(f"| {name} | {m['n']} | {m.get('wr',0)} | {m.get('avg_pnl',0)} | {m.get('sl_rate',0)} | {m.get('median_pnl',0)} |")
    lines += ['', f"有效完整SMC故事占比: **{report['valid_pct']}%**", '', '## 失败原因', '| reason | count | pct all |', '|---|---:|---:|']
    for k, v in fail_counts.most_common():
        lines.append(f'| {k} | {v} | {round(v/max(len(rows),1)*100,2)} |')
    for title, key in [('市场状态','market_context'), ('SMC故事','smc_story'), ('结构事件','struct_event'), ('POI位置','pd_zone'), ('主失败原因','primary_fail')]:
        lines += ['', f'## {title}', '| bucket | n | WR | avg | SL率 | median |', '|---|---:|---:|---:|---:|---:|']
        for k, m in report['buckets'][key].items():
            lines.append(f"| {k} | {m['n']} | {m.get('wr',0)} | {m.get('avg_pnl',0)} | {m.get('sl_rate',0)} | {m.get('median_pnl',0)} |")
    OUT_MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({
        'overall': report['overall'],
        'valid_story': report['valid_story'],
        'valid_pct': report['valid_pct'],
        'top_fail_reasons': dict(fail_counts.most_common(10)),
        'story_buckets': report['buckets']['smc_story'],
        'context_buckets': report['buckets']['market_context'],
        'outputs': {'json': str(OUT_JSON), 'md': str(OUT_MD)},
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
