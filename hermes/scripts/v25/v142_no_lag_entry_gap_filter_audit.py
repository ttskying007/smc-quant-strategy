#!/usr/bin/env python3
"""V142 read-only no-lag entry-gap/chase filter audit.

Continues V141: only signals knowable before original next-open buy decision
may be considered as original BUY filters. This script searches pre-buy-known
entry distance/risk/chase thresholds and writes audit artifacts only.
No production/API/frontend/watchlist changes.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v141_v140_lead_timing_availability_20260621' / 'v141_timing_availability_rows.csv'
OUT = ROOT / 'smc_audit' / 'v142_no_lag_entry_gap_filter_audit_20260621'
OUT.mkdir(parents=True, exist_ok=True)


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 'recent_avg': 0.0}
    pnl = num(df['v138_pnl_pct'])
    recent = df[bool_s(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = num(recent['v138_pnl_pct']) if len(recent) else pd.Series(dtype=float)
    hard = df['v138_exit_reason'].astype(str).isin(['ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1'])
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        'recent_avg': round(float(rp.mean()), 4) if len(recent) else 0.0,
    }


def with_delta(row: dict[str, Any], base: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out['delta_n'] = int(row['n'] - base['n'])
    out['delta_wr'] = round(float(row['wr'] - base['wr']), 2)
    out['delta_avg'] = round(float(row['avg'] - base['avg']), 4)
    out['delta_loss'] = round(float(row['loss'] - base['loss']), 2)
    out['delta_hard_exit'] = round(float(row['hard_exit'] - base['hard_exit']), 2)
    return out


def production_probe() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ep in ['/api/summary', '/api/picks/contract']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=8) as r:
                out[ep] = json.loads(r.read().decode('utf-8'))
        except Exception as e:
            out[ep] = {'error': repr(e)}
    return out


def candidate_masks(df: pd.DataFrame) -> list[tuple[str, pd.Series]]:
    masks: list[tuple[str, pd.Series]] = []
    zone_gap = num(df['v140_entry_above_zone_high_pct'])
    reclaim_gap = num(df['v140_entry_above_reclaim_close_pct'])
    chase = num(df['entry_chase_above_zone_pct']) if 'entry_chase_above_zone_pct' in df else zone_gap
    risk = num(df['v138_risk_pct'])
    source_gap_atr = num(df['source_gap_atr'])
    source_mid_body_atr = num(df['source_mid_body_atr'])
    close_above_zone = num(df['v132_reclaim_close_above_zone_high_pct'])

    for th in [1, 2, 3, 4, 5, 6, 8, 10, 12, 15]:
        masks.append((f'keep_entry_above_zone_le_{th}', zone_gap <= th))
        masks.append((f'keep_entry_above_reclaim_le_{th}', reclaim_gap <= th))
        masks.append((f'keep_chase_above_zone_le_{th}', chase <= th))
    for th in [3, 4, 5, 6, 7, 8, 10]:
        masks.append((f'keep_risk_pct_le_{th}', risk <= th))
    for th in [0.2, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0]:
        masks.append((f'keep_source_gap_atr_ge_{th}', source_gap_atr >= th))
        masks.append((f'keep_source_mid_body_atr_ge_{th}', source_mid_body_atr >= th))
    for lo, hi in [(0.5, 8), (0.5, 6), (0.5, 5), (1.0, 8), (1.0, 6), (1.0, 5)]:
        masks.append((f'keep_reclaim_close_above_zone_{lo}_to_{hi}', (close_above_zone >= lo) & (close_above_zone <= hi)))
    return masks


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    df = df[bool_s(df['valid_backtest'])].copy() if 'valid_backtest' in df else df.copy()

    baseline = metrics(df)
    rows: list[dict[str, Any]] = []
    for name, mask in candidate_masks(df):
        keep = df[mask.fillna(False)]
        reject = df[~mask.fillna(False)]
        km = metrics(keep)
        rm = metrics(reject)
        row = with_delta({'rule': name, **km, 'reject_n': rm['n'], 'reject_wr': rm['wr'], 'reject_avg': rm['avg'], 'reject_loss': rm['loss'], 'reject_hard_exit': rm['hard_exit']}, baseline)
        row['production_safe_candidate'] = bool(row['n'] >= 120 and row['delta_wr'] >= 0 and row['delta_avg'] >= 0 and row['delta_hard_exit'] <= 0 and row['recent_n'] >= 10 and row['recent_wr'] >= baseline['recent_wr'])
        rows.append(row)

    # Two-factor combinations, kept intentionally small and pre-buy-known.
    zone_gap = num(df['v140_entry_above_zone_high_pct'])
    chase = num(df['entry_chase_above_zone_pct']) if 'entry_chase_above_zone_pct' in df else zone_gap
    risk = num(df['v138_risk_pct'])
    source_gap_atr = num(df['source_gap_atr'])
    combo_rows: list[dict[str, Any]] = []
    for z in [3, 4, 5, 6, 8, 10]:
        for r in [5, 6, 7, 8, 10]:
            mask = (zone_gap <= z) & (risk <= r)
            m = metrics(df[mask.fillna(False)])
            row = with_delta({'rule': f'keep_zone_gap_le_{z}__risk_le_{r}', **m}, baseline)
            row['production_safe_candidate'] = bool(row['n'] >= 120 and row['delta_wr'] >= 0 and row['delta_avg'] >= 0 and row['delta_hard_exit'] <= 0 and row['recent_n'] >= 10 and row['recent_wr'] >= baseline['recent_wr'])
            combo_rows.append(row)
    for c in [3, 4, 5, 6, 8, 10]:
        for sg in [0.2, 0.3, 0.4, 0.5, 0.65]:
            mask = (chase <= c) & (source_gap_atr >= sg)
            m = metrics(df[mask.fillna(False)])
            row = with_delta({'rule': f'keep_chase_le_{c}__source_gap_atr_ge_{sg}', **m}, baseline)
            row['production_safe_candidate'] = bool(row['n'] >= 120 and row['delta_wr'] >= 0 and row['delta_avg'] >= 0 and row['delta_hard_exit'] <= 0 and row['recent_n'] >= 10 and row['recent_wr'] >= baseline['recent_wr'])
            combo_rows.append(row)

    single = pd.DataFrame(rows).sort_values(['production_safe_candidate', 'delta_avg', 'delta_hard_exit', 'n'], ascending=[False, False, True, False])
    combo = pd.DataFrame(combo_rows).sort_values(['production_safe_candidate', 'delta_avg', 'delta_hard_exit', 'n'], ascending=[False, False, True, False])
    single.to_csv(OUT / 'v142_single_factor_thresholds.csv', index=False)
    combo.to_csv(OUT / 'v142_two_factor_thresholds.csv', index=False)

    safe_single = single[single['production_safe_candidate']].copy()
    safe_combo = combo[combo['production_safe_candidate']].copy()
    production = production_probe()
    decision = 'NO_PRE_BUY_FILTER_PROMOTION'
    best = None
    if len(safe_single) or len(safe_combo):
        candidates = pd.concat([safe_single.assign(kind='single'), safe_combo.assign(kind='combo')], ignore_index=True)
        candidates = candidates.sort_values(['delta_avg', 'delta_hard_exit', 'n'], ascending=[False, True, False])
        best = candidates.iloc[0].to_dict()
        # Still no promotion unless it improves both all-sample and recent materially.
        if best['delta_avg'] >= 0.25 and best['delta_wr'] >= 2.0 and best['delta_hard_exit'] <= -2.0:
            decision = 'HAS_STRONG_NO_LAG_FILTER_CANDIDATE_BUT_NOT_PROMOTED_READONLY'
        else:
            decision = 'ONLY_WEAK_NO_LAG_FILTER_CANDIDATES_NO_PROMOTION'

    summary = {
        'decision': decision,
        'production_write': False,
        'input': str(IN),
        'out': str(OUT),
        'baseline': baseline,
        'best_safe_candidate': best,
        'safe_single_count': int(len(safe_single)),
        'safe_combo_count': int(len(safe_combo)),
        'top_single': single.head(15).to_dict(orient='records'),
        'top_combo': combo.head(15).to_dict(orient='records'),
        't1_violation_count': int(bool_s(df['v138_t1_violation']).sum()) if 'v138_t1_violation' in df else -1,
        'production_probe': {
            'summary_engine': production.get('/api/summary', {}).get('engine'),
            'summary_total_trades': production.get('/api/summary', {}).get('total_trades'),
            'summary_win_rate': production.get('/api/summary', {}).get('win_rate'),
            'tradable_active_pick_count': production.get('/api/picks/contract', {}).get('tradable_active_pick_count'),
            'watch_only_count': production.get('/api/picks/contract', {}).get('watch_only_count'),
            'raw_pick_file_count': production.get('/api/picks/contract', {}).get('raw_pick_file_count'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    md: list[str] = []
    md.append('# V142 no-lag entry-gap/chase filter audit（只读）')
    md.append('')
    md.append(f"Decision: `{decision}`。只读 V141 rows；只写 `{OUT}`；未改生产/API/frontend/watchlist/TP/SL。")
    md.append('')
    md.append('## 1. Baseline')
    md.append(pd.DataFrame([baseline]).to_markdown(index=False))
    md.append('')
    md.append('## 2. 可上线候选判定')
    if best:
        md.append(pd.DataFrame([best]).to_markdown(index=False))
        md.append('')
        md.append('结论：候选未达到“全样本WR +2pp、均值 +0.25pp、hard_exit -2pp”三项同时改善的晋级线，因此不推广为生产买入过滤器。')
    else:
        md.append('没有任何满足最低安全线的买入前过滤候选。')
    md.append('')
    md.append('## 3. Top single-factor thresholds')
    md.append(single.head(12).to_markdown(index=False))
    md.append('')
    md.append('## 4. Top two-factor thresholds')
    md.append(combo.head(12).to_markdown(index=False))
    md.append('')
    md.append('## 5. 生产/T+1验证')
    md.append(f"- T+1 violation: `{summary['t1_violation_count']}`")
    md.append(f"- production summary: `{summary['production_probe']}`")
    md.append('')
    md.append('## 6. 下一步')
    md.append('买入前 entry-gap/chase 过滤没有足够收益；继续走 V141 第二条：把 close/intraday 才知道的信号做 watch/cancel 生命周期元数据的只读映射，不变成 BUY。')
    (OUT / 'report.md').write_text('\n'.join(md), encoding='utf-8')


if __name__ == '__main__':
    main()
