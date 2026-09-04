#!/usr/bin/env python3
"""Root-cause audit for Phase2 strict L→D SL/WR problem.

Compares signal source, entry timing/price, SL design, and TP/RR design on the
same unique strict L→D setup universe. Output is aggregate only to keep files
small enough for rapid iteration.
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
OUT = Path('/root/.hermes/smc_opt_v25/phase2_root_cause_audit.json')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60
RR_SET = (0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5)


def f(x):
    try: return float(x or 0)
    except Exception: return 0.0


def sim(ks, entry_idx, ep, sl, tp1, max_hold=MAX_HOLD):
    if not (ep and sl and tp1) or ep <= sl or tp1 <= ep:
        return None
    for j in range(entry_idx + 1, min(len(ks), entry_idx + max_hold + 1)):  # T+1 exit
        lo, hi = f(ks[j].get('l')), f(ks[j].get('h'))
        if lo <= sl:
            return {'reason': 'SL', 'pnl': (sl / ep - 1) * 100, 'hold': j - entry_idx}
        if hi >= tp1:
            return {'reason': 'TP', 'pnl': (tp1 / ep - 1) * 100, 'hold': j - entry_idx}
    if entry_idx + max_hold < len(ks):
        px = f(ks[entry_idx + max_hold].get('c'))
        return {'reason': 'TIME', 'pnl': (px / ep - 1) * 100, 'hold': max_hold}
    return None


def metrics(rows):
    if not rows:
        return {'n': 0}
    wins = [r for r in rows if r['pnl'] > 0]
    sls = [r for r in rows if r['reason'] == 'SL']
    tps = [r for r in rows if r['reason'] == 'TP']
    losses = [r for r in rows if r['pnl'] <= 0]
    avg = sum(r['pnl'] for r in rows) / len(rows)
    aw = sum(r['pnl'] for r in wins) / len(wins) if wins else 0
    al = sum(r['pnl'] for r in losses) / len(losses) if losses else 0
    return {
        'n': len(rows),
        'wr': round(len(wins) / len(rows) * 100, 2),
        'sl_rate': round(len(sls) / len(rows) * 100, 2),
        'tp_rate': round(len(tps) / len(rows) * 100, 2),
        'avg_pnl': round(avg, 4),
        'cum': round(sum(r['pnl'] for r in rows), 2),
        'avg_win': round(aw, 4),
        'avg_loss': round(al, 4),
        'payoff': round(aw / abs(al), 3) if al else 0,
        'avg_hold': round(sum(r['hold'] for r in rows) / len(rows), 2),
    }


def add(bucket, key, row):
    bucket[str(key)].append(row)


def bucket_metrics(bucket):
    return {k: metrics(v) for k, v in sorted(bucket.items(), key=lambda kv: str(kv[0]))}


def setup_universe(symbol, ks):
    setups = []
    used = set()
    for L in ld.find_ssl_sweeps(ks):
        D = ld.find_displacement_after(ks, L['bar'])
        if not D:
            continue
        for poi in ld.demand_pois(ks, L['bar'], D['bar']):
            e = ld.find_reclaim_entry(ks, poi, D['bar'])
            if e is None:
                continue
            key = (D['bar'], e, poi['type'], poi['bar'])
            if key in used:
                continue
            used.add(key)
            ep_close = f(ks[e].get('c'))
            if ep_close <= 0:
                continue
            a = ld.atr(ks, e)
            zl, zh = poi['low'], poi['high']
            width = max(zh - zl, 1e-9)
            base_sl = min(zl * 0.985, zl - a * 0.25)
            if base_sl <= 0:
                continue
            retr = max(0, min(100, (zh - f(ks[e].get('l'))) / width * 100))
            setups.append({
                'symbol': symbol,
                'ks': ks,
                'entry_idx': e,
                'entry_close': ep_close,
                'entry_next_open': f(ks[e+1].get('o')) if e+1 < len(ks) else 0,
                'entry_zone_mid': (zl + zh) / 2,
                'entry_zone_high': zh,
                'entry_zone_low': zl,
                'zone_type': poi['type'],
                'zone_low': zl,
                'zone_high': zh,
                'zone_width_pct': width / max(zl, 1e-9) * 100,
                'base_sl': base_sl,
                'atr': a,
                'retrace_pct': retr,
                'pierce_atr': L['pierce_atr'],
                'wick_ratio': L.get('wick_ratio', 0),
                'disp_atr': D['disp_atr'],
                'bars_L_to_D': D['bar'] - L['bar'],
                'bars_D_to_E': e - D['bar'],
                'liq_bar': L['bar'],
                'disp_bar': D['bar'],
            })
    # dedup one POI per entry. Same empirical priority as main script.
    priority = {'FVG_Demand': 0, 'OB_Demand': 1, 'OB_FVG_Demand': 2}
    best = {}
    for s in setups:
        k = s['entry_idx']
        old = best.get(k)
        if old is None or (priority.get(s['zone_type'], 9), -s['disp_atr'], -s['pierce_atr']) < (priority.get(old['zone_type'], 9), -old['disp_atr'], -old['pierce_atr']):
            best[k] = s
    return list(best.values())


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
        for k in ('o','h','l','c','v'):
            if k in b:
                b[k] = f(b[k])
    return setup_universe(symbol, ks)


def binv(x, cuts, labels):
    for c, lab in zip(cuts, labels):
        if x < c:
            return lab
    return labels[-1]


def main():
    files = sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N > 0:
        files = files[:N]
    print(f'Phase2 root-cause audit {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    setups = []
    for i, kf in enumerate(files, 1):
        setups.extend(replay_file(kf))
        if i % 500 == 0:
            print(f'  {i}/{len(files)} setups={len(setups)}', flush=True)

    variant_rows = defaultdict(list)
    rr_rows = defaultdict(list)
    zone_rows = defaultdict(list)
    risk_rows = defaultdict(list)
    retrace_rows = defaultdict(list)
    disp_rows = defaultdict(list)
    timing_rows = defaultdict(list)
    combo_rows = defaultdict(list)

    for s in setups:
        ks, e = s['ks'], s['entry_idx']
        entry_variants = {
            'A_close_reclaim_current': s['entry_close'],
            'B_next_open_Tplus1_entry': s['entry_next_open'],
            'C_zone_high_limit': s['entry_zone_high'],
            'D_zone_mid_limit': s['entry_zone_mid'],
        }
        sl_variants = {
            'S1_zone_low_minus_1p5pct_or_ATR25_current': s['base_sl'],
            'S2_zone_low_minus_0p8pct_or_ATR10_tighter': min(s['zone_low'] * 0.992, s['zone_low'] - s['atr'] * 0.10),
            'S3_zone_low_minus_2p5pct_or_ATR50_wider': min(s['zone_low'] * 0.975, s['zone_low'] - s['atr'] * 0.50),
            'S4_sweep_low_proxy': min(s['base_sl'], s['zone_low'] - s['atr'] * 0.75),
        }
        for ename, ep in entry_variants.items():
            if ep <= 0 or ep <= s['base_sl']:
                continue
            for sname, sl in sl_variants.items():
                if sl <= 0 or ep <= sl:
                    continue
                risk = (ep / sl - 1) * 100
                if risk < 1 or risk > 10:
                    continue
                for rr in RR_SET:
                    out = sim(ks, e if ename != 'B_next_open_Tplus1_entry' else e+1, ep, sl, ep + (ep - sl) * rr)
                    if not out:
                        continue
                    row = {'pnl': out['pnl'], 'reason': out['reason'], 'hold': out['hold'], 'risk': risk}
                    key = f'{ename}|{sname}|RR{rr}'
                    variant_rows[key].append(row)
                    if ename == 'A_close_reclaim_current' and sname == 'S1_zone_low_minus_1p5pct_or_ATR25_current':
                        rr_rows[rr].append(row)
                        add(zone_rows, s['zone_type'], row)
                        add(risk_rows, binv(risk, [2,4,6,8], ['<2','2-4','4-6','6-8','>=8']), row)
                        add(retrace_rows, binv(s['retrace_pct'], [30,60,90], ['<30','30-60','60-90','90-100']), row)
                        add(disp_rows, binv(s['disp_atr'], [0.5,0.8,1.2,1.8], ['<0.5','0.5-0.8','0.8-1.2','1.2-1.8','>=1.8']), row)
                        add(timing_rows, f"L2D_{binv(s['bars_L_to_D'], [3,6,10], ['<3','3-5','6-9','>=10'])}|D2E_{binv(s['bars_D_to_E'], [2,5,9], ['<2','2-4','5-8','>=9'])}", row)
                        add(combo_rows, f"{s['zone_type']}|risk{binv(risk, [2,4,6,8], ['<2','2-4','4-6','6-8','>=8'])}|retr{binv(s['retrace_pct'], [30,60,90], ['<30','30-60','60-90','90-100'])}", row)

    # rank variants: production-relevant sample size, WR, avg_pnl, lower SL.
    ranked = []
    for k, rows in variant_rows.items():
        m = metrics(rows)
        if m['n'] >= max(200, len(setups) // 20):
            ranked.append((m['avg_pnl'], m['wr'], -m['sl_rate'], k, m))
    ranked.sort(reverse=True)

    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'n_stocks': len(files),
        'unique_setups': len(setups),
        'note': 'Rows in RR/bucket sections multiply unique setups by 7 RR targets. Use variant_rank to isolate entry/SL/TP design.',
        'current_baseline_all_rr': metrics(rr_rows['0.8'] + rr_rows['1.0'] + rr_rows['1.2'] + rr_rows['1.5'] + rr_rows['0.5'] + rr_rows['0.6'] + rr_rows['0.7']),
        'rr_target_current_entry_sl': bucket_metrics(rr_rows),
        'zone_type_current_entry_sl_all_rr': bucket_metrics(zone_rows),
        'risk_current_entry_sl_all_rr': bucket_metrics(risk_rows),
        'retrace_current_entry_sl_all_rr': bucket_metrics(retrace_rows),
        'disp_atr_current_entry_sl_all_rr': bucket_metrics(disp_rows),
        'timing_current_entry_sl_all_rr': bucket_metrics(timing_rows),
        'combo_current_entry_sl_all_rr_top': dict(sorted(bucket_metrics(combo_rows).items(), key=lambda kv: kv[1].get('avg_pnl', -999), reverse=True)[:30]),
        'variant_rank_top30': [{'variant': k, **m} for _,__,___,k,m in ranked[:30]],
        'variant_rank_bottom20': [{'variant': k, **m} for _,__,___,k,m in ranked[-20:]],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2)[:12000])
    print('Saved:', OUT)

if __name__ == '__main__':
    main()
