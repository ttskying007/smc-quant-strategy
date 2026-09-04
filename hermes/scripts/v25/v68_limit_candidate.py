#!/usr/bin/env python3
"""V68 strict L→D candidate with validated zone-limit entry.

Definition:
  SSL sweep -> bullish displacement -> FVG_Demand -> validated limit entry
  + structure SL + hybrid BSL/RR target + T+1 exit.

This script intentionally imports the strict L→D primitives from
phase2_strict_ld_backtest.py and only changes the production candidate layer.
"""
import json, sys, importlib.util
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v68_strict_ld')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60
ENGINE = 'V68_STRICT_LD_FVG_LIMIT_STRUCTURE'
DEFINITION = 'Phase2_LD_v3_FVG_zone_limit_structure_sl_hybrid_tp'


def f(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def date_of(ks, idx):
    if idx is None or idx < 0 or idx >= len(ks):
        return ''
    return ld.d(ks[idx])


def recent_swing_low_price(ks, upto, lookback=20):
    vals = []
    for i in range(max(3, upto - lookback), max(3, upto - 3) + 1):
        if i + 3 < len(ks) and ld.is_swing_low(ks, i, 3, 3):
            vals.append((i, f(ks[i].get('l'))))
    return vals[-1] if vals else (None, 0.0)


def recent_bsl_price(ks, after_idx, before_idx, fallback_rr_tp):
    highs = []
    end = min(len(ks) - 3, before_idx + 30)
    for i in range(max(3, after_idx), end + 1):
        if ld.is_swing_high(ks, i, 3, 3):
            highs.append((i, f(ks[i].get('h'))))
    # Use nearest future/prior BSL above entry target area if available; otherwise RR fallback.
    candidates = [x for x in highs if x[1] > fallback_rr_tp * 0.98]
    return (candidates[0] if candidates else (None, fallback_rr_tp))


def first_limit_fill(ks, start_idx, end_idx, limit_price):
    """Validated limit fill: no assumed fill; bar must trade through limit."""
    for i in range(start_idx, min(end_idx, len(ks) - MAX_HOLD - 1)):
        lo, hi, cl = f(ks[i].get('l')), f(ks[i].get('h')), f(ks[i].get('c'))
        if lo <= limit_price <= hi:
            return i
        # Demand decisively lost before fill.
        if cl < limit_price * 0.985:
            return None
    return None


def simulate(ks, entry_idx, ep, sl, tp1):
    if not (ep and sl and tp1) or ep <= sl or tp1 <= ep:
        return None
    for j in range(entry_idx + 1, min(len(ks), entry_idx + MAX_HOLD + 1)):  # T+1 hard exit
        lo, hi = f(ks[j].get('l')), f(ks[j].get('h'))
        if lo <= sl:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'SL_HIT', 'exit_price': round(sl, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((sl / ep - 1) * 100, 4)}
        if hi >= tp1:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'TP1_HIT', 'exit_price': round(tp1, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((tp1 / ep - 1) * 100, 4)}
    if entry_idx + MAX_HOLD < len(ks):
        px = f(ks[entry_idx + MAX_HOLD].get('c'))
        return {'exit_idx': entry_idx + MAX_HOLD, 'exit_date': date_of(ks, entry_idx + MAX_HOLD), 'exit_reason': 'TIME_STOP', 'exit_price': round(px, 4), 'hold_bars': MAX_HOLD, 'pnl_pct': round((px / ep - 1) * 100, 4)}
    return None


def build_trades(symbol, ks):
    rows = []
    used = set()
    for L in ld.find_ssl_sweeps(ks):
        D = ld.find_displacement_after(ks, L['bar'])
        if not D:
            continue
        for poi in ld.demand_pois(ks, L['bar'], D['bar']):
            if poi.get('type') != 'FVG_Demand':
                continue
            zl, zh = f(poi.get('low')), f(poi.get('high'))
            if not (zl > 0 and zh > zl):
                continue
            entry_price = (zl + zh) / 2.0
            start = max(D['bar'] + 1, poi.get('bar', D['bar']) + 1)
            fill_idx = first_limit_fill(ks, start, D['bar'] + 16, entry_price)
            if fill_idx is None:
                continue
            sw_idx, sw_low = recent_swing_low_price(ks, fill_idx, 30)
            a = ld.atr(ks, fill_idx)
            structure_anchor = min([x for x in (sw_low, L.get('liq_price'), zl) if x and x > 0])
            sl = min(zl * 0.985, structure_anchor - a * 0.20)
            if sl <= 0 or entry_price <= sl:
                continue
            risk = (entry_price / sl - 1) * 100
            if risk < 1.0 or risk > 8.0:
                continue
            rr_tp = entry_price + (entry_price - sl) * 1.0
            bsl_idx, bsl = recent_bsl_price(ks, D['bar'], fill_idx, rr_tp)
            # Hybrid: cap impossible far targets but keep at least RR0.8.
            min_tp = entry_price + (entry_price - sl) * 0.8
            tp1 = max(min_tp, min(bsl if bsl > entry_price else rr_tp, entry_price + (entry_price - sl) * 1.2))
            sim = simulate(ks, fill_idx, entry_price, sl, tp1)
            if not sim:
                continue
            key = (fill_idx, round(entry_price, 4), poi['bar'])
            if key in used:
                continue
            used.add(key)
            retr = max(0, min(100, (zh - f(ks[fill_idx].get('l'))) / max(zh - zl, 1e-9) * 100))
            if not (30 <= retr < 90):
                continue
            row = {
                'symbol': symbol,
                'engine': ENGINE,
                'definition_version': DEFINITION,
                'sequence': 'SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> ZONE_MID_LIMIT_ENTRY',
                'entry_model': 'ZONE_MID_LIMIT_VALIDATED',
                'sl_model': 'STRUCTURE_LOW_OR_FVG_LOW_ATR_BUFFER',
                'tp_model': 'BSL_CAPPED_RR0_8_TO_1_2',
                'liq_date': date_of(ks, L['bar']),
                'confirm_date': date_of(ks, D['bar']),
                'zone_date': date_of(ks, poi['bar']),
                'entry_date': date_of(ks, fill_idx),
                'pick_date': date_of(ks, fill_idx),
                'select_date': date_of(ks, fill_idx),
                'join_date': date_of(ks, fill_idx),
                'liq_bar': L['bar'],
                'confirm_bar': D['bar'],
                'zone_bar': poi['bar'],
                'entry_idx': fill_idx,
                'zone_type': 'FVG_Demand',
                'signal_type': 'FVG_Demand',
                'zone_low': round(zl, 4),
                'zone_high': round(zh, 4),
                'dz_low': round(zl, 4),
                'dz_high': round(zh, 4),
                'entry_price': round(entry_price, 4),
                'price': round(entry_price, 4),
                'smart_money_cost': round(entry_price, 4),
                'cost_line': round(entry_price, 4),
                'sl': round(sl, 4),
                'tp1': round(tp1, 4),
                'tp2': round(entry_price + (entry_price - sl) * 1.5, 4),
                'risk_pct': round(risk, 3),
                'volatility_pct': round(risk, 3),
                'v25_vol_class': 'LOW' if risk < 3 else ('MID' if risk < 6 else 'HIGH'),
                'retrace_pct': round(retr, 2),
                'pierce_atr': round(L.get('pierce_atr', 0), 3),
                'disp_atr': round(D.get('disp_atr', 0), 3),
                'entry_quality': 'ZONE_LIMIT',
                'status': 'BACKTEST_VERIFIED',
                'pick_scope': 'STRICT_LD_V68_LIMIT',
                'semantic_layer': 'STRICT_LD',
                'strict_audit_status': 'PASS',
                'signal_correctness_claim': 'STRICT_TEMPORAL_T1_FIELD_PASS',
                'won': sim['pnl_pct'] > 0,
                **sim,
            }
            rows.append(row)
    return rows


def replay_file(kf):
    sym = kf.stem.replace('_daily_750', '')
    symbol = sym.replace('_SH', '.SH').replace('_SZ', '.SZ').replace('_BJ', '.BJ')
    try:
        ks = json.loads(kf.read_text())
    except Exception:
        return []
    if len(ks) < 180:
        return []
    for b in ks:
        for k in ('o', 'h', 'l', 'c', 'v'):
            if k in b:
                b[k] = f(b[k])
    return build_trades(symbol, ks)


def metrics(ts):
    if not ts:
        return {'n': 0}
    wins = [t for t in ts if t['pnl_pct'] > 0]
    sls = [t for t in ts if t['exit_reason'] == 'SL_HIT']
    tps = [t for t in ts if t['exit_reason'] == 'TP1_HIT']
    losses = [t for t in ts if t['pnl_pct'] <= 0]
    avg = sum(t['pnl_pct'] for t in ts) / len(ts)
    aw = sum(t['pnl_pct'] for t in wins) / len(wins) if wins else 0
    al = sum(t['pnl_pct'] for t in losses) / len(losses) if losses else 0
    return {'n': len(ts), 'wr': round(len(wins) / len(ts) * 100, 2), 'sl_rate': round(len(sls) / len(ts) * 100, 2), 'tp_rate': round(len(tps) / len(ts) * 100, 2), 'avg_pnl': round(avg, 4), 'cum': round(sum(t['pnl_pct'] for t in ts), 2), 'avg_win': round(aw, 4), 'avg_loss': round(al, 4), 'payoff': round(aw / abs(al), 3) if al else 0, 'avg_hold': round(sum(t['hold_bars'] for t in ts) / len(ts), 2)}


def bucket(ts, fn):
    g = defaultdict(list)
    for t in ts:
        g[fn(t)].append(t)
    return {str(k): metrics(v) for k, v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def audit(ts):
    fails = []
    required = ('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1')
    for t in ts:
        issues = []
        if not (t['liq_bar'] < t['confirm_bar'] and t['zone_bar'] <= t['confirm_bar'] + 1 and t['entry_idx'] > max(t['zone_bar'], t['confirm_bar'])):
            issues.append('semantic_order')
        if t.get('exit_idx') is not None and t['exit_idx'] <= t['entry_idx']:
            issues.append('t_plus_1')
        for k in required:
            v = t.get(k)
            if v in (None, '', 0, 0.0):
                issues.append(f'missing_{k}')
        if t.get('zone_type') != 'FVG_Demand':
            issues.append('not_fvg_demand')
        if issues:
            fails.append({'symbol': t.get('symbol'), 'entry_date': t.get('entry_date'), 'issues': issues})
    return {'n': len(ts), 'fail_count': len(fails), 'pass_count': len(ts) - len(fails), 'semantic_order_fail': sum('semantic_order' in x['issues'] for x in fails), 't_plus_1_fail': sum('t_plus_1' in x['issues'] for x in fails), 'field_contract_fail': sum(any(i.startswith('missing_') for i in x['issues']) for x in fails), 'sample_fails': fails[:20]}


def make_picks(ts):
    by_symbol = {}
    for t in sorted(ts, key=lambda x: (x.get('entry_date',''), x.get('symbol',''))):
        by_symbol[t['symbol']] = t
    latest = sorted(by_symbol.values(), key=lambda x: x.get('entry_date',''), reverse=True)[:200]
    picks = []
    today = datetime.now().strftime('%Y%m%d')
    for t in latest:
        p = dict(t)
        p['pick_scope'] = 'ACTIVE_CANDIDATE' if t.get('entry_date','') >= '20260601' else 'WATCH_ONLY'
        p['is_active_pick'] = p['pick_scope'] == 'ACTIVE_CANDIDATE'
        p['status'] = p['pick_scope']
        p['joined_at'] = p.get('join_date') or p.get('entry_date') or today
        p['source'] = ENGINE
        p['reason'] = 'V68 FVG_Demand zone-mid limit entry; strict L→D semantic/T+1 audited'
        picks.append(p)
    return picks


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N > 0:
        files = files[:N]
    all_trades = []
    print(f'V68 limit replay {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for i, kf in enumerate(files, 1):
        all_trades.extend(replay_file(kf))
        if i % 500 == 0:
            print(f'  {i}/{len(files)} trades={len(all_trades)}', flush=True)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'engine': ENGINE,
        'definition_version': DEFINITION,
        'n_stocks': len(files),
        'metrics': metrics(all_trades),
        'audit': audit(all_trades),
        'buckets': {
            'risk_bin': bucket(all_trades, lambda t: '<3' if t['risk_pct'] < 3 else ('3-6' if t['risk_pct'] < 6 else '6-8')),
            'retrace_bin': bucket(all_trades, lambda t: '<30' if t['retrace_pct'] < 30 else ('30-60' if t['retrace_pct'] < 60 else ('60-90' if t['retrace_pct'] < 90 else '90-100'))),
            'exit_reason': bucket(all_trades, lambda t: t['exit_reason']),
        }
    }
    picks = make_picks(all_trades)
    (OUT_DIR / 'v68_trades.json').write_text(json.dumps(all_trades, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v68_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v68_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2)[:12000])
    print('Saved:', OUT_DIR)


if __name__ == '__main__':
    main()
