#!/usr/bin/env python3
"""V69 full-market L→D entry/SL/TP matrix audit.

Goal:
  1. Extract one unique setup per strict L→D opportunity.
  2. Keep FVG_Demand as tradable signal; compute OB/OB_FVG only as observation.
  3. Compare executable entry models, SL models, and TP models on the same setup base.
  4. Save full per-trade variants + compact bucket tables for deep review.

No production/frontend sync is performed by this script.
"""
import json, sys, importlib.util, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v69_matrix')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60
ENGINE = 'V69_STRICT_LD_ENTRY_SL_TP_MATRIX'
DEFINITION = 'Phase2_LD_v4_unique_setup_entry_sl_tp_matrix_no_production_sync'
ENTRY_MODELS = ('reclaim_close', 'zone_high_limit', 'zone_mid_limit')
SL_MODELS = ('current_poi_atr_sl', 'sweep_low_atr_sl', 'swing_low_atr_sl')
TP_MODELS = ('rr0_8', 'rr1_0', 'bsl_target', 'hybrid_bsl_rr')


def f(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def date_of(ks, idx):
    if idx is None or idx < 0 or idx >= len(ks):
        return ''
    return ld.d(ks[idx])


def pct(a, b):
    return (a / b - 1.0) * 100.0 if b else 0.0


def recent_swing_low(ks, upto, lookback=30):
    vals = []
    for i in range(max(3, upto - lookback), max(3, upto - 3) + 1):
        if i + 3 < len(ks) and ld.is_swing_low(ks, i, 3, 3):
            vals.append((i, f(ks[i].get('l'))))
    return vals[-1] if vals else (None, 0.0)


def nearest_bsl_above(ks, from_idx, upto_idx, entry_price):
    # BSL target is the nearest confirmed swing high above entry around/after displacement.
    candidates = []
    start = max(3, from_idx - 20)
    end = min(len(ks) - 4, max(upto_idx + 30, from_idx + 5))
    for i in range(start, end + 1):
        if ld.is_swing_high(ks, i, 3, 3):
            hi = f(ks[i].get('h'))
            if hi > entry_price * 1.002:
                candidates.append((abs(i - upto_idx), i, hi))
    if not candidates:
        return None, 0.0
    _, i, hi = sorted(candidates, key=lambda x: (x[0], x[2]))[0]
    return i, hi


def first_limit_fill(ks, start_idx, end_idx, limit_price, zone_low):
    for i in range(start_idx, min(end_idx, len(ks) - MAX_HOLD - 1)):
        lo, hi, cl = f(ks[i].get('l')), f(ks[i].get('h')), f(ks[i].get('c'))
        if lo <= limit_price <= hi:
            return i
        # Demand decisively lost before executable fill; stop this setup for this entry model.
        if cl < zone_low:
            return None
    return None


def reclaim_entry(ks, poi, dbar, max_wait=16):
    zl, zh = f(poi['low']), f(poi['high'])
    for i in range(max(dbar + 1, poi.get('bar', dbar) + 1), min(len(ks) - MAX_HOLD - 1, dbar + max_wait + 1)):
        op, cl, hi, lo = f(ks[i].get('o')), f(ks[i].get('c')), f(ks[i].get('h')), f(ks[i].get('l'))
        if not (lo <= zh and hi >= zl):
            continue
        if cl < zl:
            return None
        reclaim = cl >= max(zl, (zl + zh) / 2.0) and cl > op
        pin = (min(op, cl) - lo) >= abs(cl - op) * 1.3 and cl >= zl
        if reclaim or pin:
            return i, cl
    return None


def executable_entry(ks, setup, entry_model):
    poi = setup['poi']
    dbar = setup['D']['bar']
    zl, zh = setup['zone_low'], setup['zone_high']
    start = max(dbar + 1, poi.get('bar', dbar) + 1)
    end = dbar + 18
    if entry_model == 'reclaim_close':
        got = reclaim_entry(ks, poi, dbar, 18)
        if not got:
            return None
        return {'entry_idx': got[0], 'entry_price': got[1], 'fill_type': 'reclaim_close'}
    if entry_model == 'zone_high_limit':
        ep = zh
    elif entry_model == 'zone_mid_limit':
        ep = (zl + zh) / 2.0
    else:
        return None
    eidx = first_limit_fill(ks, start, end, ep, zl)
    if eidx is None:
        return None
    return {'entry_idx': eidx, 'entry_price': ep, 'fill_type': 'validated_limit'}


def sl_price(ks, setup, entry_idx, entry_price, sl_model):
    zl = setup['zone_low']
    a = ld.atr(ks, entry_idx)
    if sl_model == 'current_poi_atr_sl':
        anchor = zl
        sl = min(zl * 0.985, zl - a * 0.25)
        reason = 'zone_low_atr_buffer'
    elif sl_model == 'sweep_low_atr_sl':
        anchor = f(setup['L'].get('liq_price')) or zl
        sl = anchor - a * 0.20
        reason = 'sweep_liquidity_low_atr_buffer'
    elif sl_model == 'swing_low_atr_sl':
        sw_idx, sw_low = recent_swing_low(ks, entry_idx, 30)
        anchor = sw_low or f(setup['L'].get('liq_price')) or zl
        sl = anchor - a * 0.20
        reason = 'recent_swing_low_atr_buffer' if sw_low else 'fallback_sweep_low_atr_buffer'
    else:
        return None
    if sl <= 0 or entry_price <= sl:
        return None
    risk = pct(entry_price, sl)
    if risk < 0.3 or risk > 15.0:
        return None
    return {'sl': sl, 'sl_anchor': anchor, 'risk_pct': risk, 'sl_reason': reason}


def tp_price(ks, setup, entry_idx, entry_price, sl, tp_model):
    risk_abs = entry_price - sl
    rr08 = entry_price + risk_abs * 0.8
    rr10 = entry_price + risk_abs * 1.0
    bsl_idx, bsl = nearest_bsl_above(ks, setup['D']['bar'], entry_idx, entry_price)
    if tp_model == 'rr0_8':
        tp, reason = rr08, 'fixed_rr_0_8'
    elif tp_model == 'rr1_0':
        tp, reason = rr10, 'fixed_rr_1_0'
    elif tp_model == 'bsl_target':
        if not bsl or bsl <= entry_price:
            return None
        tp, reason = bsl, 'nearest_bsl'
    elif tp_model == 'hybrid_bsl_rr':
        if bsl and bsl > entry_price:
            # Keep BSL but cap at RR1.2 and floor at RR0.8.
            tp = max(rr08, min(bsl, entry_price + risk_abs * 1.2))
            reason = 'bsl_capped_rr0_8_to_1_2'
        else:
            tp = rr10
            reason = 'fallback_rr_1_0'
    else:
        return None
    if tp <= entry_price:
        return None
    return {'tp1': tp, 'target_rr': (tp - entry_price) / risk_abs if risk_abs else 0, 'tp_reason': reason, 'bsl_idx': bsl_idx, 'bsl_price': bsl}


def simulate(ks, entry_idx, ep, sl, tp1):
    # Strict T+1: exit scan starts at next bar only.
    if not (ep > 0 and sl > 0 and tp1 > ep and ep > sl):
        return None
    for j in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):
        lo, hi = f(ks[j].get('l')), f(ks[j].get('h'))
        if lo <= sl:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'SL_HIT', 'exit_price': round(sl, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round(pct(sl, ep), 4)}
        if hi >= tp1:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'TP1_HIT', 'exit_price': round(tp1, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round(pct(tp1, ep), 4)}
    stop_idx = entry_idx + MAX_HOLD
    if stop_idx < len(ks):
        px = f(ks[stop_idx].get('c'))
        return {'exit_idx': stop_idx, 'exit_date': date_of(ks, stop_idx), 'exit_reason': 'TIME_STOP', 'exit_price': round(px, 4), 'hold_bars': MAX_HOLD, 'pnl_pct': round(pct(px, ep), 4)}
    return None


