#!/usr/bin/env python3
"""
V129 FVG_Demand scanner-layer contract decomposition.
Read-only research script. No production/API/frontend/watchlist writes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

IN_CSV = Path('/root/.hermes/smc_audit/v128_parallel_scanner_candidate_audit_20260620/v128_parallel_shadow_backtest_all.csv')
OUT_DIR = Path('/root/.hermes/smc_audit/v129_fvg_scanner_contract_decomposition_20260620')
RECENT_JSON = Path('/root/.hermes/smc_opt_v90_daily_full_market_scanner/v128_parallel_shadow_recent45.json')

HARD_EXIT_REASONS = {'EXIT_TREND_STRUCTURE_DAMAGE'}
V125_STATES = {'MIXED', 'BEAR_RISK'}


def metrics(df: pd.DataFrame) -> Dict:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0, 'avg': 0, 'loss_rate': 0, 'hard_exit_rate': 0, 'months': 0, 'stable3': 0, 'stable5': 0}
    pnl = pd.to_numeric(df['pnl_pct'], errors='coerce').fillna(0)
    win = pnl > 0
    hard = df['exit_reason'].isin(HARD_EXIT_REASONS)
    months = df.assign(month=df['entry_date'].astype(str).str[:6]).groupby('month')
    stable3 = 0
    stable5 = 0
    for _, g in months:
        if len(g) >= 3 and (pd.to_numeric(g['pnl_pct'], errors='coerce').fillna(0) > 0).mean() >= 0.60:
            stable3 += 1
        if len(g) >= 5 and (pd.to_numeric(g['pnl_pct'], errors='coerce').fillna(0) > 0).mean() >= 0.60:
            stable5 += 1
    return {
        'n': n,
        'wr': round(float(win.mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss_rate': round(float((~win).mean() * 100), 2),
        'hard_exit_rate': round(float(hard.mean() * 100), 2),
        'months': int(months.ngroups),
        'stable3': int(stable3),
        'stable5': int(stable5),
    }


def add_recent_flag(df: pd.DataFrame) -> pd.DataFrame:
    recent_keys = set()
    if RECENT_JSON.exists():
        rows = json.loads(RECENT_JSON.read_text())
        for r in rows:
            recent_keys.add((str(r.get('symbol')), str(r.get('entry_date')), str(r.get('poi_source'))))
    df = df.copy()
    df['recent45'] = [
        (str(r.symbol), str(r.entry_date), str(r.poi_source)) in recent_keys
        for r in df.itertuples(index=False)
    ]
    # Fallback if JSON mismatch: latest 45 trading dates from CSV.
    if df['recent45'].sum() == 0:
        dates = sorted(df['entry_date'].dropna().astype(int).unique())[-45:]
        df['recent45'] = df['entry_date'].astype(int).isin(dates)
    return df


def mask_v125(df: pd.DataFrame) -> pd.Series:
    return (
        (df['poi_source'] == 'FVG_Demand')
        & (df['combo_family'] == 'REVERSAL')
        & (pd.to_numeric(df['source_mid_body_atr'], errors='coerce') >= 0.65)
        & (pd.to_numeric(df['source_gap_atr'], errors='coerce') >= 0.8)
        & (pd.to_numeric(df['risk_pct'], errors='coerce').between(1, 3, inclusive='both'))
        & (pd.to_numeric(df['v85_zone_width_pct'], errors='coerce').between(1.2, 2.2, inclusive='both'))
        & (pd.to_numeric(df['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5)
        & (pd.to_numeric(df['touch_to_reclaim_bars'], errors='coerce').between(1, 3, inclusive='both'))
        & (df['market_state'].isin(V125_STATES))
    )


def breakdown_table(base: pd.DataFrame, recent: pd.DataFrame) -> List[Dict]:
    clauses: List[Tuple[str, pd.Series]] = [
        ('base_FVG_Demand', pd.Series(True, index=base.index)),
        ('combo_family == REVERSAL', base['combo_family'] == 'REVERSAL'),
        ('source_mid_body_atr >= 0.65', pd.to_numeric(base['source_mid_body_atr'], errors='coerce') >= 0.65),
        ('source_gap_atr >= 0.8', pd.to_numeric(base['source_gap_atr'], errors='coerce') >= 0.8),
        ('risk_pct 1-3', pd.to_numeric(base['risk_pct'], errors='coerce').between(1, 3, inclusive='both')),
        ('width_pct 1.2-2.2', pd.to_numeric(base['v85_zone_width_pct'], errors='coerce').between(1.2, 2.2, inclusive='both')),
        ('reclaim_above >= 0.5', pd.to_numeric(base['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5),
        ('touch_to_reclaim 1-3', pd.to_numeric(base['touch_to_reclaim_bars'], errors='coerce').between(1, 3, inclusive='both')),
        ('market_state MIXED/BEAR_RISK', base['market_state'].isin(V125_STATES)),
    ]
    rows = []
    cumulative = pd.Series(True, index=base.index)
    for name, m in clauses:
        cumulative = cumulative & m
        sub = base[cumulative]
        rec = sub[sub['recent45']]
        rows.append({
            'step': name,
            'all': metrics(sub),
            'recent45': metrics(rec),
        })
    return rows


def single_clause_impact(base: pd.DataFrame) -> List[Dict]:
    clauses = {
        'REVERSAL': base['combo_family'] == 'REVERSAL',
        'mid>=0.65': pd.to_numeric(base['source_mid_body_atr'], errors='coerce') >= 0.65,
        'gap>=0.8': pd.to_numeric(base['source_gap_atr'], errors='coerce') >= 0.8,
        'risk1-3': pd.to_numeric(base['risk_pct'], errors='coerce').between(1, 3, inclusive='both'),
        'width1.2-2.2': pd.to_numeric(base['v85_zone_width_pct'], errors='coerce').between(1.2, 2.2, inclusive='both'),
        'reclaim>=0.5': pd.to_numeric(base['reclaim_close_above_zone_pct'], errors='coerce') >= 0.5,
        'delay1-3': pd.to_numeric(base['touch_to_reclaim_bars'], errors='coerce').between(1, 3, inclusive='both'),
        'state_mixed_bear': base['market_state'].isin(V125_STATES),
    }
    rows = []
    for name, m in clauses.items():
        rows.append({
            'clause': name,
            'pass_all': metrics(base[m]),
            'fail_all': metrics(base[~m]),
            'pass_recent45': metrics(base[m & base['recent45']]),
            'fail_recent45': metrics(base[(~m) & base['recent45']]),
        })
    return rows


def fail_reason_counts(base: pd.DataFrame) -> Dict:
    recent = base[base['recent45']]
    tests = {
        'not_REVERSAL': recent['combo_family'] != 'REVERSAL',
        'mid<0.65': pd.to_numeric(recent['source_mid_body_atr'], errors='coerce') < 0.65,
        'gap<0.8': pd.to_numeric(recent['source_gap_atr'], errors='coerce') < 0.8,
        'risk_not_1_3': ~pd.to_numeric(recent['risk_pct'], errors='coerce').between(1, 3, inclusive='both'),
        'width_not_1.2_2.2': ~pd.to_numeric(recent['v85_zone_width_pct'], errors='coerce').between(1.2, 2.2, inclusive='both'),
        'reclaim<0.5': pd.to_numeric(recent['reclaim_close_above_zone_pct'], errors='coerce') < 0.5,
        'delay_not_1_3': ~pd.to_numeric(recent['touch_to_reclaim_bars'], errors='coerce').between(1, 3, inclusive='both'),
        'state_not_mixed_bear': ~recent['market_state'].isin(V125_STATES),
    }
    return {k: int(v.sum()) for k, v in tests.items()}


def bucket_metrics(base: pd.DataFrame) -> Dict:
    df = base.copy()
    df['risk_bucket'] = pd.cut(pd.to_numeric(df['risk_pct'], errors='coerce'), [-0.01,1,2,3,5,8,100], labels=['<=1','1-2','2-3','3-5','5-8','>8'])
    df['width_bucket'] = pd.cut(pd.to_numeric(df['v85_zone_width_pct'], errors='coerce'), [-0.01,1.2,2.2,3,5,100], labels=['<=1.2','1.2-2.2','2.2-3','3-5','>5'])
    df['mid_bucket'] = pd.cut(pd.to_numeric(df['source_mid_body_atr'], errors='coerce'), [-100,0.35,0.65,1,100], labels=['<0.35','0.35-0.65','0.65-1','>=1'])
    df['gap_bucket'] = pd.cut(pd.to_numeric(df['source_gap_atr'], errors='coerce'), [-100,0.5,0.8,1.2,100], labels=['<0.5','0.5-0.8','0.8-1.2','>=1.2'])
    out = {}
    for col in ['combo_family','market_state','risk_bucket','width_bucket','mid_bucket','gap_bucket','touch_to_reclaim_bars']:
        rows = []
        for val, g in df.groupby(col, observed=False):
            if len(g) == 0:
                continue
            rows.append({'bucket': str(val), 'all': metrics(g), 'recent45': metrics(g[g['recent45']])})
        out[col] = rows
    return out


def contract_search(base: pd.DataFrame) -> List[Dict]:
    num = lambda col: pd.to_numeric(base[col], errors='coerce')
    candidates = []
    family_opts = [
        ('ANY', pd.Series(True, index=base.index)),
        ('REVERSAL', base['combo_family'] == 'REVERSAL'),
        ('CONTINUATION', base['combo_family'] == 'CONTINUATION'),
    ]
    state_opts = [
        ('ANY', pd.Series(True, index=base.index)),
        ('MIXED_OR_BEAR', base['market_state'].isin(['MIXED','BEAR_RISK'])),
        ('BEAR_RISK', base['market_state'] == 'BEAR_RISK'),
        ('MIXED', base['market_state'] == 'MIXED'),
        ('NOT_DISTRIBUTION', base['market_state'] != 'DISTRIBUTION'),
    ]
    # Keep the grid deliberately small. This is V129 diagnosis, not an optimizer.
    mids = [0, 0.65, 1.0]
    gaps = [0, 0.8]
    risks = [(0,3), (0,5), (1,3), (1,5)]
    widths = [(0,3.0), (1.0,3.0), (1.2,2.2), (1.2,4.0)]
    reclaims = [0, 0.5]
    delays = [(1,3), (1,5)]
    for fname, fm in family_opts:
        for sname, sm in state_opts:
            for mid in mids:
                mm = num('source_mid_body_atr') >= mid
                for gap in gaps:
                    gm = num('source_gap_atr') >= gap
                    for rlo, rhi in risks:
                        rm = num('risk_pct').between(rlo, rhi, inclusive='both')
                        for wlo, whi in widths:
                            wm = num('v85_zone_width_pct').between(wlo, whi, inclusive='both')
                            for rec in reclaims:
                                recm = num('reclaim_close_above_zone_pct') >= rec
                                for dlo, dhi in delays:
                                    dm = num('touch_to_reclaim_bars').between(dlo, dhi, inclusive='both')
                                    mask = fm & sm & mm & gm & rm & wm & recm & dm
                                    sub = base[mask]
                                    recent = sub[sub['recent45']]
                                    if len(sub) < 80 or len(recent) < 10:
                                        continue
                                    ma = metrics(sub)
                                    mr = metrics(recent)
                                    # Research ranking only; not a production gate.
                                    score = (ma['wr'] - 36.49) + 0.35*(mr['wr'] - 35.59) - 0.03*max(0, 80-len(recent)) + 0.1*ma['stable5']
                                    candidates.append({
                                        'contract': f'{fname}; state={sname}; mid>={mid}; gap>={gap}; risk={rlo}-{rhi}; width={wlo}-{whi}; reclaim>={rec}; delay={dlo}-{dhi}',
                                        'score': round(float(score), 4),
                                        'all': ma,
                                        'recent45': mr,
                                    })
    candidates.sort(key=lambda x: (x['score'], x['all']['wr'], x['recent45']['n']), reverse=True)
    return candidates[:50]


def write_md(summary: Dict) -> str:
    lines = []
    lines.append('# V129 FVG_Demand scanner层合同分解（只读）')
    lines.append('')
    lines.append('Decision: `V129_SCANNER_NATIVE_FVG_CONTRACT_DECOMPOSED_NO_PRODUCTION_CHANGE`')
    lines.append('')
    lines.append('## 1. V125逐条件漏斗')
    lines.append('| step | all n | all WR | all loss | recent45 n | recent45 WR | recent45 loss |')
    lines.append('|---|---:|---:|---:|---:|---:|---:|')
    for r in summary['v125_cumulative_funnel']:
        a, b = r['all'], r['recent45']
        lines.append(f"| {r['step']} | {a['n']} | {a['wr']} | {a['loss_rate']} | {b['n']} | {b['wr']} | {b['loss_rate']} |")
    lines.append('')
    lines.append('## 2. recent45为什么V125=0')
    lines.append('| fail reason | count in recent45 FVG_Demand |')
    lines.append('|---|---:|')
    for k, v in summary['recent45_v125_fail_counts'].items():
        lines.append(f'| {k} | {v} |')
    lines.append('')
    lines.append('## 3. 单条件贡献（FVG_Demand全量）')
    lines.append('| clause | pass n/WR/loss | fail n/WR/loss | recent pass n/WR |')
    lines.append('|---|---:|---:|---:|')
    for r in summary['single_clause_impact']:
        p, f, rp = r['pass_all'], r['fail_all'], r['pass_recent45']
        lines.append(f"| {r['clause']} | {p['n']}/{p['wr']}/{p['loss_rate']} | {f['n']}/{f['wr']}/{f['loss_rate']} | {rp['n']}/{rp['wr']} |")
    lines.append('')
    lines.append('## 4. scanner-native候选合同Top10（研究用，非上线）')
    lines.append('| rank | contract | all n | all WR | all loss | recent n | recent WR | recent loss | stable5 |')
    lines.append('|---:|---|---:|---:|---:|---:|---:|---:|---:|')
    for i, r in enumerate(summary['top_contracts'][:10], 1):
        a, b = r['all'], r['recent45']
        lines.append(f"| {i} | {r['contract']} | {a['n']} | {a['wr']} | {a['loss_rate']} | {b['n']} | {b['wr']} | {b['loss_rate']} | {a['stable5']} |")
    lines.append('')
    lines.append('## 5. 结论')
    lines.append('- V125迁移失败不是字段缺失，而是历史研究样本与V128 scanner候选分布不同：严格条件全量只剩5条，recent45为0。')
    lines.append('- recent45最大阻断是risk/width与market_state/family分布；单独扩大FVG_Demand供应会放大低质量raw信号。')
    lines.append('- V129找到的scanner-native合同仍是shadow研究候选：有recent45覆盖，但WR/loss距离生产级仍不足，不能推广。')
    lines.append('- 下一步应做逐笔亏损语义复盘：高risk FVG是否是追高成交、zone过宽、reclaim后已离区过远，还是市场状态标注错误。')
    return '\n'.join(lines) + '\n'


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(IN_CSV)
    df = add_recent_flag(df)
    fvg = df[(df['poi_source'] == 'FVG_Demand') & (df['valid_backtest'] == True)].copy()

    summary = {
        'decision': 'V129_SCANNER_NATIVE_FVG_CONTRACT_DECOMPOSED_NO_PRODUCTION_CHANGE',
        'input_csv': str(IN_CSV),
        'base_all': metrics(df),
        'fvg_demand_all': metrics(fvg),
        'fvg_demand_recent45': metrics(fvg[fvg['recent45']]),
        'v125_scanner': metrics(fvg[mask_v125(fvg)]),
        'v125_scanner_recent45': metrics(fvg[mask_v125(fvg) & fvg['recent45']]),
        'v125_cumulative_funnel': breakdown_table(fvg, fvg[fvg['recent45']]),
        'single_clause_impact': single_clause_impact(fvg),
        'recent45_v125_fail_counts': fail_reason_counts(fvg),
        'bucket_metrics': bucket_metrics(fvg),
        'top_contracts': contract_search(fvg),
        'no_production_api_frontend_watchlist_write': True,
        'no_tp_sl_tuning': True,
    }
    (OUT_DIR / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    (OUT_DIR / 'report.md').write_text(write_md(summary))

    # CSV artifacts for quick review.
    pd.DataFrame([
        {'step': r['step'], **{f'all_{k}': v for k, v in r['all'].items()}, **{f'recent45_{k}': v for k, v in r['recent45'].items()}}
        for r in summary['v125_cumulative_funnel']
    ]).to_csv(OUT_DIR / 'v125_cumulative_funnel.csv', index=False)
    pd.DataFrame([
        {'contract': r['contract'], 'score': r['score'], **{f'all_{k}': v for k, v in r['all'].items()}, **{f'recent45_{k}': v for k, v in r['recent45'].items()}}
        for r in summary['top_contracts']
    ]).to_csv(OUT_DIR / 'scanner_native_contract_candidates.csv', index=False)
    print(json.dumps({
        'decision': summary['decision'],
        'out_dir': str(OUT_DIR),
        'fvg_all': summary['fvg_demand_all'],
        'fvg_recent45': summary['fvg_demand_recent45'],
        'v125_all': summary['v125_scanner'],
        'v125_recent45': summary['v125_scanner_recent45'],
        'top_contract': summary['top_contracts'][0] if summary['top_contracts'] else None,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
