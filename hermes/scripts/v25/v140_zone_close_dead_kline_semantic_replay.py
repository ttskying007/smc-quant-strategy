#!/usr/bin/env python3
"""V140 read-only K-line semantic replay for V139 no-MIXED RECLAIM losses.

Reads V138 executable shadow rows and local kline cache only.
Writes audit artifacts only. No production/API/frontend/watchlist/TP/SL changes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v138_keep_watch_strong_executable_semantic_audit_20260620' / 'v138_executable_entry_exit_shadow_backtest.csv'
OUT = ROOT / 'smc_audit' / 'v140_zone_close_dead_kline_semantic_replay_20260621'
KLINE_DIR = ROOT / 'kline_cache'
OUT.mkdir(parents=True, exist_ok=True)


def bool_s(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors='coerce')


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default


def pct(a: float, b: float) -> float:
    return 0.0 if b == 0 else (a - b) / b * 100.0


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


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def load_bars(symbol: str) -> list[dict[str, Any]]:
    p = kline_path(symbol)
    if not p.exists():
        p = KLINE_DIR / f"{symbol.replace('.', '_')}_daily_300.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding='utf-8'))
    if isinstance(data, dict):
        for key in ['data', 'klines', 'bars']:
            if isinstance(data.get(key), list):
                data = data[key]
                break
    return data if isinstance(data, list) else []


def bar_date(b: dict[str, Any]) -> str:
    return str(b.get('t', b.get('date', b.get('time', '')))).replace('-', '')[:8]


def enrich_row(r: pd.Series) -> dict[str, Any]:
    symbol = str(r['symbol'])
    bars = load_bars(symbol)
    dates = {bar_date(b): i for i, b in enumerate(bars)}
    entry_date = str(r['v138_entry_date'])[:8]
    reclaim_i = int(fnum(r['reclaim_idx'], -1))
    touch_i = int(fnum(r['touch_idx'], -1))
    entry_i = dates.get(entry_date, int(fnum(r['v138_entry_idx'], -1)))
    zone_high = fnum(r['zone_high'])
    zone_low = fnum(r['zone_low'])
    entry_price = fnum(r['v138_entry_price'])
    reclaim_close = fnum(r['reclaim_close'])
    reclaim_low = None
    reclaim_high = None
    entry_open = entry_high = entry_low = entry_close = None
    next1_close = next1_low = None
    next2_close = next2_low = None

    def get(i: int, key: str) -> float | None:
        if i < 0 or i >= len(bars):
            return None
        return fnum(bars[i].get(key), None)  # type: ignore[arg-type]

    reclaim_low = get(reclaim_i, 'l')
    reclaim_high = get(reclaim_i, 'h')
    entry_open = get(entry_i, 'o')
    entry_high = get(entry_i, 'h')
    entry_low = get(entry_i, 'l')
    entry_close = get(entry_i, 'c')
    next1_close = get(entry_i + 1, 'c')
    next1_low = get(entry_i + 1, 'l')
    next2_close = get(entry_i + 2, 'c')
    next2_low = get(entry_i + 2, 'l')

    entry_above_zone = pct(entry_price, zone_high)
    entry_reclaim_gap = pct(entry_price, reclaim_close)
    entry_day_retests_zone = bool(entry_low is not None and entry_low <= zone_high)
    entry_day_closes_below_zone = bool(entry_close is not None and entry_close < zone_high)
    entry_day_close_pos = 0.0
    if entry_high is not None and entry_low is not None and entry_high > entry_low and entry_close is not None:
        entry_day_close_pos = (entry_close - entry_low) / (entry_high - entry_low) * 100.0
    next1_zone_fail = bool(next1_close is not None and next1_close < zone_high)
    next2_zone_fail = bool(next2_close is not None and next2_close < zone_high)
    early_zone_fail = entry_day_closes_below_zone or next1_zone_fail or next2_zone_fail
    early_low_break_reclaim = bool(reclaim_low is not None and (
        (entry_low is not None and entry_low < reclaim_low) or
        (next1_low is not None and next1_low < reclaim_low) or
        (next2_low is not None and next2_low < reclaim_low)
    ))
    no_entry_follow_through = bool(entry_close is not None and entry_close <= entry_price * 1.01)
    gap_up_fade = bool(entry_reclaim_gap > 2.0 and entry_day_close_pos < 45.0)
    zone_close_dead_lead = bool(early_zone_fail or early_low_break_reclaim or gap_up_fade or no_entry_follow_through or entry_above_zone > 2.0)

    return {
        **r.to_dict(),
        'v140_kline_found': bool(len(bars)),
        'v140_entry_i_resolved': int(entry_i),
        'v140_entry_above_zone_high_pct': round(entry_above_zone, 4),
        'v140_entry_above_reclaim_close_pct': round(entry_reclaim_gap, 4),
        'v140_entry_day_retests_zone_high': entry_day_retests_zone,
        'v140_entry_day_closes_below_zone_high': entry_day_closes_below_zone,
        'v140_entry_day_close_pos_pct': round(entry_day_close_pos, 4),
        'v140_next1_closes_below_zone_high': next1_zone_fail,
        'v140_next2_closes_below_zone_high': next2_zone_fail,
        'v140_early_zone_fail_0_2': early_zone_fail,
        'v140_early_low_breaks_reclaim_low_0_2': early_low_break_reclaim,
        'v140_no_entry_follow_through_le_1pct': no_entry_follow_through,
        'v140_gap_up_fade': gap_up_fade,
        'v140_zone_close_dead_lead_signal': zone_close_dead_lead,
    }


def bucket_rows(df: pd.DataFrame) -> pd.DataFrame:
    conditions = {
        'entry_above_zone>2': df['v140_entry_above_zone_high_pct'] > 2,
        'entry_above_reclaim>2': df['v140_entry_above_reclaim_close_pct'] > 2,
        'entry_day_retests_zone': bool_s(df['v140_entry_day_retests_zone_high']),
        'entry_day_closes_below_zone': bool_s(df['v140_entry_day_closes_below_zone_high']),
        'next1_closes_below_zone': bool_s(df['v140_next1_closes_below_zone_high']),
        'next2_closes_below_zone': bool_s(df['v140_next2_closes_below_zone_high']),
        'early_zone_fail_0_2': bool_s(df['v140_early_zone_fail_0_2']),
        'early_low_breaks_reclaim_low_0_2': bool_s(df['v140_early_low_breaks_reclaim_low_0_2']),
        'no_entry_follow_through_le_1pct': bool_s(df['v140_no_entry_follow_through_le_1pct']),
        'gap_up_fade': bool_s(df['v140_gap_up_fade']),
        'zone_close_dead_lead_signal': bool_s(df['v140_zone_close_dead_lead_signal']),
    }
    rows = []
    for name, mask in conditions.items():
        sub = df[mask]
        rows.append({'bucket': name, 'n': int(mask.sum()), 'share_pct': round(float(mask.mean() * 100), 2) if len(df) else 0.0, **metrics(sub)})
    return pd.DataFrame(rows).sort_values(['n', 'bucket'], ascending=[False, True])


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    base = df[(df['v138_mode'].eq('RECLAIM_NEXT_OPEN')) & (~bool_s(df['v138_mixed']))].copy()
    losses = base[base['v138_pnl_pct'] <= 0].copy()
    zcd = losses[losses['v138_exit_reason'].eq('ZONE_CLOSE_DEAD_T1')].copy()
    enriched = pd.DataFrame([enrich_row(r) for _, r in zcd.iterrows()])
    enriched.to_csv(OUT / 'v140_zone_close_dead_replay_rows.csv', index=False)
    buckets = bucket_rows(enriched) if len(enriched) else pd.DataFrame()
    buckets.to_csv(OUT / 'v140_zone_close_dead_lead_buckets.csv', index=False)

    # Counterfactual diagnostic on the whole non-MIXED RECLAIM baseline, not a production gate.
    all_enriched = pd.DataFrame([enrich_row(r) for _, r in base.iterrows()])
    all_enriched.to_csv(OUT / 'v140_no_mixed_reclaim_all_replay_rows.csv', index=False)
    keep_no_lead = all_enriched[~bool_s(all_enriched['v140_zone_close_dead_lead_signal'])]
    reject_lead = all_enriched[bool_s(all_enriched['v140_zone_close_dead_lead_signal'])]
    sens = pd.DataFrame([
        {'slice': 'R1_no_mixed_reclaim_baseline', **metrics(all_enriched)},
        {'slice': 'keep_without_v140_lead_signal', **metrics(keep_no_lead)},
        {'slice': 'reject_v140_lead_signal', **metrics(reject_lead)},
    ])
    sens.to_csv(OUT / 'v140_lead_signal_counterfactual.csv', index=False)

    t1 = int(bool_s(df['v138_t1_violation']).sum())
    summary = {
        'decision': 'V140_READONLY_ZONE_CLOSE_DEAD_KLINE_REPLAY_DONE_NO_PRODUCTION_CHANGE',
        'input': str(IN),
        'out': str(OUT),
        'production_write': False,
        'baseline_no_mixed_reclaim': metrics(all_enriched),
        'zone_close_dead_loss_count': int(len(zcd)),
        'zone_close_dead_bucket_top': buckets.head(8).to_dict(orient='records') if len(buckets) else [],
        'lead_signal_counterfactual': sens.to_dict(orient='records'),
        't1_violation_count': t1,
        'missing_kline_count': int((~bool_s(enriched['v140_kline_found'])).sum()) if len(enriched) else 0,
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    md = []
    md.append('# V140 ZONE_CLOSE_DEAD K线语义复盘（只读）')
    md.append('')
    md.append(f"Decision: `{summary['decision']}`。仅读 V138 shadow 结果 + 本地K线缓存，只写 audit 目录；未改生产/API/frontend/watchlist/TP/SL。")
    md.append('')
    md.append('## 1. no-MIXED RECLAIM 基线与 V140 lead-signal 诊断')
    md.append(sens.to_markdown(index=False))
    md.append('')
    md.append('## 2. ZONE_CLOSE_DEAD_T1 亏损前兆桶')
    md.append(buckets.to_markdown(index=False) if len(buckets) else '无 ZONE_CLOSE_DEAD_T1 样本')
    md.append('')
    md.append('## 3. 结论')
    md.append('- V139 剩余亏损核心不是 TP/SL 参数，而是 reclaim 后 0-2 根内再次失守 zone_high / 跌破 reclaim low / gap-up fade。')
    md.append('- `v140_zone_close_dead_lead_signal` 是失败语义诊断，不是生产 gate；若后续要进入交易层，只能作为 watch/cancel 事件继续 shadow。')
    md.append('- 下一步应验证该 lead-signal 在全部 KEEP_WATCH 生命周期中的时序可用性：是否能在买入前或未成交 watch 阶段触发取消；不能把事后T+1失败当作原始入场选择器。')
    (OUT / 'report.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