def unique_setups(symbol, ks):
    setups = []
    seen = set()
    for L in ld.find_ssl_sweeps(ks):
        D = ld.find_displacement_after(ks, L['bar'])
        if not D:
            continue
        pois = ld.demand_pois(ks, L['bar'], D['bar'])
        # Observation keeps OB visible, but tradable matrix only uses FVG_Demand.
        for poi in pois:
            zl, zh = f(poi.get('low')), f(poi.get('high'))
            if not (zl > 0 and zh > zl):
                continue
            key = (symbol, L['bar'], D['bar'], poi.get('type'), poi.get('bar'), round(zl, 4), round(zh, 4))
            if key in seen:
                continue
            seen.add(key)
            setups.append({
                'setup_id': f"{symbol}|L{L['bar']}|D{D['bar']}|Z{poi.get('bar')}|{poi.get('type')}",
                'symbol': symbol,
                'L': L,
                'D': D,
                'poi': poi,
                'zone_type': poi.get('type'),
                'zone_low': zl,
                'zone_high': zh,
            })
    return setups


def variant_rows(symbol, ks):
    rows = []
    obs_rows = []
    for s in unique_setups(symbol, ks):
        base = {
            'setup_id': s['setup_id'],
            'symbol': symbol,
            'zone_type': s['zone_type'],
            'liq_bar': s['L']['bar'],
            'confirm_bar': s['D']['bar'],
            'zone_bar': s['poi']['bar'],
            'liq_date': date_of(ks, s['L']['bar']),
            'confirm_date': date_of(ks, s['D']['bar']),
            'zone_date': date_of(ks, s['poi']['bar']),
            'zone_low': round(s['zone_low'], 4),
            'zone_high': round(s['zone_high'], 4),
            'pierce_atr': round(f(s['L'].get('pierce_atr')), 3),
            'disp_atr': round(f(s['D'].get('disp_atr')), 3),
            'zone_width_pct': round(pct(s['zone_high'], s['zone_low']), 3),
        }
        obs_rows.append(base)
        if s['zone_type'] != 'FVG_Demand':
            continue
        for em in ENTRY_MODELS:
            ent = executable_entry(ks, s, em)
            if not ent:
                continue
            eidx, ep = ent['entry_idx'], ent['entry_price']
            retr = max(0.0, min(100.0, (s['zone_high'] - f(ks[eidx].get('l'))) / max(s['zone_high'] - s['zone_low'], 1e-9) * 100.0))
            for sm in SL_MODELS:
                sl = sl_price(ks, s, eidx, ep, sm)
                if not sl:
                    continue
                for tm in TP_MODELS:
                    tp = tp_price(ks, s, eidx, ep, sl['sl'], tm)
                    if not tp:
                        continue
                    sim = simulate(ks, eidx, ep, sl['sl'], tp['tp1'])
                    if not sim:
                        continue
                    rows.append({
                        'engine': ENGINE,
                        'definition_version': DEFINITION,
                        'sequence': 'SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> EXECUTABLE_ENTRY',
                        **base,
                        'entry_model': em,
                        'sl_model': sm,
                        'tp_model': tm,
                        'entry_idx': eidx,
                        'entry_date': date_of(ks, eidx),
                        'pick_date': date_of(ks, eidx),
                        'join_date': date_of(ks, eidx),
                        'entry_price': round(ep, 4),
                        'price': round(ep, 4),
                        'smart_money_cost': round(ep, 4),
                        'cost_line': round(ep, 4),
                        'sl': round(sl['sl'], 4),
                        'tp1': round(tp['tp1'], 4),
                        'target_rr': round(tp['target_rr'], 3),
                        'risk_pct': round(sl['risk_pct'], 3),
                        'volatility_pct': round(sl['risk_pct'], 3),
                        'retrace_pct': round(retr, 2),
                        'sl_reason': sl['sl_reason'],
                        'tp_reason': tp['tp_reason'],
                        'bsl_price': round(tp['bsl_price'], 4) if tp['bsl_price'] else 0,
                        'fill_type': ent['fill_type'],
                        'won': sim['pnl_pct'] > 0,
                        **sim,
                    })
    return rows, obs_rows


