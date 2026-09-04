#!/usr/bin/env python3
"""V107 TRADEABLE_REGIME research audit.

Research-only. Does not write production/frontend/monitor files.
Builds an ex-ante market-state layer on top of V104 strict reclaim trades,
keeping the original V104 structural TP/SL exits unchanged.
"""
from __future__ import annotations

import bisect
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path('/root/.hermes')
TRADES_PATH = ROOT / 'smc_opt_v104_strict_reclaim' / 'v104_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT_DIR = ROOT / 'smc_audit'
OUT_JSON = OUT_DIR / 'v107_tradeable_regime_audit_20260619.json'
OUT_MD = OUT_DIR / 'v107_tradeable_regime_audit_20260619.md'

MIN_N_PRODUCTION = 100
PROMOTION_WR = 70.0
PROMOTION_STABLE_MONTHS = 12
PROMOTION_SL_MAX = 30.0


def f(x, default=0.0):
    try:
        if x is None or x == '':
            return default
        y = float(x)
        if math.isnan(y):
            return default
        return y
    except Exception:
        return default


def pct(a, b):
    return round(a * 100.0 / b, 4) if b else 0.0


def ymd_to_month(s):
    s = str(s or '')
    return s[:6] if len(s) >= 6 else 'UNKNOWN'


def load_trades():
    rows = json.loads(TRADES_PATH.read_text())
    rows = [r for r in rows if r.get('entry_date')]
    rows.sort(key=lambda r: (str(r.get('entry_date')), str(r.get('symbol'))))
    return rows


def load_kline_file(path: Path):
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return []
    out = []
    for r in rows:
        d = str(r.get('t') or r.get('date') or '')
        c = f(r.get('c'), None)
        if len(d) >= 8 and c and c > 0:
            out.append((d[:8], c))
    out.sort(key=lambda x: x[0])
    return out


def compute_full_market_stats(entry_dates):
    """Compute ex-ante full-universe breadth for each entry date.

    For each symbol, use the latest K-line at or before entry_date and only
    past closes for MA/returns; no future bars or trade outcome fields.
    """
    acc = {d: {'total': 0, 'up20': 0, 'up60': 0, 'ret20_pos': 0, 'ret60_pos': 0,
               'ret20_vals': [], 'ret60_vals': []} for d in entry_dates}
    dates = sorted(entry_dates)
    for i, path in enumerate(sorted(KLINE_DIR.glob('*_daily_300.json')), 1):
        ks = load_kline_file(path)
        if len(ks) < 80:
            continue
        kdates = [x[0] for x in ks]
        closes = [x[1] for x in ks]
        for d in dates:
            idx = bisect.bisect_right(kdates, d) - 1
            if idx < 60:
                continue
            c = closes[idx]
            ma20 = mean(closes[idx-19:idx+1])
            ma60 = mean(closes[idx-59:idx+1])
            ret20 = (c / closes[idx-20] - 1.0) * 100.0 if closes[idx-20] else 0.0
            ret60 = (c / closes[idx-60] - 1.0) * 100.0 if closes[idx-60] else 0.0
            a = acc[d]
            a['total'] += 1
            a['up20'] += int(c > ma20)
            a['up60'] += int(c > ma60)
            a['ret20_pos'] += int(ret20 > 0)
            a['ret60_pos'] += int(ret60 > 0)
            a['ret20_vals'].append(ret20)
            a['ret60_vals'].append(ret60)
    stats = {}
    for d, a in acc.items():
        total = a['total']
        stats[d] = {
            'total': total,
            'up20_pct': round(pct(a['up20'], total), 2),
            'up60_pct': round(pct(a['up60'], total), 2),
            'ret20_pos_pct': round(pct(a['ret20_pos'], total), 2),
            'ret60_pos_pct': round(pct(a['ret60_pos'], total), 2),
            'avg_ret20': round(mean(a['ret20_vals']), 4) if a['ret20_vals'] else 0.0,
            'avg_ret60': round(mean(a['ret60_vals']), 4) if a['ret60_vals'] else 0.0,
        }
    return stats


