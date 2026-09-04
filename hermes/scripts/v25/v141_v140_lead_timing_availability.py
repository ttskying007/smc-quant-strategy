#!/usr/bin/env python3
"""V141 read-only timing availability audit for V140 lead signatures.

Goal: determine whether V140's no-follow-through / entry-above-zone /
entry-day zone-retest signatures are knowable before buy, only on entry day,
or only after the buy. Writes audit artifacts only.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v140_zone_close_dead_kline_semantic_replay_20260621' / 'v140_no_mixed_reclaim_all_replay_rows.csv'
OUT = ROOT / 'smc_audit' / 'v141_v140_lead_timing_availability_20260621'
OUT.mkdir(parents=True, exist_ok=True)


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')


def metrics(df: pd.DataFrame) -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0}
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
    }


def row_metrics(name: str, df: pd.DataFrame) -> dict[str, Any]:
    return {'slice': name, **metrics(df)}


def production_probe() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ep in ['/api/summary', '/api/picks/contract']:
        try:
            with urllib.request.urlopen('http://127.0.0.1:8890' + ep, timeout=8) as r:
                out[ep] = json.loads(r.read().decode('utf-8'))
        except Exception as e:  # audit only
            out[ep] = {'error': repr(e)}
    return out


def classify_timing(row: pd.Series) -> str:
    """Earliest possible availability for V140 lead components.

    PRE_BUY_AT_NEXT_OPEN: known before order decision at original next-open.
    ENTRY_DAY_AFTER_OPEN: known at/after entry open but before close.
    ENTRY_DAY_CLOSE: requires same-day close, cannot cancel original buy.
    AFTER_ENTRY_DAY: requires later bars.
    NONE: no V140 lead signature.
    """
    entry_above_zone = bool(row['v140_entry_above_zone_high_pct'] > 2.0)
    entry_above_reclaim = bool(row['v140_entry_above_reclaim_close_pct'] > 2.0)
    zone_retest = str(row['v140_entry_day_retests_zone_high']).lower() == 'true'
    no_follow = str(row['v140_no_entry_follow_through_le_1pct']).lower() == 'true'
    gap_up_fade = str(row['v140_gap_up_fade']).lower() == 'true'
    entry_close_fail = str(row['v140_entry_day_closes_below_zone_high']).lower() == 'true'
    next_fail = (
        str(row['v140_next1_closes_below_zone_high']).lower() == 'true'
        or str(row['v140_next2_closes_below_zone_high']).lower() == 'true'
    )
    if entry_above_zone or entry_above_reclaim:
        return 'PRE_BUY_AT_NEXT_OPEN'
    if zone_retest:
        return 'ENTRY_DAY_AFTER_OPEN'
    if no_follow or gap_up_fade or entry_close_fail:
        return 'ENTRY_DAY_CLOSE'
    if next_fail:
        return 'AFTER_ENTRY_DAY'
    return 'NONE'


def component_table(df: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('entry_above_zone>2', 'PRE_BUY_AT_NEXT_OPEN', df['v140_entry_above_zone_high_pct'] > 2.0),
        ('entry_above_reclaim>2', 'PRE_BUY_AT_NEXT_OPEN', df['v140_entry_above_reclaim_close_pct'] > 2.0),
        ('entry_day_retests_zone', 'ENTRY_DAY_AFTER_OPEN', bool_s(df['v140_entry_day_retests_zone_high'])),
        ('no_entry_follow_through<=1%', 'ENTRY_DAY_CLOSE', bool_s(df['v140_no_entry_follow_through_le_1pct'])),
        ('gap_up_fade', 'ENTRY_DAY_CLOSE', bool_s(df['v140_gap_up_fade'])),
        ('entry_day_closes_below_zone', 'ENTRY_DAY_CLOSE', bool_s(df['v140_entry_day_closes_below_zone_high'])),
        ('next1_or_next2_closes_below_zone', 'AFTER_ENTRY_DAY', bool_s(df['v140_next1_closes_below_zone_high']) | bool_s(df['v140_next2_closes_below_zone_high'])),
    ]
    rows = []
    for name, timing, mask in specs:
        rows.append({'component': name, 'timing': timing, **metrics(df[mask])})
    return pd.DataFrame(rows)


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    df['v141_earliest_lead_timing'] = df.apply(classify_timing, axis=1)
    df['v141_pre_buy_cancel_available'] = df['v141_earliest_lead_timing'].eq('PRE_BUY_AT_NEXT_OPEN')
    df['v141_intraday_cancel_only'] = df['v141_earliest_lead_timing'].eq('ENTRY_DAY_AFTER_OPEN')
    df['v141_close_or_later_only'] = df['v141_earliest_lead_timing'].isin(['ENTRY_DAY_CLOSE', 'AFTER_ENTRY_DAY'])
    df['v141_original_buy_selector_valid'] = df['v141_pre_buy_cancel_available']
    df['v141_watch_cancel_valid_after_buy_decision'] = df['v141_earliest_lead_timing'].ne('NONE')
    df.to_csv(OUT / 'v141_timing_availability_rows.csv', index=False)

    by_timing = pd.DataFrame([row_metrics(str(k), g) for k, g in df.groupby('v141_earliest_lead_timing', dropna=False)])
    by_timing.to_csv(OUT / 'v141_by_timing_metrics.csv', index=False)

    components = component_table(df)
    components.to_csv(OUT / 'v141_component_timing_metrics.csv', index=False)

    baseline = df
    prebuy_reject = df[bool_s(df['v141_pre_buy_cancel_available'])]
    prebuy_keep = df[~bool_s(df['v141_pre_buy_cancel_available'])]
    watch_reject = df[bool_s(df['v141_watch_cancel_valid_after_buy_decision'])]
    watch_keep = df[~bool_s(df['v141_watch_cancel_valid_after_buy_decision'])]
    close_later = df[bool_s(df['v141_close_or_later_only'])]
    sensitivity = pd.DataFrame([
        row_metrics('baseline_no_mixed_reclaim', baseline),
        row_metrics('reject_pre_buy_known_entry_gap_only', prebuy_reject),
        row_metrics('keep_after_pre_buy_gap_filter', prebuy_keep),
        row_metrics('watch_cancel_all_v140_lead_after_decision', watch_reject),
        row_metrics('keep_without_any_v140_lead', watch_keep),
        row_metrics('signals_known_only_entry_close_or_later', close_later),
    ])
    sensitivity.to_csv(OUT / 'v141_timing_counterfactual.csv', index=False)

    zcd = df[df['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1')]
    zcd_timing = pd.DataFrame([row_metrics(str(k), g) for k, g in zcd.groupby('v141_earliest_lead_timing', dropna=False)])
    zcd_timing.to_csv(OUT / 'v141_zone_close_dead_by_timing.csv', index=False)

    t1 = int(bool_s(df['v138_t1_violation']).sum()) if 'v138_t1_violation' in df else -1
    production = production_probe()
    summary = {
        'decision': 'V141_READONLY_V140_LEAD_TIMING_AVAILABILITY_DONE_NO_PRODUCTION_CHANGE',
        'input': str(IN),
        'out': str(OUT),
        'production_write': False,
        'timing_meaning': {
            'PRE_BUY_AT_NEXT_OPEN': 'known before original next-open buy decision; only this can be original-entry cancel/filter',
            'ENTRY_DAY_AFTER_OPEN': 'known after buy/open intraday; can only be intraday risk/watch metadata, not avoid original buy',
            'ENTRY_DAY_CLOSE': 'known after entry-day close; next-cycle/watch downgrade only',
            'AFTER_ENTRY_DAY': 'known after later bars; next-cycle/watch downgrade only',
            'NONE': 'no V140 lead signature',
        },
        'baseline': metrics(baseline),
        'by_timing': by_timing.to_dict(orient='records'),
        'component_timing': components.to_dict(orient='records'),
        'counterfactual': sensitivity.to_dict(orient='records'),
        'zone_close_dead_by_timing': zcd_timing.to_dict(orient='records'),
        't1_violation_count': t1,
        'production_probe': {
            'summary_engine': production.get('/api/summary', {}).get('engine'),
            'summary_total_trades': production.get('/api/summary', {}).get('total_trades'),
            'summary_win_rate': production.get('/api/summary', {}).get('win_rate'),
            'tradable_active_pick_count': production.get('/api/picks/contract', {}).get('tradable_active_pick_count'),
            'watch_only_count': production.get('/api/picks/contract', {}).get('watch_only_count'),
            'raw_pick_file_count': production.get('/api/picks/contract', {}).get('raw_pick_file_count'),
        },
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    md = []
    md.append('# V141 V140 lead signal timing availability audit（只读）')
    md.append('')
    md.append(f"Decision: `{summary['decision']}`。只读 V140 replay rows；只写 `{OUT}`；未改生产/API/frontend/watchlist/TP/SL。")
    md.append('')
    md.append('## 1. 结论')
    md.append('V140 的组合 lead signal 不能整体升级为原始买入前过滤器。只有 `entry_above_zone>2` / `entry_above_reclaim>2` 这类 next-open 价格距离信号在买入前可知；`no_entry_follow_through<=1%` 必须等买入日收盘，`entry_day_retests_zone` 必须等买入后盘中，后两者只能作为 watch/cancel/次周期降级元数据，不能用来证明原始买点可过滤。')
    md.append('')
    md.append('## 2. Timing sensitivity')
    md.append(sensitivity.to_markdown(index=False))
    md.append('')
    md.append('## 3. Component timing')
    md.append(components.to_markdown(index=False))
    md.append('')
    md.append('## 4. ZONE_CLOSE_DEAD_T1 timing')
    md.append(zcd_timing.to_markdown(index=False))
    md.append('')
    md.append('## 5. 生产/T+1验证')
    md.append(f"- T+1 violation: `{t1}`")
    md.append(f"- production summary: `{summary['production_probe']}`")
    md.append('')
    md.append('## 6. 下一步')
    md.append('不要把 V140 lead signal 作为原始买入选择器上线。下一步只允许两条只读方向：1) 用买入前可知的 entry-gap/chase 单独做 no-lag 过滤审计；2) 把 close/intraday 才知道的信号做 watch/cancel 生命周期元数据，不变成 BUY。')
    (OUT / 'report.md').write_text('\n'.join(md), encoding='utf-8')


if __name__ == '__main__':
    main()
