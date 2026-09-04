#!/usr/bin/env python3
"""V316 no-write audit: V185 exit-mechanism frontier and residual loss attribution.

Scope:
- Read V185 historical trades and local daily K-line cache only.
- Do not modify production/frontend/watchlist.
- Re-simulate T+1 executable exit variants from already-selected V185 entries.
- Test whether an exit-only change can clear the remaining V185 production gap without
  using future information available at entry.
"""
from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v185_combined_production_candidate' / 'v185_trades.json'
KDIR = ROOT / 'kline_cache'
AUDIT = ROOT / 'smc_audit'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUTDIR = AUDIT / f'v316_v185_exit_mechanism_frontier_no_write_{TS}'
LATEST = AUDIT / 'v316_v185_exit_mechanism_frontier_latest.json'

# Formal target: exceed current V185 while preserving breadth and T+1.
PRODUCTION_GATE = {
    'n_min': 300,
    'min_year_n_min': 40,
    'wr_min': 87.0,
    'avg_min': 6.8,
    'year_wr_min': 84.0,
    'micro_max': 1.0,
}


def fnum(x, default=None):
    if x is None or x == '':
        return default
    try:
        if isinstance(x, bool):
            return default
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def dkey(v) -> str:
    s = ''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s) >= 8 else ''


def load_bars(symbol: str):
    if not symbol or '.' not in symbol:
        return []
    code, exch = symbol.split('.')
    p = KDIR / f'{code}_{exch}_daily_750.json'
    if not p.exists():
        return []
    data = json.load(open(p))
    if isinstance(data, dict):
        for k in ('data', 'klines', 'bars'):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    out = []
    for b in data if isinstance(data, list) else []:
        o = fnum(b.get('o')); h = fnum(b.get('h')); l = fnum(b.get('l')); c = fnum(b.get('c'))
        date = dkey(b.get('t') or b.get('date') or b.get('day'))
        if date and None not in (o, h, l, c):
            out.append({'date': date, 'o': o, 'h': h, 'l': l, 'c': c})
    return sorted(out, key=lambda x: x['date'])


def t1_path(row):
    entry_date = dkey(row.get('entry_date'))
    bars = load_bars(str(row.get('symbol') or ''))
    return [b for b in bars if entry_date and b['date'] > entry_date]