def classify_regime(m):
    up20 = f(m.get('up20_pct'))
    up60 = f(m.get('up60_pct'))
    avg20 = f(m.get('avg_ret20'))
    avg60 = f(m.get('avg_ret60'))
    pos20 = f(m.get('ret20_pos_pct'))
    if up20 >= 55 and up60 >= 50 and avg20 >= 3 and avg60 >= 0:
        return 'BULL_EXPANSION'
    if up20 >= 45 and up60 >= 40 and avg20 >= 1 and pos20 >= 55:
        return 'BULL_RECOVERY'
    if up20 >= 35 and up60 >= 30 and avg20 >= -2:
        return 'REPAIRABLE_RANGE'
    if up20 < 30 or avg20 < -4 or avg60 < -8:
        return 'NO_TRADE_BEAR_STRESS'
    return 'MIXED_CHOP'


def enrich(rows, market_stats):
    out = []
    for r in rows:
        rr = dict(r)
        m = market_stats.get(str(r.get('entry_date')), {})
        rr['market'] = m
        rr['tradeable_regime'] = classify_regime(m)
        rr['month'] = ymd_to_month(r.get('entry_date'))
        rr['year'] = str(r.get('entry_date'))[:4]
        out.append(rr)
    return out


def summarize(rows):
    n = len(rows)
    wins = sum(1 for r in rows if f(r.get('net_pnl_pct')) >= 0.8)
    gross_wins = sum(1 for r in rows if f(r.get('pnl_pct')) > 0)
    sl = sum(1 for r in rows if r.get('exit_reason') == 'SL_HIT')
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    by_month = defaultdict(list)
    by_year = defaultdict(list)
    for r in rows:
        by_month[r['month']].append(r)
        by_year[r['year']].append(r)
    stable3 = 0
    stable5 = 0
    month_rows = {}
    for m, rs in sorted(by_month.items()):
        s = summarize_shallow(rs)
        month_rows[m] = s
        if s['n'] >= 3 and s['wr'] >= 70 and s['sl'] <= 30:
            stable3 += 1
        if s['n'] >= 5 and s['wr'] >= 70 and s['sl'] <= 30:
            stable5 += 1
    return {
        'n': n,
        'wr': round(pct(wins, n), 2),
        'gross_wr': round(pct(gross_wins, n), 2),
        'sl': round(pct(sl, n), 2),
        'avg': round(mean(vals), 4) if vals else 0.0,
        'cum': round(sum(vals), 4),
        'months': len(by_month),
        'stable3': stable3,
        'stable5': stable5,
        'by_year': {y: summarize_shallow(rs) for y, rs in sorted(by_year.items())},
        'month_rows': month_rows,
    }


def summarize_shallow(rows):
    n = len(rows)
    vals = [f(r.get('net_pnl_pct')) for r in rows]
    return {
        'n': n,
        'wr': round(pct(sum(1 for r in rows if f(r.get('net_pnl_pct')) >= 0.8), n), 2),
        'sl': round(pct(sum(1 for r in rows if r.get('exit_reason') == 'SL_HIT'), n), 2),
        'avg': round(mean(vals), 4) if vals else 0.0,
    }


def pass_rule(r, rule):
    m = r.get('market', {})
    if r.get('tradeable_regime') not in rule['regimes']:
        return False
    if rule.get('family') != 'ANY' and r.get('family') != rule['family']:
        return False
    if rule.get('trend') != 'ANY' and r.get('trend_state') != rule['trend']:
        return False
    if f(r.get('risk_pct')) < rule['risk_lo'] or f(r.get('risk_pct')) > rule['risk_hi']:
        return False
    if f(r.get('retrace_pct')) < rule['retr_lo'] or f(r.get('retrace_pct')) > rule['retr_hi']:
        return False
    if f(r.get('chase_pct')) > rule['chase_hi']:
        return False
    if f(r.get('disp_atr')) < rule['disp_min']:
        return False
    if f(m.get('up20_pct')) < rule['up20_min']:
        return False
    if f(m.get('up60_pct')) < rule['up60_min']:
        return False
    if f(m.get('avg_ret20')) < rule['avg20_min']:
        return False
    if f(m.get('ret20_pos_pct')) < rule['pos20_min']:
        return False
    return True


