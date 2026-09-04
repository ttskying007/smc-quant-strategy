#!/usr/bin/env python3
"""
V28 SMC Diagnostics — Cohort Analysis + Root Cause Attribution + Auto-Fix
═══════════════════════════════════════════════════════════════════════════
Analyzes V28 trades to:

1. Auto-find WORST cohorts (by exit reason, market state, zone type, grade)
2. Auto-find BEST cohorts
3. Auto-find high-SL-rate groups
4. Auto-find high-RR groups
5. Auto-generate fix suggestions
6. Output diagnostics JSON for frontend display

Run: python3 smc_diagnostics_v28.py
"""

import json, sys, math
from pathlib import Path
from collections import defaultdict, Counter
from typing import List, Dict
sys.path.insert(0, '/root/.hermes/scripts/v25')

OUT_DIR = Path('/root/.hermes/smc_opt_v28')


def exit_key(t_or_reason):
    """Canonical exit reason for mixed V25-V29 outputs."""
    reason = t_or_reason.get('exit_reason', 'UNKNOWN') if isinstance(t_or_reason, dict) else t_or_reason
    r = str(reason or 'UNKNOWN').strip().upper()
    aliases = {
        'SL_HIT': 'SL_HIT', 'STOP_LOSS': 'SL_HIT',
        'TP_HIT': 'TP_HIT', 'TP1_HIT': 'TP1_HIT', 'TP2_HIT': 'TP2_HIT', 'TP3_HIT': 'TP3_HIT',
        'TP1': 'TP1_HIT', 'TP2': 'TP2_HIT', 'TP3': 'TP3_HIT',
        'TRAILING': 'TRAILING_STOP', 'TRAILING_STOP': 'TRAILING_STOP', 'RUNNER_TRAIL': 'TRAILING_STOP',
        'TIMEOUT': 'TIMEOUT', 'TIME_STOP': 'TIMEOUT', 'TIMEOUT_PARTIAL': 'TIMEOUT_PARTIAL',
        'MULTI_EXIT': 'MULTI_EXIT',
    }
    return aliases.get(r, r)


def load_v28_data():
    """Load V28 trades, picks, metrics."""
    trades, picks, metrics = [], [], {}
    for name, var in [('v28_trades.json', 'trades'), ('v28_picks.json', 'picks'), ('v28_metrics.json', 'metrics')]:
        f = OUT_DIR / name
        if f.exists():
            try:
                data = json.loads(f.read_text())
                if var == 'trades': trades = data
                elif var == 'picks': picks = data
                else: metrics = data
            except Exception as e:
                print(f"WARN: failed to load {name}: {e}")
    return trades, picks, metrics


def cohort_by_exit_reason(trades: List[Dict]) -> Dict:
    """Worst cohorts by exit reason."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'total_pnl': 0.0, 'examples': []})
    for t in trades:
        reason = exit_key(t)
        g = groups[reason]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        if pnl > 0: g['won'] += 1
        g['total_pnl'] += pnl
        if len(g['examples']) < 3:
            g['examples'].append(f"{t.get('symbol','')} {t.get('zone_type','')} {t.get('entry_date','')} {pnl:+.1f}%")

    result = []
    for reason, g in sorted(groups.items(), key=lambda x: x[1]['total_pnl']):
        n = g['n']
        wr = g['won'] / max(n, 1) * 100
        avg_pnl = g['total_pnl'] / max(n, 1)
        result.append({
            'cohort': reason, 'type': 'exit_reason',
            'n_trades': n, 'wr': round(wr, 1), 'avg_pnl': round(avg_pnl, 2),
            'total_pnl': round(g['total_pnl'], 2), 'examples': g['examples'][:3],
            'severity': 'HIGH' if avg_pnl < -1.0 else 'MEDIUM' if avg_pnl < 0 else 'LOW',
        })
    return result


def cohort_by_market_state(trades: List[Dict]) -> Dict:
    """Performance by market state."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'total_pnl': 0.0, 'sl_hits': 0})
    for t in trades:
        ms = t.get('market_state', 'UNKNOWN')
        g = groups[ms]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        if pnl > 0: g['won'] += 1
        g['total_pnl'] += pnl
        if exit_key(t) == 'SL_HIT' and pnl < 0:
            g['sl_hits'] += 1

    result = []
    for ms, g in sorted(groups.items(), key=lambda x: x[1]['total_pnl']):
        n = g['n']
        wr = g['won'] / max(n, 1) * 100
        sl_rate = g['sl_hits'] / max(n, 1) * 100
        avg_pnl = g['total_pnl'] / max(n, 1)
        result.append({
            'cohort': ms, 'type': 'market_state',
            'n_trades': n, 'wr': round(wr, 1), 'sl_rate': round(sl_rate, 1),
            'avg_pnl': round(avg_pnl, 2), 'total_pnl': round(g['total_pnl'], 2),
            'severity': 'HIGH' if sl_rate > 40 else 'MEDIUM' if sl_rate > 25 else 'LOW',
            'fix': 'SKIP' if ms == 'RANGE' and sl_rate > 30 else 'FILTER' if sl_rate > 35 else 'OK',
        })
    return result