def simulate(row, cfg):
    entry = fnum(row.get('entry_price') or row.get('price'))
    sl0 = fnum(row.get('sl') or row.get('sl_price'))
    if entry is None or sl0 is None or entry <= 0 or sl0 <= 0 or sl0 >= entry:
        return None
    risk = entry - sl0
    risk_pct = risk / entry * 100.0
    max_hold = int(cfg.get('max_hold') or fnum(row.get('max_hold'), 10) or 10)
    r_tp = float(cfg.get('r_tp', 1.5))
    tp = entry + risk * r_tp
    be_trigger = cfg.get('be_trigger_r')
    trail_trigger = cfg.get('trail_trigger_r')
    trail_r = cfg.get('trail_r')
    early_time_cut = cfg.get('early_time_cut')
    early_min_mfe_r = cfg.get('early_min_mfe_r')
    giveback_cut = cfg.get('giveback_cut')
    partial = float(cfg.get('partial', 0.0))
    runner_r_tp = cfg.get('runner_r_tp')

    path = t1_path(row)
    if not path:
        return None
    stop = sl0
    best_h = -1e18
    worst_l = 1e18
    partial_done = False
    partial_pnl = 0.0
    partial_reason = ''

    for i, b in enumerate(path, start=1):
        best_h = max(best_h, b['h'])
        worst_l = min(worst_l, b['l'])
        mfe_r_open = (best_h - entry) / risk
        # Update non-leaking protective stop based on already-observed prior/up-to-current high.
        if be_trigger is not None and mfe_r_open >= float(be_trigger):
            stop = max(stop, entry)
        if trail_trigger is not None and trail_r is not None and mfe_r_open >= float(trail_trigger):
            stop = max(stop, best_h - risk * float(trail_r))
        # Conservative same-day ordering: protective stop before target.
        if b['o'] <= stop:
            pnl = (b['o'] / entry - 1.0) * 100.0
            if partial_done:
                pnl = partial_pnl + (1.0 - partial) * pnl
            return finish(row, b, 'GAP_STOP' if stop > sl0 else 'GAP_SL', b['o'], pnl, i, best_h, worst_l, cfg, partial_reason)
        if b['l'] <= stop:
            pnl = (stop / entry - 1.0) * 100.0
            reason = 'BE_STOP' if abs(stop - entry) < 1e-9 else ('TRAIL_STOP' if stop > sl0 else 'SL')
            if partial_done:
                pnl = partial_pnl + (1.0 - partial) * pnl
            return finish(row, b, reason, stop, pnl, i, best_h, worst_l, cfg, partial_reason)
        if partial > 0 and (not partial_done) and b['h'] >= tp:
            partial_done = True
            partial_pnl = partial * ((tp / entry - 1.0) * 100.0)
            partial_reason = f'PARTIAL_{r_tp}R'
            if runner_r_tp is None:
                # Full target, no runner.
                return finish(row, b, 'TP', tp, (tp / entry - 1.0) * 100.0, i, best_h, worst_l, cfg, partial_reason)
            # Runner becomes break-even protected after TP1.
            stop = max(stop, entry)
        elif partial <= 0 and b['h'] >= tp:
            return finish(row, b, 'TP', tp, (tp / entry - 1.0) * 100.0, i, best_h, worst_l, cfg, partial_reason)
        if partial_done and runner_r_tp is not None:
            runner_tp = entry + risk * float(runner_r_tp)
            if b['h'] >= runner_tp:
                runner_pnl = (runner_tp / entry - 1.0) * 100.0
                pnl = partial_pnl + (1.0 - partial) * runner_pnl
                return finish(row, b, 'RUNNER_TP', runner_tp, pnl, i, best_h, worst_l, cfg, partial_reason)
        if early_time_cut and i >= int(early_time_cut):
            mfe_r = (best_h - entry) / risk
            if early_min_mfe_r is None or mfe_r < float(early_min_mfe_r):
                pnl = (b['c'] / entry - 1.0) * 100.0
                if partial_done:
                    pnl = partial_pnl + (1.0 - partial) * pnl
                return finish(row, b, 'EARLY_TIME_WEAK_MFE', b['c'], pnl, i, best_h, worst_l, cfg, partial_reason)
        if giveback_cut is not None:
            mfe_pct = (best_h / entry - 1.0) * 100.0
            cur_pct = (b['c'] / entry - 1.0) * 100.0
            if mfe_pct >= risk_pct and (mfe_pct - cur_pct) >= float(giveback_cut) * risk_pct:
                pnl = cur_pct
                if partial_done:
                    pnl = partial_pnl + (1.0 - partial) * pnl
                return finish(row, b, 'GIVEBACK_CUT', b['c'], pnl, i, best_h, worst_l, cfg, partial_reason)
        if i >= max_hold:
            pnl = (b['c'] / entry - 1.0) * 100.0
            if partial_done:
                pnl = partial_pnl + (1.0 - partial) * pnl
            return finish(row, b, 'TIME', b['c'], pnl, i, best_h, worst_l, cfg, partial_reason)
    b = path[-1]
    pnl = (b['c'] / entry - 1.0) * 100.0
    if partial_done:
        pnl = partial_pnl + (1.0 - partial) * pnl
    return finish(row, b, 'OPEN_MARK', b['c'], pnl, len(path), best_h, worst_l, cfg, partial_reason)