def replay_file(kf):
    sym = kf.stem.replace('_daily_750', '')
    symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    try:
        ks = json.loads(kf.read_text())
    except Exception:
        return [], []
    if len(ks) < 180:
        return [], []
    for b in ks:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                b[k] = f(b[k])
    return variant_rows(symbol, ks)


def metrics(ts):
    if not ts:
        return {'n': 0}
    wins = [t for t in ts if t['pnl_pct'] > 0]
    losses = [t for t in ts if t['pnl_pct'] <= 0]
    sls = [t for t in ts if t['exit_reason'] == 'SL_HIT']
    tps = [t for t in ts if t['exit_reason'] == 'TP1_HIT']
    avg = sum(t['pnl_pct'] for t in ts) / len(ts)
    aw = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0.0
    al = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0.0
    return {
        'n': len(ts),
        'wr': round(len(wins) / len(ts) * 100.0, 2),
        'sl_rate': round(len(sls) / len(ts) * 100.0, 2),
        'tp_rate': round(len(tps) / len(ts) * 100.0, 2),
        'avg_pnl': round(avg, 4),
        'cum_pnl': round(sum(t['pnl_pct'] for t in ts), 2),
        'avg_win': round(aw, 4),
        'avg_loss': round(al, 4),
        'payoff': round(aw / abs(al), 3) if al else 0,
        'avg_hold': round(sum(t['hold_bars'] for t in ts) / len(ts), 2),
    }