def cohort_by_zone_type(trades: List[Dict]) -> Dict:
    """Performance by zone type (OB/OTE/BPR)."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'total_pnl': 0.0})
    for t in trades:
        zt = t.get('zone_type', 'UNKNOWN')
        g = groups[zt]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        if pnl > 0: g['won'] += 1
        g['total_pnl'] += pnl
    result = []
    for zt, g in sorted(groups.items(), key=lambda x: x[1]['total_pnl']):
        n = g['n']
        wr = g['won'] / max(n, 1) * 100
        avg_pnl = g['total_pnl'] / max(n, 1)
        result.append({'cohort': zt, 'type': 'zone_type', 'n_trades': n,
                       'wr': round(wr, 1), 'avg_pnl': round(avg_pnl, 2),
                       'total_pnl': round(g['total_pnl'], 2)})
    return result


def cohort_by_quality_grade(trades: List[Dict]) -> Dict:
    """Performance by signal quality grades."""
    grades = ['ob_grade', 'structure', 'cost_proximity']
    results = {}
    for grade_field in grades:
        groups = defaultdict(lambda: {'n': 0, 'won': 0, 'total_pnl': 0.0})
        for t in trades:
            gv = t.get(grade_field, 'UNKNOWN')
            grp = groups[gv]
            grp['n'] += 1
            pnl = float(t.get('pnl_pct', 0))
            if pnl > 0: grp['won'] += 1
            grp['total_pnl'] += pnl
        items = []
        for gv, grp in sorted(groups.items(), key=lambda x: x[1]['total_pnl']):
            n = grp['n']
            wr = grp['won'] / max(n, 1) * 100
            avg_pnl = grp['total_pnl'] / max(n, 1)
            items.append({'grade': gv, 'n_trades': n, 'wr': round(wr, 1),
                          'avg_pnl': round(avg_pnl, 2), 'total_pnl': round(grp['total_pnl'], 2)})
        results[grade_field] = items
    return results


def cohort_by_resonance(trades: List[Dict]) -> Dict:
    """Performance by MTF resonance alignment."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'total_pnl': 0.0})
    for t in trades:
        res = t.get('resonance', 'UNKNOWN')
        g = groups[res]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        if pnl > 0: g['won'] += 1
        g['total_pnl'] += pnl
    result = []
    for res, g in sorted(groups.items(), key=lambda x: x[1]['total_pnl']):
        n = g['n']
        wr = g['won'] / max(n, 1) * 100
        avg_pnl = g['total_pnl'] / max(n, 1)
        result.append({'cohort': res, 'type': 'resonance', 'n_trades': n,
                       'wr': round(wr, 1), 'avg_pnl': round(avg_pnl, 2),
                       'total_pnl': round(g['total_pnl'], 2)})
    return result


def find_high_sl_groups(trades: List[Dict]) -> List[Dict]:
    """Find clusters with abnormally high SL rate."""
    # Group by (market_state, zone_type, resonance)
    groups = defaultdict(lambda: {'n': 0, 'sl': 0, 'total_pnl': 0.0, 'symbols': set()})
    for t in trades:
        key = f"{t.get('market_state','')}|{t.get('zone_type','')}|{t.get('resonance','')}|{t.get('ob_grade','')}|{t.get('structure','')}"
        g = groups[key]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        if exit_key(t) == 'SL_HIT' and pnl < 0:
            g['sl'] += 1
        g['total_pnl'] += pnl
        if g['n'] <= 20 and t.get('symbol'):
            g['symbols'].add(t.get('symbol'))

    high_sl = []
    for key, g in groups.items():
        if g['n'] < 5: continue
        sl_rate = g['sl'] / max(g['n'], 1) * 100
        if sl_rate > 35:
            avg_pnl = g['total_pnl'] / max(g['n'], 1)
            high_sl.append({'group': key, 'n_trades': g['n'], 'sl_hits': g['sl'],
                           'sl_rate': round(sl_rate, 1), 'avg_pnl': round(avg_pnl, 2),
                           'sample_symbols': list(g['symbols'])[:5]})
    return sorted(high_sl, key=lambda x: -x['sl_rate'])