def finish(row, b, reason, price, pnl, hold, best_h, worst_l, cfg, partial_reason):
    entry = fnum(row.get('entry_price') or row.get('price'))
    sl0 = fnum(row.get('sl') or row.get('sl_price'))
    risk = entry - sl0 if entry and sl0 else None
    return {
        'symbol': row.get('symbol'),
        'entry_date': dkey(row.get('entry_date')),
        'exit_date': b['date'],
        'exit_reason': reason,
        'exit_price': round(price, 4),
        'pnl_pct': round(pnl, 4),
        'hold_bars': hold,
        'mfe_pct': round((best_h / entry - 1.0) * 100.0, 4) if entry else None,
        'mae_pct': round((worst_l / entry - 1.0) * 100.0, 4) if entry else None,
        'mfe_r': round((best_h - entry) / risk, 4) if risk else None,
        'mae_r': round((worst_l - entry) / risk, 4) if risk else None,
        'same_day_exit_violation': b['date'] == dkey(row.get('entry_date')),
        'source_exit_reason': row.get('exit_reason'),
        'source_pnl_pct': fnum(row.get('pnl_pct')),
        'v185_source': row.get('v185_source'),
        'cfg': cfg['name'],
        'partial_reason': partial_reason,
    }


def metrics(rows):
    n = len(rows)
    if not n:
        return {'n': 0}
    pnls = [fnum(r.get('pnl_pct'), 0.0) for r in rows]
    years = defaultdict(list)
    for r, p in zip(rows, pnls):
        years[str(r.get('entry_date') or '')[:4]].append(p)
    year_counts = {y: len(v) for y, v in sorted(years.items()) if y}
    year_wr = {y: round(sum(p >= 0.8 for p in v) / len(v) * 100.0, 4) for y, v in sorted(years.items()) if y}
    return {
        'n': n,
        'wr': round(sum(p >= 0.8 for p in pnls) / n * 100.0, 4),
        'gross_wr': round(sum(p > 0 for p in pnls) / n * 100.0, 4),
        'avg': round(mean(pnls), 4),
        'median': round(median(pnls), 4),
        'loss_pct': round(sum(p < 0 for p in pnls) / n * 100.0, 4),
        'micro_profit_pct': round(sum(0 < p < 0.8 for p in pnls) / n * 100.0, 4),
        'min_year_n': min(year_counts.values()) if year_counts else 0,
        'year_counts': year_counts,
        'year_wr': year_wr,
        'all_year_wr_min': round(min(year_wr.values()), 4) if year_wr else 0,
        'same_day_exit_violations': sum(1 for r in rows if r.get('same_day_exit_violation')),
        'exit_counts': dict(Counter(r.get('exit_reason') for r in rows)),
    }


def gate(m):
    if m.get('same_day_exit_violations', 0):
        return 'FAIL_T1'
    ok = (
        m.get('n', 0) >= PRODUCTION_GATE['n_min'] and
        m.get('min_year_n', 0) >= PRODUCTION_GATE['min_year_n_min'] and
        m.get('wr', 0) >= PRODUCTION_GATE['wr_min'] and
        m.get('avg', 0) >= PRODUCTION_GATE['avg_min'] and
        m.get('all_year_wr_min', 0) >= PRODUCTION_GATE['year_wr_min'] and
        m.get('micro_profit_pct', 999) <= PRODUCTION_GATE['micro_max']
    )
    return 'PRODUCTION_PASS' if ok else 'FAIL'


def baseline_metrics(rows):
    sim_rows = []
    for r in rows:
        sim_rows.append({
            'entry_date': dkey(r.get('entry_date')),
            'exit_date': dkey(r.get('exit_date')),
            'exit_reason': r.get('exit_reason'),
            'pnl_pct': fnum(r.get('pnl_pct'), 0.0),
            'same_day_exit_violation': dkey(r.get('entry_date')) == dkey(r.get('exit_date')),
        })
    return metrics(sim_rows)