def bucket_key(t, name):
    if name == 'signal': return t['zone_type']
    if name == 'entry': return t['entry_model']
    if name == 'sl': return t['sl_model']
    if name == 'tp': return t['tp_model']
    if name == 'combo': return f"{t['entry_model']}|{t['sl_model']}|{t['tp_model']}"
    if name == 'sl_reason': return t['sl_reason']
    if name == 'exit_reason': return t['exit_reason']
    if name == 'hold_bin':
        h = t['hold_bars']
        return '01_1bar' if h <= 1 else ('02_2_3' if h <= 3 else ('03_4_7' if h <= 7 else ('04_8_15' if h <= 15 else ('05_16_30' if h <= 30 else '06_31_60'))))
    if name == 'retrace_bin':
        r = t['retrace_pct']
        return 'a_<30' if r < 30 else ('b_30_60' if r < 60 else ('c_60_90' if r < 90 else 'd_90_100+'))
    if name == 'risk_bin':
        r = t['risk_pct']
        return 'a_<2' if r < 2 else ('b_2_4' if r < 4 else ('c_4_6' if r < 6 else ('d_6_8' if r < 8 else ('e_8_12' if r < 12 else 'f_12+'))))
    if name == 'year': return (t.get('entry_date') or '')[:4]
    return 'NA'


