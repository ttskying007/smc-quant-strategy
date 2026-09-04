#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

SRC = Path('/root/.hermes/smc_opt_v95_exit_contract_autopsy/v95_exit_autopsy_rows.json')
OUT = Path('/root/.hermes/smc_opt_v96_runner_sl_split_autopsy')
OUT.mkdir(parents=True, exist_ok=True)

ENGINE = 'V96_RUNNER_SL_SPLIT_AUTOPSY'


def num(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or x == '':
            return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_key(v: Any) -> str:
    return ''.join(ch for ch in str(v or '') if ch.isdigit())[:8]


def runner_class(r: Dict[str, Any]) -> str:
    if r.get('exit_reason') != 'RUNNER_TRAIL':
        return 'NOT_RUNNER'
    up3 = num(r.get('post_3d_max_high_ret_pct'))
    up5 = num(r.get('post_5d_max_high_ret_pct'))
    up10 = num(r.get('post_10d_max_high_ret_pct'))
    up20 = num(r.get('post_20d_max_high_ret_pct'))
    down5 = num(r.get('post_5d_min_low_ret_pct'))
    down10 = num(r.get('post_10d_min_low_ret_pct'))
    down20 = num(r.get('post_20d_min_low_ret_pct'))
    close20 = num(r.get('post_20d_close_ret_pct'))

    # 趋势延续：卖出后很快/持续给出上行空间，且不是先大幅下杀。
    if up5 >= 5 and down5 > -3:
        return 'RUNNER_TREND_CONTINUATION_FAST'
    if up10 >= 8 and down10 > -5 and close20 > 0:
        return 'RUNNER_TREND_CONTINUATION_STABLE'
    if up20 >= 10 and close20 > 5 and down20 > -8:
        return 'RUNNER_TREND_CONTINUATION_SLOW'

    # 冲高回落：确实有冲高，但随后回撤深，说明不能简单放宽runner。
    if up10 >= 5 and down20 <= -8:
        return 'RUNNER_SPIKE_THEN_DEEP_PULLBACK'
    if up20 >= 10 and down20 <= -10:
        return 'RUNNER_SPIKE_THEN_CRASH'

    # 卖出正确/保护：后续没有足够上行，或下跌风险更大。
    if up20 < 5 and down20 <= -5:
        return 'RUNNER_EXIT_PROTECTIVE_NO_FOLLOW_THROUGH'
    if up20 < 5:
        return 'RUNNER_EXIT_OK_NO_FOLLOW_THROUGH'
    return 'RUNNER_MIXED_CHOP_NEEDS_DYNAMIC_TRAIL'


def sl_class_v96(r: Dict[str, Any]) -> str:
    if r.get('exit_reason') != 'SL_HIT':
        return 'NOT_SL'
    up3 = num(r.get('post_3d_max_high_ret_pct'))
    up5 = num(r.get('post_5d_max_high_ret_pct'))
    up10 = num(r.get('post_10d_max_high_ret_pct'))
    up20 = num(r.get('post_20d_max_high_ret_pct'))
    down3 = num(r.get('post_3d_min_low_ret_pct'))
    down5 = num(r.get('post_5d_min_low_ret_pct'))
    down10 = num(r.get('post_10d_min_low_ret_pct'))
    down20 = num(r.get('post_20d_min_low_ret_pct'))
    mfe = num(r.get('mfe_r'))
    mae = abs(num(r.get('mae_r')))

    # SL位置不合理/被洗：止损后不再明显下杀，快速反弹，说明invalid点放得太近。
    if up5 >= 5 and down5 > -3:
        return 'SL_POSITION_TOO_TIGHT_FAST_REBOUND'
    if up10 >= 8 and down10 > -5:
        return 'SL_POSITION_TOO_TIGHT_REBOUND'
    if up20 >= 10 and down20 > -6:
        return 'SL_POSITION_TOO_TIGHT_SLOW_REBOUND'

    # 入场太早：止损后继续杀，但后面又大反弹，说明方向可能对，但入场确认不足/过早。
    if down5 <= -5 and up20 >= 10:
        return 'ENTRY_TOO_EARLY_WASHOUT_THEN_REBOUND'
    if down10 <= -8 and up20 >= 8:
        return 'ENTRY_TOO_EARLY_DEEP_WASHOUT'
    if mae >= 1.2 and mfe < 0.8 and up20 >= 5:
        return 'ENTRY_TOO_EARLY_NO_INITIAL_PROOF'

    # 保护性SL：止损后继续走坏且没有有效收复。
    if up20 < 5 and down20 <= -5:
        return 'PROTECTIVE_SL_VALID_CONTINUED_DOWN'
    if up20 < 2:
        return 'PROTECTIVE_SL_VALID_NO_RECLAIM'

    return 'SL_BORDERLINE_RECLAIM_NOT_ENOUGH'


def action_for_runner(cls: str) -> str:
    return {
        'RUNNER_TREND_CONTINUATION_FAST': 'V97候选: 放宽runner，TP2后至少给5日/结构跟踪；不应次日锁死',
        'RUNNER_TREND_CONTINUATION_STABLE': 'V97候选: 使用结构低点/2R宽trail，避免过早出局',
        'RUNNER_TREND_CONTINUATION_SLOW': 'V97观察: 延迟确认后再放宽，需防慢涨前回撤',
        'RUNNER_SPIKE_THEN_DEEP_PULLBACK': '保持动态trail，不可无限持有；适合冲高分批卖',
        'RUNNER_SPIKE_THEN_CRASH': '保持快速锁利；不适合放宽',
        'RUNNER_EXIT_PROTECTIVE_NO_FOLLOW_THROUGH': '当前退出合理',
        'RUNNER_EXIT_OK_NO_FOLLOW_THROUGH': '当前退出基本合理',
        'RUNNER_MIXED_CHOP_NEEDS_DYNAMIC_TRAIL': '需要market_state/volatility二级门禁',
    }.get(cls, '')


def action_for_sl(cls: str) -> str:
    return {
        'SL_POSITION_TOO_TIGHT_FAST_REBOUND': 'V97候选: SL放到zone_low/结构低点外，或给一次日内/次日确认',
        'SL_POSITION_TOO_TIGHT_REBOUND': 'V97候选: 轻微扩大SL buffer，不改入场',
        'SL_POSITION_TOO_TIGHT_SLOW_REBOUND': '观察: 慢反弹，不能直接扩大所有SL',
        'ENTRY_TOO_EARLY_WASHOUT_THEN_REBOUND': '改入场确认: 等二次reclaim/次日站回zone，不是放宽SL',
        'ENTRY_TOO_EARLY_DEEP_WASHOUT': '改入场确认或降级watch，不是放宽SL',
        'ENTRY_TOO_EARLY_NO_INITIAL_PROOF': '要求入场后1-2日有效证明，否则不进',
        'PROTECTIVE_SL_VALID_CONTINUED_DOWN': '保留SL',
        'PROTECTIVE_SL_VALID_NO_RECLAIM': '保留SL',
        'SL_BORDERLINE_RECLAIM_NOT_ENOUGH': '边界样本，需看信号/zone质量',
    }.get(cls, '')


def metrics(rows: List[Dict[str, Any]], pnl_key='pnl_pct') -> Dict[str, Any]:
    if not rows:
        return {'n': 0}
    vals = [num(r.get(pnl_key)) for r in rows]
    n = len(rows)
    def avg(k: str) -> float:
        xs = [num(r.get(k)) for r in rows if r.get(k) is not None]
        return round(mean(xs), 4) if xs else 0.0
    def med(k: str) -> float:
        xs = [num(r.get(k)) for r in rows if r.get(k) is not None]
        return round(median(xs), 4) if xs else 0.0
    return {
        'n': n,
        'wr': round(sum(v > 0 for v in vals) / n * 100, 2),
        'avg_pnl': round(mean(vals), 4),
        'cum_pnl': round(sum(vals), 2),
        'avg_post5_up': avg('post_5d_max_high_ret_pct'),
        'avg_post10_up': avg('post_10d_max_high_ret_pct'),
        'avg_post20_up': avg('post_20d_max_high_ret_pct'),
        'med_post20_up': med('post_20d_max_high_ret_pct'),
        'avg_post20_down': avg('post_20d_min_low_ret_pct'),
        'post20_up_gt5_rate': round(sum(num(r.get('post_20d_max_high_ret_pct')) >= 5 for r in rows) / n * 100, 2),
        'post20_up_gt10_rate': round(sum(num(r.get('post_20d_max_high_ret_pct')) >= 10 for r in rows) / n * 100, 2),
        'post20_down_gt5_rate': round(sum(num(r.get('post_20d_min_low_ret_pct')) <= -5 for r in rows) / n * 100, 2),
        'avg_v95_delta': avg('v95_delta_pnl_pct'),
    }


def bucket(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    g = defaultdict(list)
    for r in rows:
        g[str(r.get(key))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0]))}