def find_high_rr_groups(trades: List[Dict]) -> List[Dict]:
    """Find clusters with highest RR."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'sl': 0, 'total_rr': 0.0, 'total_pnl': 0.0})
    for t in trades:
        key = f"{t.get('zone_type','')}|{t.get('ob_grade','')}|{t.get('resonance','')}|{t.get('market_state','')}"
        g = groups[key]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        rr = float(t.get('rr', 0) or 0)
        g['total_rr'] += rr
        g['total_pnl'] += pnl
        if pnl > 0: g['won'] += 1
        if exit_key(t) == 'SL_HIT' and pnl < 0: g['sl'] += 1

    high_rr = []
    for key, g in groups.items():
        if g['n'] < 5: continue
        avg_rr = g['total_rr'] / max(g['n'], 1)
        wr = g['won'] / max(g['n'], 1) * 100
        sl_rate = g['sl'] / max(g['n'], 1) * 100
        avg_pnl = g['total_pnl'] / max(g['n'], 1)
        high_rr.append({'group': key, 'n_trades': g['n'],
                       'avg_rr': round(avg_rr, 2), 'wr': round(wr, 1),
                       'sl_rate': round(sl_rate, 1), 'avg_pnl': round(avg_pnl, 2)})
    return sorted(high_rr, key=lambda x: -x['avg_rr'])[:15]


# ═══ SIGNAL RANKING ANALYSIS ═══

def _group_stats(trades, group_key_fn, min_n=3):
    """Generic grouper: compute WR, SL rate, avg PnL, quality, top state, etc."""
    groups = defaultdict(lambda: {'n': 0, 'won': 0, 'sl': 0, 'total_pnl': 0.0,
                                   'total_quality': 0.0, 'total_hold': 0,
                                   'market_states': defaultdict(int),
                                   'exit_reasons': defaultdict(int)})
    for t in trades:
        key = group_key_fn(t)
        if not key: continue
        g = groups[key]
        g['n'] += 1
        pnl = float(t.get('pnl_pct', 0))
        g['total_pnl'] += pnl
        g['total_quality'] += float(t.get('quality_score', 0) or 0)
        g['total_hold'] += t.get('hold_bars', 0)
        if pnl > 0: g['won'] += 1
        if exit_key(t) == 'SL_HIT' and pnl < 0: g['sl'] += 1
        g['market_states'][t.get('market_state', '?')] += 1
        g['exit_reasons'][exit_key(t)] += 1

    results = []
    for key, g in groups.items():
        if g['n'] < min_n: continue
        n = g['n']
        top_state = max(g['market_states'].items(), key=lambda x: x[1])[0] if g['market_states'] else '?'
        top_exit = max(g['exit_reasons'].items(), key=lambda x: x[1])[0] if g['exit_reasons'] else '?'
        results.append({
            'group': key, 'n': n,
            'wr': round(g['won'] / n * 100, 1),
            'sl_rate': round(g['sl'] / n * 100, 1),
            'avg_pnl': round(g['total_pnl'] / n, 2),
            'total_pnl': round(g['total_pnl'], 1),
            'avg_quality': round(g['total_quality'] / n, 2),
            'avg_hold': round(g['total_hold'] / n, 1),
            'top_state': top_state, 'top_exit': top_exit,
        })
    return sorted(results, key=lambda x: x['total_pnl'])


def signal_ranking(trades):
    """Comprehensive signal ranking by ctx_seq, zone×conf, grade, resonance, market."""
    return {
        'by_ctx_seq': _group_stats(trades, lambda t: t.get('ctx_seq', ''), min_n=10),
        'by_zone_conf': _group_stats(trades, lambda t: f"{t.get('zone_type','')}×{t.get('conf_type','')}", min_n=5),
        'by_ob_grade': _group_stats(trades, lambda t: f"{t.get('zone_type','')}×{t.get('ob_grade','?')}", min_n=5),
        'by_ote_grade': _group_stats(trades, lambda t: f"{t.get('zone_type','')}×{t.get('ote_grade','?')}", min_n=5),
        'by_resonance_zone': _group_stats(trades, lambda t: f"{t.get('resonance','')}×{t.get('zone_type','')}", min_n=5),
        'by_market_conf': _group_stats(trades, lambda t: f"{t.get('market_state','')}×{t.get('conf_type','')}", min_n=5),
        'by_structure': _group_stats(trades, lambda t: f"{t.get('structure','')}×{t.get('zone_type','')}", min_n=5),
        'by_weekly': _group_stats(trades, lambda t: f"{t.get('weekly','')}×{t.get('zone_type','')}", min_n=5),
    }


def signal_failure_attribution(trades):
    """Root cause analysis: why do certain signal groups fail?"""
    attributions = []
    all_by_seq = _group_stats(trades, lambda t: t.get('ctx_seq', ''), min_n=10)

    # Find worst 5 groups by WR
    worst = sorted(all_by_seq, key=lambda x: x['wr'])[:5]
    for r in worst:
        # Get the trades for this group
        group_trades = [t for t in trades if t.get('ctx_seq', '') == r['group']]
        if len(group_trades) < 5: continue

        # Analyze SL reason distribution
        sl_reasons = defaultdict(int)
        for t in group_trades:
            if float(t.get('pnl_pct', 0)) < 0:
                sl_reasons[exit_key(t)] += 1
        top_sl_reason = max(sl_reasons.items(), key=lambda x: x[1])[0] if sl_reasons else 'N/A'

        # Market state distribution
        states = defaultdict(int)
        for t in group_trades:
            states[t.get('market_state', '?')] += 1

        # Average quality and hold
        avg_q = sum(float(t.get('quality_score', 0)) for t in group_trades) / len(group_trades)
        avg_hold = sum(t.get('hold_bars', 0) for t in group_trades) / len(group_trades)

        # Attribution
        causes = []
        if r['sl_rate'] > 30:
            causes.append(f'高SL率({r["sl_rate"]:.0f}%)—{top_sl_reason}主导')
        if r['wr'] < 55:
            causes.append(f'低胜率({r["wr"]:.0f}%)')
        if avg_q < 6.0:
            causes.append(f'低质量(Q={avg_q:.1f})')
        if avg_hold < 3:
            causes.append(f'持仓短({avg_hold:.0f}bar)')
        # Check if dominated by bad market state
        bad_states = sum(states.get(s, 0) for s in ['RANGE', 'TREND_DOWN', 'CONFLICT'])
        if bad_states / max(len(group_trades), 1) > 0.4:
            causes.append(f'{bad_states}/{len(group_trades)}笔在不利状态')
        if not causes:
            causes.append('整体表现尚可—SL率偏高是主要损耗')

        attributions.append({
            'group': r['group'], 'n': r['n'], 'wr': r['wr'],
            'sl_rate': r['sl_rate'], 'avg_pnl': r['avg_pnl'],
            'top_sl_reason': top_sl_reason, 'avg_quality': round(avg_q, 2),
            'avg_hold': round(avg_hold, 1),
            'causes': causes,
            'severity': 'CRITICAL' if r['wr'] < 50 else 'HIGH' if r['wr'] < 60 else 'MEDIUM',
        })

    # Also check worst resonance groups
    by_res = _group_stats(trades, lambda t: t.get('resonance', ''), min_n=10)
    worst_res = sorted(by_res, key=lambda x: x['wr'])[:5]
    for r in worst_res:
        if r['group'] == 'CONFLICT':
            causes = ['共振失效—周线/日线方向冲突，必须过滤']
            sev = 'CRITICAL'
        elif r['group'] == 'PARTIAL':
            causes = ['共振不足—部分对齐但不够强，可提高过滤阈值']
            sev = 'MEDIUM'
        elif r['wr'] < 55:
            causes = [f'低胜率共振({r["wr"]}%)']
            sev = 'HIGH'
        else:
            continue  # Skip healthy resonance groups
        attributions.append({
            'group': f"共振:{r['group']}", 'n': r['n'], 'wr': r['wr'],
            'sl_rate': r['sl_rate'], 'avg_pnl': r['avg_pnl'],
            'top_sl_reason': r['top_exit'], 'avg_quality': r['avg_quality'],
            'avg_hold': r['avg_hold'],
            'causes': causes,
            'severity': sev,
        })

    return attributions


def generate_fix_suggestions(trades: List[Dict]) -> List[Dict]:
    """Auto-generate fix suggestions based on diagnostics."""
    suggestions = []
    n = len(trades)
    if n == 0: return suggestions

    sl_rate = sum(1 for t in trades if exit_key(t) == 'SL_HIT' and float(t.get('pnl_pct', 0)) < 0) / max(n, 1) * 100
    timeout_rate = sum(1 for t in trades if exit_key(t) == 'TIMEOUT') / max(n, 1) * 100
    range_pnl = sum(float(t.get('pnl_pct', 0)) for t in trades if t.get('market_state') == 'RANGE')
    range_n = sum(1 for t in trades if t.get('market_state') == 'RANGE')
    bpr_trades = [t for t in trades if t.get('zone_type') == 'BPR']
    bpr_pnl = sum(float(t.get('pnl_pct', 0)) for t in bpr_trades)
    conflict_trades = [t for t in trades if t.get('resonance') == 'CONFLICT']
    conflict_pnl = sum(float(t.get('pnl_pct', 0)) for t in conflict_trades)

    wr = sum(1 for t in trades if float(t.get('pnl_pct', 0)) > 0) / max(n, 1) * 100

    # SL rate too high
    if sl_rate > 35:
        suggestions.append({
            'priority': 'CRITICAL', 'category': 'stop_loss',
            'issue': f'SL rate {sl_rate:.1f}% too high',
            'fix': 'SL可能太紧。增大SL缓冲(ATR×0.35→0.45)，使用swing SL而非ATR SL。',
            'impact': f'Expected improvement: WR +{min(10, sl_rate - 25):.0f}%'})

    # RANGE state losing
    if range_n > 0:
        range_wr = sum(1 for t in trades if t.get('market_state') == 'RANGE' and float(t.get('pnl_pct', 0)) > 0) / max(range_n, 1) * 100
        if range_wr < 40:
            suggestions.append({
                'priority': 'HIGH', 'category': 'market_state_filter',
                'issue': f'RANGE state WR={range_wr:.1f}% ({range_n} trades)',
                'fix': '全部跳过RANGE市场状态(已知低胜率)。在enhance_setups中range_skip=True。',
                'impact': f'Skip {range_n} trades, save {abs(range_pnl):.1f}% drawdown'})

    # BPR losing
    if len(bpr_trades) > 5:
        bpr_wr = sum(1 for t in bpr_trades if float(t.get('pnl_pct', 0)) > 0) / max(len(bpr_trades), 1) * 100
        if bpr_wr < 45:
            suggestions.append({
                'priority': 'HIGH', 'category': 'zone_type_filter',
                'issue': f'BPR WR={bpr_wr:.1f}% ({len(bpr_trades)} trades)',
                'fix': 'BPR仅在HIGH_TRUST+PNBAR确认时保留，当前quality threshold可提高到8.5。',
                'impact': f'Remove weak BPR, expected WR improvement +5-8%'})

    # CONFLICT resonance losing
    if len(conflict_trades) > 5 and conflict_pnl < 0:
        suggestions.append({
            'priority': 'MEDIUM', 'category': 'resonance_filter',
            'issue': f'CONFLICT resonance PnL={conflict_pnl:.1f}% ({len(conflict_trades)} trades)',
            'fix': 'CONFLICT信号已在输出过滤，确认前端不再展示。',
            'impact': 'Already filtered in V28 output.'})

    # Timeout too high — trailing too loose
    if timeout_rate > 50:
        suggestions.append({
            'priority': 'MEDIUM', 'category': 'trailing',
            'issue': f'Timeout rate {timeout_rate:.1f}% — trailing可能太松',
            'fix': '收紧trail_lock: 0.35R→0.30R (RANGE), 0.50R→0.45R (TREND_DOWN)',
            'impact': 'More trades close on trail instead of timeout'})

    # Low quality filtering
    avg_q = sum(float(t.get('quality_score', 0)) for t in trades) / max(n, 1)
    if avg_q < 6.0:
        suggestions.append({
            'priority': 'MEDIUM', 'category': 'quality_threshold',
            'issue': f'Average quality score {avg_q:.2f} — too low',
            'fix': '提高MIN_QUALITY从5.5到6.5, 减少低质量信号。',
            'impact': f'Fewer trades, higher WR. Current WR={wr:.1f}%'})

    # Overall metrics
    if wr < 55:
        suggestions.append({
            'priority': 'CRITICAL', 'category': 'overall',
            'issue': f'Overall WR={wr:.1f}% — system needs recalibration',
            'fix': '应用所有上述修复 + 重新全量扫描。检查OB检测逻辑。',
            'impact': 'System-wide review needed'})

    return suggestions


def write_diagnostics_report(trades: List[Dict], picks: List[Dict], metrics: Dict) -> Dict:
    """Generate complete diagnostics report."""
    report = {
        'generated_at': __import__('time').strftime('%Y-%m-%d %H:%M:%S'),
        'overview': {
            'n_trades': len(trades),
            'n_picks': len(picks),
            'n_won': sum(1 for t in trades if float(t.get('pnl_pct', 0)) > 0),
            'total_pnl': round(sum(float(t.get('pnl_pct', 0)) for t in trades), 2),
            'avg_pnl': round(sum(float(t.get('pnl_pct', 0)) for t in trades) / max(len(trades), 1), 2),
            'wr': round(sum(1 for t in trades if float(t.get('pnl_pct', 0)) > 0) / max(len(trades), 1) * 100, 1),
            'avg_hold_bars': round(sum(t.get('hold_bars', 0) for t in trades) / max(len(trades), 1), 1),
            'avg_quality': round(sum(float(t.get('quality_score', 0)) for t in trades) / max(len(trades), 1), 2),
        },
        'cohorts': {
            'by_exit_reason': cohort_by_exit_reason(trades),
            'by_market_state': cohort_by_market_state(trades),
            'by_zone_type': cohort_by_zone_type(trades),
            'by_quality_grade': cohort_by_quality_grade(trades),
            'by_resonance': cohort_by_resonance(trades),
        },
        'anomalies': {
            'high_sl_groups': find_high_sl_groups(trades),
            'high_rr_groups': find_high_rr_groups(trades),
        },
        'fix_suggestions': generate_fix_suggestions(trades),
        'summary': ' '.join([
            f"T={len(trades)}",
            f"WR={trades and round(sum(1 for t in trades if float(t.get('pnl_pct',0))>0)/max(len(trades),1)*100,1)}%",
            f"PnL={round(sum(float(t.get('pnl_pct',0)) for t in trades),1)}%",
            f"Q={trades and round(sum(float(t.get('quality_score',0)) for t in trades)/max(len(trades),1),1)}"
        ]),
    }
    return report


def main():
    trades, picks, metrics = load_v28_data()
    if not trades:
        print("ERROR: No V28 trades found. Run v28_full_scan.py first.")
        sys.exit(1)

    report = write_diagnostics_report(trades, picks, metrics)
    # Add new signal ranking analysis
    ranking = signal_ranking(trades)
    report['signal_ranking'] = ranking
    report['failure_attribution'] = signal_failure_attribution(trades)
    outf = OUT_DIR / 'v28_diagnostics.json'
    outf.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Diagnostics written to {outf}")

    summary = report['summary']
    print(f"\n=== V28 DIAGNOSTICS ===")
    print(summary)
    print(f"\nTop fix suggestions:")
    for s in report['fix_suggestions'][:5]:
        print(f"  [{s['priority']}] {s['issue']} → {s['fix'][:80]}...")
    print(f"\nWorst cohorts:")
    for c in report['cohorts']['by_exit_reason'][:3]:
        if c['severity'] in ('HIGH', 'MEDIUM'):
            print(f"  {c['cohort']}: WR={c['wr']}% PnL={c['total_pnl']:.1f}% ({c['n_trades']}t) [{c['severity']}]")
    for c in report['cohorts']['by_market_state'][:3]:
        if c.get('severity') in ('HIGH', 'MEDIUM'):
            print(f"  {c['cohort']}: WR={c['wr']}% SL={c.get('sl_rate',0)}% ({c['n_trades']}t) [{c.get('fix','')}]")

    return report


if __name__ == '__main__':
    main()