def bucket(ts, name):
    g = defaultdict(list)
    for t in ts:
        g[bucket_key(t, name)].append(t)
    return {str(k): metrics(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def combo_table(ts):
    g = defaultdict(list)
    for t in ts:
        g[(t['entry_model'], t['sl_model'], t['tp_model'])].append(t)
    rows = []
    for key, vals in g.items():
        m = metrics(vals)
        rows.append({'entry_model': key[0], 'sl_model': key[1], 'tp_model': key[2], **m})
    return sorted(rows, key=lambda x: (-x['wr'], -x['n'], -x['avg_pnl']))


def audit(ts):
    fails = []
    required = ('symbol','setup_id','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1','entry_model','sl_model','tp_model','sl_reason','hold_bars','retrace_pct')
    for t in ts:
        issues = []
        if t['zone_type'] != 'FVG_Demand':
            issues.append('not_fvg_demand')
        if not (t['liq_bar'] < t['confirm_bar'] and t['zone_bar'] <= t['confirm_bar'] + 1 and t['entry_idx'] > max(t['zone_bar'], t['confirm_bar'])):
            issues.append('semantic_order')
        if t.get('exit_idx') is not None and t['exit_idx'] <= t['entry_idx']:
            issues.append('t_plus_1')
        if t.get('entry_model', '').endswith('_limit'):
            # Re-check fill bar actually traded through the claimed limit entry.
            # Full bar data is not in row, so this is checked at generation; keep field for contract.
            pass
        for k in required:
            v = t.get(k)
            if v in (None, '', 0, 0.0) and k not in ('retrace_pct',):
                issues.append(f'missing_{k}')
        if issues:
            fails.append({'symbol': t.get('symbol'), 'setup_id': t.get('setup_id'), 'entry_date': t.get('entry_date'), 'combo': bucket_key(t, 'combo'), 'issues': issues})
    return {
        'n': len(ts),
        'fail_count': len(fails),
        'pass_count': len(ts) - len(fails),
        'semantic_order_fail': sum('semantic_order' in x['issues'] for x in fails),
        't_plus_1_fail': sum('t_plus_1' in x['issues'] for x in fails),
        'field_contract_fail': sum(any(i.startswith('missing_') for i in x['issues']) for x in fails),
        'sample_fails': fails[:30],
    }


def observation_report(obs_rows):
    c = Counter(r['zone_type'] for r in obs_rows)
    return {
        'unique_setup_count': len(obs_rows),
        'by_zone_type': dict(sorted(c.items())),
        'decision': 'Only FVG_Demand is tradable in this matrix; OB_Demand and OB_FVG_Demand are observation-only because previous strict L→D audits showed OB buckets drag expectancy.',
    }


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N > 0:
        files = files[:N]
    all_rows = []
    all_obs = []
    print(f'V69 matrix replay {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for i, kf in enumerate(files, 1):
        rows, obs = replay_file(kf)
        all_rows.extend(rows)
        all_obs.extend(obs)
        if i % 250 == 0:
            print(f'  {i}/{len(files)} variants={len(all_rows)} setups={len(all_obs)}', flush=True)
    table = combo_table(all_rows)
    best = table[0] if table else {}
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'definition_version': DEFINITION,
        'n_stocks': len(files),
        'n_variant_trades': len(all_rows),
        'unique_setup_observation': observation_report(all_obs),
        'matrix_contract': {
            'entry_models': ENTRY_MODELS,
            'sl_models': SL_MODELS,
            'tp_models': TP_MODELS,
            'production_synced': False,
            'frontend_synced': False,
        },
        'overall_metrics': metrics(all_rows),
        'best_combo': best,
        'audit': audit(all_rows),
        'buckets': {name: bucket(all_rows, name) for name in ('signal','entry','sl','tp','sl_reason','exit_reason','hold_bin','retrace_bin','risk_bin','year')},
        'combo_table': table,
        'loser_samples': sorted([t for t in all_rows if t['pnl_pct'] <= 0], key=lambda x: (x['entry_date'], x['symbol']))[:200],
    }
    (OUT_DIR / 'v69_matrix_trades.json').write_text(json.dumps(all_rows, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v69_unique_setups_observation.json').write_text(json.dumps(all_obs, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v69_matrix_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    # Also write a compact markdown table for mobile inspection.
    lines = ['# V69 Matrix Combo Table', '', '| entry | SL | TP | n | WR | avg | SL% | TP% | hold |', '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in table[:80]:
        lines.append(f"| {r['entry_model']} | {r['sl_model']} | {r['tp_model']} | {r['n']} | {r['wr']} | {r['avg_pnl']} | {r['sl_rate']} | {r['tp_rate']} | {r['avg_hold']} |")
    (OUT_DIR / 'v69_combo_table.md').write_text('\n'.join(lines))
    print(json.dumps({k: report[k] for k in ('generated_at','n_stocks','n_variant_trades','unique_setup_observation','best_combo','audit')}, ensure_ascii=False, indent=2))
    print('Saved:', OUT_DIR)


if __name__ == '__main__':
    main()