def build_matrix(rows):
    # Keep the search deliberately compact: V106 already proved broad brute-force
    # TP/SL-style optimization is the wrong direction. V107 only tests a small
    # ex-ante market-state layer plus structural entry-quality ranges.
    regime_sets = [
        ('EXPANSION_ONLY', ['BULL_EXPANSION']),
        ('EXPANSION_RECOVERY', ['BULL_EXPANSION', 'BULL_RECOVERY']),
        ('TRADEABLE_ONLY', ['BULL_EXPANSION', 'BULL_RECOVERY', 'REPAIRABLE_RANGE']),
    ]
    retr_ranges = [(10, 50), (15, 45), (20, 40), (20, 50), (10, 40)]
    out = []
    for regime_name, regimes in regime_sets:
        for family in ['ANY', 'CONTINUATION']:
            for trend in ['ANY', 'UP_TREND', 'RANGE_TRANSITION']:
                for risk_lo in [0, 3]:
                    for risk_hi in [5, 8]:
                        if risk_lo >= risk_hi:
                            continue
                        for retr_lo, retr_hi in retr_ranges:
                            for chase_hi in [2, 4, 99]:
                                for disp_min in [0, 2]:
                                    for up20_min in [0, 35, 45, 55]:
                                        for up60_min in [0, 30, 40, 50]:
                                            for avg20_min in [-2, 0, 2, 3]:
                                                for pos20_min in [0, 55]:
                                                    rule = {
                                                        'regime_name': regime_name,
                                                        'regimes': regimes,
                                                        'family': family,
                                                        'trend': trend,
                                                        'risk_lo': risk_lo,
                                                        'risk_hi': risk_hi,
                                                        'retr_lo': retr_lo,
                                                        'retr_hi': retr_hi,
                                                        'chase_hi': chase_hi,
                                                        'disp_min': disp_min,
                                                        'up20_min': up20_min,
                                                        'up60_min': up60_min,
                                                        'avg20_min': avg20_min,
                                                        'pos20_min': pos20_min,
                                                    }
                                                    rs = [r for r in rows if pass_rule(r, rule)]
                                                    if len(rs) < 40:
                                                        continue
                                                    s = summarize(rs)
                                                    s2 = {k: v for k, v in s.items() if k != 'month_rows'}
                                                    s2['rule'] = rule
                                                    s2['production_pass'] = (
                                                        s['n'] >= MIN_N_PRODUCTION and
                                                        s['wr'] >= PROMOTION_WR and
                                                        s['sl'] <= PROMOTION_SL_MAX and
                                                        s['stable3'] >= PROMOTION_STABLE_MONTHS
                                                    )
                                                    out.append(s2)
    out.sort(key=lambda x: (x['production_pass'], x['stable3'], x['n'] >= MIN_N_PRODUCTION, x['wr'], -x['sl'], x['cum']), reverse=True)
    # de-duplicate near-identical result sets by rule signature and headline metrics.
    return out[:200]