def compact_examples(rows: List[Dict[str, Any]], sort_key: str, n=12) -> List[Dict[str, Any]]:
    out = []
    for r in sorted(rows, key=lambda x: num(x.get(sort_key)), reverse=True)[:n]:
        out.append({
            'symbol': r.get('symbol'),
            'entry_date': r.get('entry_date'),
            'exit_date': r.get('exit_date'),
            'exit_reason': r.get('exit_reason'),
            'pnl_pct': r.get('pnl_pct'),
            'post_5d_up': r.get('post_5d_max_high_ret_pct'),
            'post_10d_up': r.get('post_10d_max_high_ret_pct'),
            'post_20d_up': r.get('post_20d_max_high_ret_pct'),
            'post_20d_down': r.get('post_20d_min_low_ret_pct'),
            'runner_class_v96': r.get('runner_class_v96'),
            'sl_class_v96': r.get('sl_class_v96'),
            'v96_action': r.get('v96_action'),
        })
    return out


def main() -> None:
    rows = json.loads(SRC.read_text())
    out_rows = []
    for r in rows:
        nr = dict(r)
        nr['runner_class_v96'] = runner_class(nr)
        nr['sl_class_v96'] = sl_class_v96(nr)
        nr['v96_action'] = action_for_runner(nr['runner_class_v96']) if nr.get('exit_reason') == 'RUNNER_TRAIL' else action_for_sl(nr['sl_class_v96']) if nr.get('exit_reason') == 'SL_HIT' else ''
        out_rows.append(nr)

    runners = [r for r in out_rows if r.get('exit_reason') == 'RUNNER_TRAIL']
    sls = [r for r in out_rows if r.get('exit_reason') == 'SL_HIT']
    report = {
        'engine': ENGINE,
        'source': str(SRC),
        'scope': {'total_rows': len(out_rows), 'runner_trail_rows': len(runners), 'sl_hit_rows': len(sls)},
        'runner_split_counts': dict(Counter(r['runner_class_v96'] for r in runners)),
        'runner_split_metrics': bucket(runners, 'runner_class_v96'),
        'sl_split_counts': dict(Counter(r['sl_class_v96'] for r in sls)),
        'sl_split_metrics': bucket(sls, 'sl_class_v96'),
        'runner_action_groups': dict(Counter(r['v96_action'] for r in runners)),
        'sl_action_groups': dict(Counter(r['v96_action'] for r in sls)),
        'top_runner_trend_continuation': compact_examples([r for r in runners if 'TREND_CONTINUATION' in r['runner_class_v96']], 'post_20d_max_high_ret_pct', 20),
        'top_runner_spike_pullback': compact_examples([r for r in runners if 'SPIKE' in r['runner_class_v96']], 'post_20d_max_high_ret_pct', 20),
        'top_sl_position_too_tight': compact_examples([r for r in sls if 'POSITION_TOO_TIGHT' in r['sl_class_v96']], 'post_20d_max_high_ret_pct', 20),
        'top_sl_entry_too_early': compact_examples([r for r in sls if 'ENTRY_TOO_EARLY' in r['sl_class_v96']], 'post_20d_max_high_ret_pct', 20),
        'validation': {
            'runner_count_ok': len(runners) == 404,
            'sl_count_ok': len(sls) == 69,
            'all_runner_classified': all(r['runner_class_v96'] != 'NOT_RUNNER' for r in runners),
            'all_sl_classified': all(r['sl_class_v96'] != 'NOT_SL' for r in sls),
            'all_actions_present': all(bool(r['v96_action']) for r in runners + sls),
        }
    }

    (OUT / 'v96_runner_sl_split_rows.json').write_text(json.dumps(out_rows, ensure_ascii=False, indent=2))
    (OUT / 'v96_runner_sl_split_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    with (OUT / 'v96_runner_sl_split_rows.csv').open('w', newline='') as fp:
        fields = sorted({k for r in out_rows for k in r if k != 'v95_exit_legs'})
        w = csv.DictWriter(fp, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(out_rows)
    print(json.dumps({
        'engine': ENGINE,
        'scope': report['scope'],
        'runner_split_counts': report['runner_split_counts'],
        'sl_split_counts': report['sl_split_counts'],
        'validation': report['validation'],
        'out': str(OUT),
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
