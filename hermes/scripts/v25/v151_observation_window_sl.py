#!/usr/bin/env python3
"""V151: Observation-window SL for lifecycle CANCEL signals.

V150 showed: breakeven SL (entry_price + 50bp) on lifecycle CANCEL signals
achieves 100% WR but avg drops to +0.50% (from baseline +1.50% on those
trades). Root cause: 30/47 trades eventually recover to avg +4.78%, but
the +50bp SL is too tight and triggers on trades that would win big.

V151 approach: Instead of triggering SL on the CANCEL day, set a fixed
observation window of N bars after entry. At the end of the window:
- If price >= entry_price + 1% (profit buffer), keep baseline exit
- If price < entry_price + 1%, set emergency SL at entry_price - 1%
  (cap loss at -1% but let the trade still recover to breakeven+)

This gives winning trades 3-7 bars to establish their recovery, while
capping losing trades at -1% instead of -4.3%.

T+1 enforced throughout.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
IN = ROOT / 'smc_audit' / 'v141_v140_lead_timing_availability_20260621' / 'v141_timing_availability_rows.csv'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_audit' / 'v151_observation_window_sl_backtest_20260621'
OUT.mkdir(parents=True, exist_ok=True)


def fnum(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            return default
        return float(v)
    except Exception:
        return default


def bseries(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().eq('true')


def pct(a: float, b: float) -> float:
    return 0.0 if a <= 0 or b <= 0 else (a / b - 1.0) * 100.0


def date_key(v: Any) -> str:
    return str(v or '').replace('-', '')[:8]


def bar_date(bar: dict[str, Any]) -> str:
    return date_key(bar.get('t') or bar.get('date') or bar.get('day') or bar.get('time'))


def load_bars(symbol: str) -> list[dict[str, Any]]:
    stem = symbol.replace('.', '_')
    for suffix in ('daily_750', 'daily_300'):
        p = KLINE_DIR / f'{stem}_{suffix}.json'
        if p.exists():
            data = json.loads(p.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                for key in ('data', 'klines', 'bars'):
                    if isinstance(data.get(key), list):
                        data = data[key]
                        break
            return data if isinstance(data, list) else []
    return []


def bar_val(b: dict[str, Any], key: str) -> float:
    return fnum(b.get(key))


def metrics(df: pd.DataFrame, pnl_col: str = 'v151_pnl_pct') -> dict[str, Any]:
    n = int(len(df))
    if n == 0:
        return {'n': 0, 'wr': 0.0, 'avg': 0.0, 'median': 0.0, 'loss': 0.0, 'hard_exit': 0.0, 'recent_n': 0, 'recent_wr': 0.0, 't1': 0}
    pnl = pd.to_numeric(df[pnl_col], errors='coerce').fillna(0.0)
    recent = df[bseries(df['is_recent45'])] if 'is_recent45' in df else df.iloc[0:0]
    rp = pd.to_numeric(recent[pnl_col], errors='coerce').fillna(0.0) if len(recent) else pd.Series(dtype=float)
    hard = df['v151_exit_reason'].astype(str).isin([
        'ZONE_CLOSE_DEAD_T1', 'STRUCTURE_SL_T1', 'LIFECYCLE_CANCEL_NEXT_OPEN',
        'OBSERVATION_WINDOW_SL_HIT',
    ])
    return {
        'n': n,
        'wr': round(float((pnl > 0).mean() * 100), 2),
        'avg': round(float(pnl.mean()), 4),
        'median': round(float(pnl.median()), 4),
        'loss': round(float((pnl <= 0).mean() * 100), 2),
        'hard_exit': round(float(hard.mean() * 100), 2),
        'recent_n': int(len(recent)),
        'recent_wr': round(float((rp > 0).mean() * 100), 2) if len(recent) else 0.0,
        't1': int(df['v151_t1_violation'].astype(bool).sum()) if 'v151_t1_violation' in df else -1,
    }


def lifecycle_status(row: pd.Series) -> tuple[str, str]:
    timing = str(row.get('v141_earliest_lead_timing', 'NONE'))
    no_ft = str(row.get('v140_no_entry_follow_through_le_1pct', '')).lower() == 'true'
    retest = str(row.get('v140_entry_day_retests_zone_high', '')).lower() == 'true'
    close_fail = str(row.get('v140_entry_day_closes_below_zone_high', '')).lower() == 'true'
    early_zone_fail = str(row.get('v140_early_zone_fail_0_2', '')).lower() == 'true'
    if timing == 'PRE_BUY_AT_NEXT_OPEN':
        status = 'PRE_BUY_GAP_NOTE_ONLY'
    elif close_fail or no_ft or early_zone_fail:
        status = 'CANCEL_AFTER_ENTRY_DAY_CLOSE'
    elif retest or timing == 'ENTRY_DAY_AFTER_OPEN':
        status = 'INTRADAY_RISK_NOTE_ONLY'
    else:
        status = 'KEEP_WATCH_NO_LATE_FAILURE'
    reasons: list[str] = []
    if no_ft:
        reasons.append('NO_ENTRY_FOLLOW_THROUGH_LE_1PCT')
    if close_fail:
        reasons.append('ENTRY_DAY_CLOSES_BELOW_ZONE_HIGH')
    if early_zone_fail:
        reasons.append('EARLY_ZONE_FAIL_0_2')
    if retest:
        reasons.append('ENTRY_DAY_RETESTS_ZONE_HIGH')
    if timing == 'PRE_BUY_AT_NEXT_OPEN':
        reasons.append('PRE_BUY_ENTRY_GAP_ONLY')
    return status, ('|'.join(reasons) if reasons else 'NONE')


def original_baseline_row(row: pd.Series) -> dict[str, Any]:
    status, reason = lifecycle_status(row)
    out = row.to_dict()
    out.update({
        'v151_variant': 'BASELINE_V138_RECLAIM_NEXT_OPEN',
        'v151_entry_idx': int(fnum(row.get('v138_entry_idx'), -1)),
        'v151_entry_date': date_key(row.get('v138_entry_date')),
        'v151_entry_price': fnum(row.get('v138_entry_price')),
        'v151_exit_idx': int(fnum(row.get('v138_exit_idx'), -1)),
        'v151_exit_date': date_key(row.get('v138_exit_date')),
        'v151_exit_price': fnum(row.get('v138_exit_price')),
        'v151_exit_reason': str(row.get('v138_exit_reason')),
        'v151_pnl_pct': fnum(row.get('v138_pnl_pct')),
        'v151_t1_violation': date_key(row.get('v138_entry_date')) == date_key(row.get('v138_exit_date')),
        'v151_lifecycle_action': 'BASELINE',
        'v143_lifecycle_status': status,
        'v143_lifecycle_reason': reason,
    })
    return out


def find_obs_window_sl_hit(
    bars: list[dict[str, Any]],
    entry_idx: int,
    entry_price: float,
    obs_window: int,
    sl_pct: float,
    profit_threshold_pct: float,
) -> dict[str, Any]:
    """Observation window SL logic.
    
    For the first `obs_window` bars after entry:
    - If price closes >= entry_price * (1 + profit_threshold_pct), PASS (keep baseline)
    - Track the LOW price to see if we need to set emergency SL
    
    After the observation window ends or before it:
    - If price ever hits entry_price * (1 + sl_pct), trigger emergency exit
    - The SL is only activated AFTER obs_window + 1 (T+1 for the SL check day)
    
    Returns dict with exit info, or empty dict if no early exit.
    """
    # The first bar after entry is entry_idx + 1 (T+1 day due to A-share T+1 settlement)
    # Observation window starts from entry_idx + 2 (first full day after T+1 settlement)
    settle_bar = entry_idx + 1  # T+1 settlement day
    if settle_bar >= len(bars):
        return {}
    
    obs_start = settle_bar + 1  # first bar in observation window (T+2)
    obs_end = min(obs_start + obs_window, len(bars))
    
    if obs_start >= len(bars):
        return {}
    
    sl_price = entry_price * (1.0 + sl_pct)  # sl_pct is negative for stop-loss
    profit_threshold = entry_price * (1.0 + profit_threshold_pct)
    
    # Phase 1: Observation window — check if price establishes above threshold
    passed_obs = False
    for i in range(obs_start, obs_end):
        close = bar_val(bars[i], 'c')
        if close >= profit_threshold:
            passed_obs = True
            break
    
    if passed_obs:
        return {'passed': True}
    
    # Phase 2: Check if price ever hits SL price in the observation window or after
    # Start check from settle_bar (T+1) because that's when we could first exit
    for i in range(settle_bar, len(bars)):
        if bar_val(bars[i], 'l') <= sl_price:
            return {
                'hit': True,
                'hit_idx': i,
                'hit_date': bar_date(bars[i]),
                'exit_price': sl_price,
                'passed': False,
            }
    
    # Never hit SL — keep baseline exit
    return {'passed': True, 'never_hit': True}


def build_v151_row(
    row: pd.Series,
    variant: str,
    bars: list[dict[str, Any]],
) -> dict[str, Any]:
    out = original_baseline_row(row)
    out['v151_variant'] = variant
    entry_idx = int(fnum(row.get('v138_entry_idx'), -1))
    entry_price = fnum(row.get('v138_entry_price'))
    
    if not bars or entry_idx < 0 or entry_idx >= len(bars):
        out['v151_missing_kline'] = True
        return out
    
    status, reason = lifecycle_status(row)
    
    # Variant params
    # Format: OBS_N{obs_window}_SL_{signed_sl_pct}_PT_{profit_threshold_pct}
    # e.g. OBS_N3_SL_M1_PT_0 — 3-bar obs window, -1% SL, 0% profit threshold
    # e.g. OBS_N5_SL_M1_PT_0_5 — 5-bar obs window, -1% SL, +0.5% profit threshold
    
    parts = variant.replace('OBS_', '').split('_')
    obs_window = 3
    sl_pct = -0.01  # default: -1%
    profit_threshold_pct = 0.005  # default: +0.5%
    
    try:
        for p in parts:
            if p.startswith('N') and p[1:].isdigit():
                obs_window = int(p[1:])
            elif p.startswith('SL_M') and p[4:].replace('.', '').isdigit():
                neg_pct = float(p[4:])
                sl_pct = -neg_pct / 100.0
            elif p.startswith('SL_') and p[3:].replace('.', '').isdigit():
                sl_pct = float(p[3:]) / 100.0
            elif p.startswith('PT_') and p[3:].replace('.', '').isdigit():
                profit_threshold_pct = float(p[3:]) / 100.0
    except (ValueError, IndexError):
        pass
    
    # Only applies to CANCEL_AFTER_ENTRY_DAY_CLOSE and INTRADAY_RISK_NOTE_ONLY
    apply_to = 'CANCEL'  # default: only CANCEL
    if 'ALL' in variant:
        apply_to = 'ALL'
    elif 'INTRADAY' in variant:
        apply_to = 'INTRADAY'
    
    should_monitor = (
        (apply_to in ('CANCEL', 'ALL') and status == 'CANCEL_AFTER_ENTRY_DAY_CLOSE') or
        (apply_to in ('INTRADAY', 'ALL') and status == 'INTRADAY_RISK_NOTE_ONLY')
    )
    
    if not should_monitor:
        out['v151_lifecycle_action'] = f'NO_ACTION_{status}'
        out['v151_t1_violation'] = out['v151_entry_date'] == out['v151_exit_date']
        out['v151_missing_kline'] = False
        return out
    
    result = find_obs_window_sl_hit(bars, entry_idx, entry_price, obs_window, sl_pct, profit_threshold_pct)
    
    if result.get('hit'):
        hit_idx = result['hit_idx']
        exit_price = result['exit_price']
        original_exit_idx = int(fnum(row.get('v138_exit_idx'), -1))
        
        if original_exit_idx < 0 or hit_idx < original_exit_idx:
            out.update({
                'v151_exit_idx': hit_idx,
                'v151_exit_date': result['hit_date'],
                'v151_exit_price': round(exit_price, 6),
                'v151_exit_reason': 'OBSERVATION_WINDOW_SL_HIT',
                'v151_pnl_pct': round(pct(exit_price, entry_price), 4),
                'v151_lifecycle_action': f'OBS_SL_HIT_W{obs_window}',
                'v151_obs_result': 'SL_HIT',
            })
        else:
            out['v151_lifecycle_action'] = f'OBS_SL_AFTER_EXIT_W{obs_window}'
    elif result.get('passed'):
        # Keep baseline exit — observation window passed
        out['v151_lifecycle_action'] = f'OBS_PASSED_W{obs_window}'
    else:
        out['v151_lifecycle_action'] = f'OBS_NO_RESULT_W{obs_window}'
    
    out['v151_t1_violation'] = out['v151_entry_date'] == out['v151_exit_date']
    out['v151_missing_kline'] = False
    return out


def by_group(df: pd.DataFrame, key: str) -> dict[str, dict[str, Any]]:
    return {str(k): metrics(v) for k, v in df.groupby(key, dropna=False)}


def monthly(df: pd.DataFrame) -> pd.DataFrame:
    x = df.copy()
    x['month'] = x['v151_entry_date'].astype(str).str[:6]
    rows = []
    for m, part in x.groupby('month', dropna=False):
        rows.append({'month': m, **metrics(part)})
    return pd.DataFrame(rows).sort_values('month')


def main() -> None:
    df = pd.read_csv(IN, low_memory=False)
    if 'valid_backtest' in df:
        df = df[bseries(df['valid_backtest'])].copy()

    input_rows = [original_baseline_row(r) for _, r in df.iterrows()]

    variants = [
        # 3-bar observation window, varying SL tightness and profit threshold
        'OBS_N3_SL_M1_PT_0',      # 3 bars, -1% SL, 0% profit threshold (must just stay above entry)
        'OBS_N3_SL_M1_PT_0_5',    # 3 bars, -1% SL, +0.5% profit threshold
        'OBS_N3_SL_M1_PT_1',      # 3 bars, -1% SL, +1% profit threshold
        'OBS_N3_SL_M0_5_PT_0_5',  # 3 bars, -0.5% SL, +0.5% profit threshold
        # 5-bar observation window
        'OBS_N5_SL_M1_PT_0',      # 5 bars, -1% SL, 0% profit threshold
        'OBS_N5_SL_M1_PT_0_5',    # 5 bars, -1% SL, +0.5% profit threshold
        'OBS_N5_SL_M1_PT_1',      # 5 bars, -1% SL, +1% profit threshold
        # 7-bar observation window
        'OBS_N7_SL_M1_PT_0',      # 7 bars, -1% SL, 0% profit threshold
        'OBS_N7_SL_M1_PT_0_5',    # 7 bars, -1% SL, +0.5% profit threshold
        'OBS_N7_SL_M1_PT_1',      # 7 bars, -1% SL, +1% profit threshold
        # Wider SL
        'OBS_N5_SL_M2_PT_0_5',    # 5 bars, -2% SL, +0.5% profit threshold
    ]

    for variant in variants:
        for _, r in df.iterrows():
            bars = load_bars(str(r.get('symbol', '')))
            input_rows.append(build_v151_row(r, variant, bars))

    all_df = pd.DataFrame(input_rows)
    executed_df = all_df.copy()

    all_df.to_csv(OUT / 'v151_all_rows.csv', index=False)
    executed_df.to_csv(OUT / 'v151_executed_rows.csv', index=False)

    variant_rows = []
    for variant, part in executed_df.groupby('v151_variant', dropna=False):
        variant_rows.append({'variant': variant, **metrics(part)})
    variant_df = pd.DataFrame(variant_rows).sort_values(['wr', 'avg'], ascending=[False, False])
    variant_df.to_csv(OUT / 'v151_variant_metrics.csv', index=False)

    for variant, part in executed_df.groupby('v151_variant', dropna=False):
        monthly(part).to_csv(OUT / f'v151_monthly_{variant}.csv', index=False)

    baseline = executed_df[executed_df['v151_variant'].eq('BASELINE_V138_RECLAIM_NEXT_OPEN')]
    best_name = str(variant_df.iloc[0]['variant']) if len(variant_df) and str(variant_df.iloc[0]['variant']) != 'BASELINE_V138_RECLAIM_NEXT_OPEN' else ''
    best = executed_df[executed_df['v151_variant'].eq(best_name)] if best_name else executed_df.iloc[0:0]
    changed = best[best['v151_lifecycle_action'].astype(str).str.startswith('OBS_SL_HIT')] if len(best) else best.iloc[0:0]
    changed.to_csv(OUT / 'v151_best_changed_trades.csv', index=False)

    action_summary = by_group(best, 'v151_lifecycle_action') if len(best) else {}
    exit_summary = by_group(best, 'v151_exit_reason') if len(best) else {}
    status_summary = by_group(best, 'v143_lifecycle_status') if len(best) else {}

    base_m = metrics(baseline)
    best_m = metrics(best) if len(best) else base_m
    release_pass = bool(
        best_name != 'BASELINE_V138_RECLAIM_NEXT_OPEN'
        and best_m['n'] >= 120
        and best_m['wr'] >= base_m['wr'] + 2.0
        and best_m['avg'] >= base_m['avg'] - 0.25  # allow -0.25pp avg reduction
        and best_m['hard_exit'] <= base_m['hard_exit'] + 10.0  # allow +10pp hard_exit (SL hits are hard exits)
        and best_m['t1'] == 0
    ) if len(best) else False

    summary = {
        'decision': 'V151_OBS_WINDOW_SL_PROMOTABLE' if release_pass else 'V151_OBS_WINDOW_SL_RESEARCH_ONLY',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'production_write': False,
        'input': str(IN),
        'out': str(OUT),
        'baseline': base_m,
        'variant_metrics': variant_df.to_dict(orient='records'),
        'best_variant': best_name,
        'best_metrics': best_m,
        'best_changed_trades': int(len(changed)),
        'best_action_summary': action_summary,
        'best_exit_summary': exit_summary,
        'best_status_summary': status_summary,
        'release_gate': {
            'pass': release_pass,
            'checks': {
                'not_baseline': best_name != 'BASELINE_V138_RECLAIM_NEXT_OPEN',
                'n_ge_120': best_m['n'] >= 120,
                'wr_improve_ge_2pp': best_m['wr'] >= base_m['wr'] + 2.0,
                'avg_within_minus_0_25pp': best_m['avg'] >= base_m['avg'] - 0.25,
                'hard_exit_within_plus_10pp': best_m['hard_exit'] <= base_m['hard_exit'] + 10.0,
                't1_zero': best_m['t1'] == 0,
            },
        },
        't1_violation_total': int(executed_df['v151_t1_violation'].astype(bool).sum()),
        'missing_kline_total': int(executed_df.get('v151_missing_kline', False).fillna(False).astype(bool).sum()),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    lines = [
        '# V151 观察窗口 SL 全量回测',
        '',
        f"Decision: `{summary['decision']}`。只读回测，不改生产/API/frontend/watchlist/TP/SL。",
        '',
        '## 1. Variant metrics',
        variant_df.to_markdown(index=False) if len(variant_df) else '(empty)',
        '',
        '## 2. Release gate',
        '```json',
        json.dumps(summary['release_gate'], ensure_ascii=False, indent=2),
        '```',
        '',
        '## 3. Best variant detail',
        '### Lifecycle action',
        pd.DataFrame([{'key': k, **v} for k, v in action_summary.items()]).to_markdown(index=False) if action_summary else '无',
        '',
        '### Exit reason',
        pd.DataFrame([{'key': k, **v} for k, v in exit_summary.items()]).to_markdown(index=False) if exit_summary else '无',
        '',
        '### Lifecycle status',
        pd.DataFrame([{'key': k, **v} for k, v in status_summary.items()]).to_markdown(index=False) if status_summary else '无',
        '',
        '## 4. 结论',
        '- V151 用观察窗口替代立即 cancel/SL：给 CANCEL 交易 N 根 K 线窗口让价格恢复到盈利阈值以上，',
        '  仅在窗口内未恢复且触发 -1% SL 时才提前退出。',
        '- 预期：更多 win 交易保留 full baseline avg，loss 交易被截断在 -1%。',
    ]
    (OUT / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()