def loss_attribution(rows):
    losses = [r for r in rows if fnum(r.get('pnl_pct'), 0) < 0]
    buckets = Counter()
    examples = defaultdict(list)
    for r in losses:
        mfe_r = fnum(r.get('mfe_pct'), 0) / max(fnum(r.get('risk_pct'), 0.0001), 0.0001)
        mae_r = abs(fnum(r.get('mae_pct'), 0)) / max(fnum(r.get('risk_pct'), 0.0001), 0.0001)
        reason = r.get('exit_reason') or ''
        if mfe_r >= 1.0 and reason in ('TIME', 'RUNNER_TIME_CLOSE'):
            b = 'MFE_GE_1R_THEN_TIME_LOSS__EXIT_GIVEBACK_PROBLEM'
        elif mfe_r >= 0.5 and reason in ('TIME', 'RUNNER_TIME_CLOSE'):
            b = 'MFE_0P5_TO_1R_THEN_TIME_LOSS__WEAK_FOLLOW_THROUGH'
        elif reason in ('SL', 'GAP_SL') and mae_r >= 0.9:
            b = 'DIRECT_STOP__ENTRY_OR_SIGNAL_QUALITY_PROBLEM'
        elif reason in ('BE_SL', 'GAP_BE_SL'):
            b = 'BREAKEVEN_OR_GAP_BE_LOSS__RUNNER_PROTECTION_PROBLEM'
        else:
            b = 'OTHER_RESIDUAL_LOSS'
        buckets[b] += 1
        if len(examples[b]) < 8:
            examples[b].append({
                'symbol': r.get('symbol'), 'entry_date': r.get('entry_date'), 'exit_reason': reason,
                'pnl_pct': fnum(r.get('pnl_pct')), 'mfe_pct': fnum(r.get('mfe_pct')),
                'mae_pct': fnum(r.get('mae_pct')), 'risk_pct': fnum(r.get('risk_pct')),
                'v185_source': r.get('v185_source'), 'zone_width': fnum(r.get('v85_zone_width_pct')),
                'reclaim_close_pos': fnum(r.get('reclaim_close_pos')),
            })
    return {'loss_count': len(losses), 'bucket_counts': dict(buckets), 'examples': dict(examples)}


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    trades = json.load(open(TRADES))
    configs = []
    for r_tp in (1.0, 1.2, 1.5, 1.8, 2.0):
        for h in (5, 7, 10, 15):
            configs.append({'name': f'FULL_TP{r_tp}R_H{h}', 'r_tp': r_tp, 'max_hold': h})
            for be in (0.8, 1.0, 1.2):
                configs.append({'name': f'FULL_TP{r_tp}R_H{h}_BE{be}R', 'r_tp': r_tp, 'max_hold': h, 'be_trigger_r': be})
            for tr in (0.6, 0.8, 1.0):
                configs.append({'name': f'FULL_TP{r_tp}R_H{h}_TRAIL1R_{tr}R', 'r_tp': r_tp, 'max_hold': h, 'trail_trigger_r': 1.0, 'trail_r': tr})
    for h in (7, 10, 15):
        configs.extend([
            {'name': f'PART50_TP1P0_RUN2P0_H{h}_BE', 'r_tp': 1.0, 'runner_r_tp': 2.0, 'partial': 0.5, 'max_hold': h, 'be_trigger_r': 1.0},
            {'name': f'PART50_TP1P2_RUN2P5_H{h}_BE', 'r_tp': 1.2, 'runner_r_tp': 2.5, 'partial': 0.5, 'max_hold': h, 'be_trigger_r': 1.2},
            {'name': f'FULL_TP1P5_H{h}_EARLY3_IF_MFE_LT0P4R', 'r_tp': 1.5, 'max_hold': h, 'early_time_cut': 3, 'early_min_mfe_r': 0.4},
            {'name': f'FULL_TP1P5_H{h}_GIVEBACK0P8R', 'r_tp': 1.5, 'max_hold': h, 'giveback_cut': 0.8},
        ])

    base = baseline_metrics(trades)
    results = []
    rows_by_cfg = {}
    for cfg in configs:
        sim = [simulate(r, cfg) for r in trades]
        sim = [r for r in sim if r is not None]
        m = metrics(sim)
        m['gate_status'] = gate(m)
        m['config'] = cfg
        m['delta_vs_v185_wr'] = round(m.get('wr', 0) - base.get('wr', 0), 4)
        m['delta_vs_v185_avg'] = round(m.get('avg', 0) - base.get('avg', 0), 4)
        results.append(m)
        rows_by_cfg[cfg['name']] = sim

    ranked = sorted(results, key=lambda x: (x['gate_status'] == 'PRODUCTION_PASS', x['wr'], x['avg'], x['all_year_wr_min'], -x['micro_profit_pct']), reverse=True)
    pass_rows = [r for r in ranked if r['gate_status'] == 'PRODUCTION_PASS']
    best = ranked[0]
    best_rows = rows_by_cfg[best['config']['name']]

    # Compare best vs V185 at row level for honest mechanism attribution.
    paired = []
    by_key = {(r['symbol'], r['entry_date']): r for r in best_rows}
    for r in trades:
        key = (r.get('symbol'), dkey(r.get('entry_date')))
        b = by_key.get(key)
        if not b:
            continue
        paired.append({
            'symbol': r.get('symbol'), 'entry_date': dkey(r.get('entry_date')),
            'v185_exit': r.get('exit_reason'), 'v185_pnl': fnum(r.get('pnl_pct')),
            'v316_exit': b.get('exit_reason'), 'v316_pnl': b.get('pnl_pct'),
            'delta': round(fnum(b.get('pnl_pct'), 0) - fnum(r.get('pnl_pct'), 0), 4),
            'mfe_r': b.get('mfe_r'), 'mae_r': b.get('mae_r'), 'v185_source': r.get('v185_source'),
        })
    improved_losses = [p for p in paired if fnum(p['v185_pnl'], 0) < 0 and fnum(p['v316_pnl'], 0) >= 0.8]
    damaged_wins = [p for p in paired if fnum(p['v185_pnl'], 0) >= 0.8 and fnum(p['v316_pnl'], 0) < 0.8]

    report = {
        'version': 'V316_V185_EXIT_MECHANISM_FRONTIER_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True,
        'production_write': False,
        'frontend_write': False,
        'watchlist_write': False,
        'input': str(TRADES),
        'gates': PRODUCTION_GATE,
        'baseline_v185_materialized': base,
        'loss_attribution_v185': loss_attribution(trades),
        'coverage': {'trades': len(trades), 'configs_tested': len(configs), 'full_replay_configs': sum(1 for r in results if r.get('n') == len(trades))},
        'production_pass_count': len(pass_rows),
        'production_pass_top10': pass_rows[:10],
        'frontier_top30': ranked[:30],
        'best_config': best,
        'best_vs_v185_row_delta': {
            'improved_v185_losses_to_net_wins': len(improved_losses),
            'damaged_v185_net_wins_to_nonwins': len(damaged_wins),
            'top_improved_losses': sorted(improved_losses, key=lambda x: x['delta'], reverse=True)[:20],
            'top_damaged_wins': sorted(damaged_wins, key=lambda x: x['delta'])[:20],
            'delta_reason_counts': {f'{a}->{b}': n for (a, b), n in Counter((p['v185_exit'], p['v316_exit']) for p in paired).items()},
        },
        'decision': 'NO_EXIT_ONLY_PROMOTION__KEEP_V185' if not pass_rows else 'EXIT_ONLY_CANDIDATE_FOUND__REQUIRES_INDEPENDENT_SCANNER_SMOKE_BEFORE_PROMOTION',
        'artifacts': {
            'report': str(OUTDIR / 'v316_report.json'),
            'best_rows': str(OUTDIR / 'v316_best_rows.json'),
            'all_configs': str(OUTDIR / 'v316_all_configs.json'),
            'latest': str(LATEST),
        },
    }
    json.dump(report, open(OUTDIR / 'v316_report.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(best_rows, open(OUTDIR / 'v316_best_rows.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(results, open(OUTDIR / 'v316_all_configs.json', 'w'), ensure_ascii=False, indent=2)
    json.dump(report, open(LATEST, 'w'), ensure_ascii=False, indent=2)
    print(json.dumps({
        'latest': str(LATEST),
        'baseline': base,
        'coverage': report['coverage'],
        'production_pass_count': len(pass_rows),
        'decision': report['decision'],
        'best_config': best,
        'loss_buckets': report['loss_attribution_v185']['bucket_counts'],
        'best_delta': report['best_vs_v185_row_delta'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
