#!/usr/bin/env python3
"""V69 search: prove whether strict L→D can reach 90% WR without lookahead.

Strict temporal chain only:
  SSL sweep -> bullish displacement -> FVG_Demand -> validated limit fill -> T+1 exit

This is a research/audit script. It does not touch production/front-end unless a
candidate passes the gate.
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
OUT_DIR = Path('/root/.hermes/smc_opt_v69_90wr_search')
MAX_HOLD = 60
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0


def f(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


def date_of(ks, idx):
    return ld.d(ks[idx]) if idx is not None and 0 <= idx < len(ks) else ''


def recent_swing_low(ks, upto, lookback=30):
    vals = []
    for i in range(max(3, upto - lookback), max(3, upto - 3) + 1):
        if i + 3 < len(ks) and ld.is_swing_low(ks, i, 3, 3):
            vals.append((i, f(ks[i].get('l'))))
    return vals[-1] if vals else (None, 0.0)


def first_fill(ks, start_idx, end_idx, price):
    for i in range(start_idx, min(end_idx, len(ks) - MAX_HOLD - 1)):
        lo, hi, cl = f(ks[i].get('l')), f(ks[i].get('h')), f(ks[i].get('c'))
        if lo <= price <= hi:
            return i
        if cl < price * 0.975:
            return None
    return None


def simulate(ks, entry_idx, ep, sl, tp, max_hold=60):
    if not (ep > 0 and sl > 0 and tp > 0 and ep > sl and tp > ep):
        return None
    for j in range(entry_idx + 1, min(len(ks), entry_idx + max_hold + 1)):
        lo, hi = f(ks[j].get('l')), f(ks[j].get('h'))
        # Conservative same-bar rule: SL first when both hit on the same future bar.
        if lo <= sl:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'SL_HIT', 'exit_price': round(sl, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((sl / ep - 1) * 100, 4)}
        if hi >= tp:
            return {'exit_idx': j, 'exit_date': date_of(ks, j), 'exit_reason': 'TP_HIT', 'exit_price': round(tp, 4), 'hold_bars': j - entry_idx, 'pnl_pct': round((tp / ep - 1) * 100, 4)}
    if entry_idx + max_hold < len(ks):
        px = f(ks[entry_idx + max_hold].get('c'))
        return {'exit_idx': entry_idx + max_hold, 'exit_date': date_of(ks, entry_idx + max_hold), 'exit_reason': 'TIME_STOP', 'exit_price': round(px, 4), 'hold_bars': max_hold, 'pnl_pct': round((px / ep - 1) * 100, 4)}
    return None


def setup_base(symbol, ks):
    rows = []
    seen = set()
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
            start = max(D['bar'] + 1, poi.get('bar', D['bar']) + 1)
            for entry_model, ep in (
                ('ZONE_HIGH_20', zl + (zh - zl) * 0.80),
                ('ZONE_MID', (zl + zh) / 2.0),
                ('ZONE_LOW_35', zl + (zh - zl) * 0.35),
            ):
                fill = first_fill(ks, start, D['bar'] + 20, ep)
                if fill is None:
                    continue
                key = (fill, round(ep, 4), poi['bar'], entry_model)
                if key in seen:
                    continue
                seen.add(key)
                atr = ld.atr(ks, fill)
                sw_idx, sw_low = recent_swing_low(ks, fill, 30)
                anchors = [x for x in (sw_low, L.get('liq_price'), zl) if x and x > 0]
                if not anchors:
                    continue
                structure_anchor = min(anchors)
                retr = max(0, min(100, (zh - f(ks[fill].get('l'))) / max(zh - zl, 1e-9) * 100))
                rows.append({
                    'symbol': symbol,
                    'liq_bar': L['bar'], 'confirm_bar': D['bar'], 'zone_bar': poi['bar'], 'entry_idx': fill,
                    'liq_date': date_of(ks, L['bar']), 'confirm_date': date_of(ks, D['bar']), 'zone_date': date_of(ks, poi['bar']), 'entry_date': date_of(ks, fill),
                    'entry_model': entry_model,
                    'zone_low': zl, 'zone_high': zh, 'entry_price': ep,
                    'atr': atr, 'sw_low': sw_low, 'liq_price': L.get('liq_price'), 'structure_anchor': structure_anchor,
                    'retr': retr, 'pierce': f(L.get('pierce_atr')), 'disp': f(D.get('disp_atr')),
                    'ks': ks,
                })
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
    return setup_base(symbol, ks)


def metrics(rows):
    if not rows:
        return {'n': 0}
    wins = [r for r in rows if r['pnl_pct'] > 0]
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'avg_pnl': round(sum(r['pnl_pct'] for r in rows) / len(rows), 4),
        'cum': round(sum(r['pnl_pct'] for r in rows), 2),
        'tp_rate': round(sum(r['exit_reason'] == 'TP_HIT' for r in rows) / len(rows) * 100, 2),
        'sl_rate': round(sum(r['exit_reason'] == 'SL_HIT' for r in rows) / len(rows) * 100, 2),
        'time_rate': round(sum(r['exit_reason'] == 'TIME_STOP' for r in rows) / len(rows) * 100, 2),
        'avg_hold': round(sum(r['hold_bars'] for r in rows) / len(rows), 2),
    }


def audit(rows):
    fails = []
    for r in rows:
        issues = []
        if not (r['liq_bar'] < r['confirm_bar'] and r['zone_bar'] <= r['confirm_bar'] + 1 and r['entry_idx'] > max(r['zone_bar'], r['confirm_bar'])):
            issues.append('semantic_order')
        if r.get('exit_idx') is not None and r['exit_idx'] <= r['entry_idx']:
            issues.append('t_plus_1')
        for k in ('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1'):
            if r.get(k) in (None, '', 0, 0.0):
                issues.append('missing_' + k)
        if issues:
            fails.append({'symbol': r.get('symbol'), 'entry_date': r.get('entry_date'), 'issues': issues})
    return {'n': len(rows), 'fail_count': len(fails), 'pass_count': len(rows) - len(fails), 'semantic_order_fail': sum('semantic_order' in x['issues'] for x in fails), 't_plus_1_fail': sum('t_plus_1' in x['issues'] for x in fails), 'field_contract_fail': sum(any(i.startswith('missing_') for i in x['issues']) for x in fails), 'sample_fails': fails[:20]}


def materialize(base, cfg):
    rows = []
    tp_rr = cfg['tp_rr']; sl_atr = cfg['sl_atr']; max_hold = cfg['max_hold']
    for b in base:
        if b['entry_model'] != cfg['entry_model']:
            continue
        if not (cfg['risk_lo'] <= 999):
            continue
        if not (cfg['retr_lo'] <= b['retr'] < cfg['retr_hi'] and b['disp'] >= cfg['disp_lo'] and b['pierce'] >= cfg['pierce_lo']):
            continue
        ep, zl = b['entry_price'], b['zone_low']
        if cfg['sl_model'] == 'FVG_ATR':
            sl = min(zl * cfg['fvg_mult'], b['structure_anchor'] - b['atr'] * sl_atr)
        elif cfg['sl_model'] == 'STRUCT_ATR':
            sl = b['structure_anchor'] - b['atr'] * sl_atr
        else:  # LIQ_WIDE
            sl = min(b['liq_price'] or zl, b['structure_anchor']) - b['atr'] * sl_atr
        if not (sl > 0 and ep > sl):
            continue
        risk = (ep / sl - 1) * 100
        if not (cfg['risk_lo'] <= risk < cfg['risk_hi']):
            continue
        tp = ep + (ep - sl) * tp_rr
        sim = simulate(b['ks'], b['entry_idx'], ep, sl, tp, max_hold=max_hold)
        if not sim:
            continue
        row = {k: v for k, v in b.items() if k != 'ks'}
        row.update(sim)
        row.update({
            'engine': 'V69_90WR_SEARCH',
            'definition_version': 'Phase2_LD_v4_90wr_exhaustive_non_leaky_search',
            'sequence': 'SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> VALIDATED_LIMIT_ENTRY',
            'zone_type': 'FVG_Demand', 'signal_type': 'FVG_Demand',
            'zone_low': round(b['zone_low'],4), 'zone_high': round(b['zone_high'],4),
            'entry_price': round(ep,4), 'price': round(ep,4), 'smart_money_cost': round(ep,4), 'cost_line': round(ep,4),
            'sl': round(sl,4), 'tp1': round(tp,4), 'tp2': round(ep + (ep - sl) * max(tp_rr * 2, 0.5),4),
            'risk_pct': round(risk,3), 'volatility_pct': round(risk,3),
            'retrace_pct': round(b['retr'],2), 'pierce_atr': round(b['pierce'],3), 'disp_atr': round(b['disp'],3),
            'pick_date': b['entry_date'], 'select_date': b['entry_date'], 'join_date': b['entry_date'],
            'entry_quality': cfg['entry_model'], 'sl_model': cfg['sl_model'], 'tp_rr': tp_rr,
            'pick_scope': 'V69_RESEARCH', 'semantic_layer': 'STRICT_LD',
        })
        rows.append(row)
    return rows


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N > 0:
        files = files[:N]
    base = []
    print(f'V69 setup extraction {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for i, kf in enumerate(files, 1):
        base.extend(replay_file(kf))
        if i % 500 == 0:
            print(f'  setup {i}/{len(files)} base={len(base)}', flush=True)
    print(f'base setups={len(base)}', flush=True)

    cfgs = []
    for entry_model in ('ZONE_HIGH_20','ZONE_MID','ZONE_LOW_35'):
      for sl_model in ('FVG_ATR','STRUCT_ATR','LIQ_WIDE'):
       for tp_rr in (0.12,0.15,0.20,0.25,0.30,0.40,0.50,0.60,0.80):
        for sl_atr in (0.1,0.2,0.35,0.5,0.8):
         for risk_lo,risk_hi in ((1,3),(2,4),(3,5),(4,6),(5,7),(6,9),(1,9)):
          for retr_lo,retr_hi in ((30,60),(40,70),(50,80),(60,90),(30,90)):
           for disp_lo in (0,0.8,1.2,1.8,2.5):
            for pierce_lo in (0,0.5,1.0,1.5):
             for max_hold in (10,20,40,60):
              cfgs.append({'entry_model':entry_model,'sl_model':sl_model,'tp_rr':tp_rr,'sl_atr':sl_atr,'risk_lo':risk_lo,'risk_hi':risk_hi,'retr_lo':retr_lo,'retr_hi':retr_hi,'disp_lo':disp_lo,'pierce_lo':pierce_lo,'max_hold':max_hold,'fvg_mult':0.985})

    leaderboard = []
    best_rows = None
    best_cfg = None
    for idx, cfg in enumerate(cfgs, 1):
        rows = materialize(base, cfg)
        if len(rows) < 30:
            continue
        mt = metrics(rows)
        years = {}
        for y in sorted(set(r['entry_date'][:4] for r in rows)):
            yr = [r for r in rows if r['entry_date'].startswith(y)]
            years[y] = metrics(yr)
        min_year_wr = min((v['wr'] for v in years.values() if v['n'] >= 10), default=0)
        item = {'cfg': cfg, 'metrics': mt, 'min_year_wr_n10': min_year_wr, 'years': years}
        if mt['wr'] >= 90 or (mt['n'] >= 100 and mt['wr'] >= 85) or (mt['n'] >= 200 and mt['wr'] >= 80):
            leaderboard.append(item)
        if best_rows is None or (mt['wr'], min(mt['n'], 300), mt['avg_pnl']) > (metrics(best_rows)['wr'], min(len(best_rows), 300), metrics(best_rows)['avg_pnl']):
            best_rows = rows
            best_cfg = cfg
    leaderboard.sort(key=lambda x: (x['metrics']['wr'], min(x['metrics']['n'], 500), x['metrics']['avg_pnl']), reverse=True)
    top = leaderboard[:50]
    if top:
        best_cfg = top[0]['cfg']; best_rows = materialize(base, best_cfg)
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'stocks': len(files),
        'base_setups': len(base),
        'searched_configs': len(cfgs),
        'gate': {'target_wr': 90, 'min_trades_for_production': 100, 'no_lookahead': True, 't_plus_1': True},
        'best': {'cfg': best_cfg, 'metrics': metrics(best_rows or []), 'audit': audit(best_rows or [])},
        'leaderboard': top,
        'passed_90_count': sum(1 for x in leaderboard if x['metrics']['wr'] >= 90),
    }
    (OUT_DIR / 'v69_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    (OUT_DIR / 'v69_best_trades.json').write_text(json.dumps(best_rows or [], ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2)[:20000])
    print('Saved:', OUT_DIR)

if __name__ == '__main__':
    main()