def semantic_audit(rows):
    issues = Counter()
    for r in rows:
        if int(r.get('entry_idx', -1)) <= int(r.get('reclaim_idx', -1)):
            issues['entry_not_after_reclaim'] += 1
        if int(r.get('exit_idx', -1)) <= int(r.get('entry_idx', -1)):
            issues['exit_not_after_entry'] += 1
        if r.get('entry_date') == r.get('exit_date'):
            issues['same_day_exit'] += 1
        if f(r.get('entry_price')) <= f(r.get('zone_high')):
            issues['entry_not_above_zone_high'] += 1
    return {'fail_count': sum(issues.values()), 'issue_counts': dict(issues)}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_trades()
    entry_dates = sorted({str(r.get('entry_date')) for r in rows if r.get('entry_date')})
    market_stats = compute_full_market_stats(entry_dates)
    enriched = enrich(rows, market_stats)
    matrix = build_matrix(enriched)
    by_regime = {k: summarize([r for r in enriched if r['tradeable_regime'] == k])
                 for k in sorted({r['tradeable_regime'] for r in enriched})}
    baseline = summarize(enriched)
    semantic = semantic_audit(enriched)
    best = matrix[0] if matrix else None
    decision = 'PROMOTE_CANDIDATE' if best and best['production_pass'] and semantic['fail_count'] == 0 else 'RESEARCH_ONLY_NOT_PROMOTED'
    result = {
        'version': 'V107_TRADEABLE_REGIME_AUDIT',
        'input': str(TRADES_PATH),
        'kline_dir': str(KLINE_DIR),
        'research_only': True,
        'production_files_touched': False,
        'structural_exit_unchanged_from_v104': True,
        'micro_tp_used': False,
        'promotion_thresholds': {
            'min_n': MIN_N_PRODUCTION,
            'wr_ge': PROMOTION_WR,
            'sl_lte': PROMOTION_SL_MAX,
            'stable3_months_ge': PROMOTION_STABLE_MONTHS,
        },
        'semantic_audit': semantic,
        'baseline': {k: v for k, v in baseline.items() if k != 'month_rows'},
        'by_regime': {k: {kk: vv for kk, vv in v.items() if kk != 'month_rows'} for k, v in by_regime.items()},
        'top_rules': matrix[:30],
        'best_rule': best,
        'decision': decision,
        'non_promotion_reasons': [] if decision == 'PROMOTE_CANDIDATE' else [
            'No V107 rule simultaneously satisfied n>=100, WR>=70%, SL<=30%, stable3_months>=12 under unchanged V104 structural TP/SL.' if not any(x.get('production_pass') for x in matrix) else 'Semantic gate failed.',
            'Research artifact only; not connected to production/API/frontend.',
        ],
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    lines = []
    lines.append('# V107 TRADEABLE_REGIME Audit (research-only)')
    lines.append('')
    lines.append(f"Decision: **{decision}**")
    lines.append('')
    lines.append('| Layer | n | WR>=0.8 | SL | Avg net | Months | Stable3 | Stable5 |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|---:|')
    b = baseline
    lines.append(f"| V104 baseline | {b['n']} | {b['wr']}% | {b['sl']}% | {b['avg']}% | {b['months']} | {b['stable3']} | {b['stable5']} |")
    for name, s in by_regime.items():
        lines.append(f"| {name} | {s['n']} | {s['wr']}% | {s['sl']}% | {s['avg']}% | {s['months']} | {s['stable3']} | {s['stable5']} |")
    lines.append('')
    lines.append('## Top rules')
    lines.append('| Rank | Regime | n | WR | SL | Avg | Months | Stable3 | Stable5 | Rule |')
    lines.append('|---:|---|---:|---:|---:|---:|---:|---:|---:|---|')
    for i, x in enumerate(matrix[:10], 1):
        r = x['rule']
        rule_txt = f"family={r['family']}, trend={r['trend']}, risk={r['risk_lo']}-{r['risk_hi']}, retr={r['retr_lo']}-{r['retr_hi']}, chase<={r['chase_hi']}, disp>={r['disp_min']}, up20>={r['up20_min']}, up60>={r['up60_min']}, avg20>={r['avg20_min']}, pos20>={r['pos20_min']}"
        lines.append(f"| {i} | {r['regime_name']} | {x['n']} | {x['wr']}% | {x['sl']}% | {x['avg']}% | {x['months']} | {x['stable3']} | {x['stable5']} | {rule_txt} |")
    OUT_MD.write_text('\n'.join(lines) + '\n')
    print(json.dumps({
        'out_json': str(OUT_JSON),
        'out_md': str(OUT_MD),
        'decision': decision,
        'semantic_audit': semantic,
        'baseline': {k: v for k, v in baseline.items() if k != 'month_rows'},
        'best_rule': best,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
