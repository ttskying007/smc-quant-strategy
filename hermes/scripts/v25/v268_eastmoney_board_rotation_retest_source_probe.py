#!/usr/bin/env python3
"""V268 no-write: Eastmoney thematic-board rotation + stock retest source-layer probe.

This is the next layer after V267 industry-classification rotation failed:
use Eastmoney concept/sector board membership (more granular than CSRC industry)
as the cross-sectional source layer. No production/frontend/watchlist writes.
"""
from __future__ import annotations

import glob
import json
import math
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

import pandas as pd

from v267_industry_rotation_retest_source_probe import (
    BASE, KLINE_DIR, BASELINE, PROD, RESEARCH, add_key, fnum, metrics, pass_gate,
    simulate_exit, symbol_from_path,
)

BOARD = BASE / 'smc_audit/v191_eastmoney_board_members_cache.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = BASE / f'smc_audit/v268_eastmoney_board_rotation_retest_source_no_write_{TS}'
LATEST = BASE / 'smc_audit/v268_eastmoney_board_rotation_retest_source_latest.json'


def load_board_maps() -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    raw = json.loads(BOARD.read_text())['boards']
    boards = {bid: {'name': b.get('name', bid), 'members': [str(x) for x in b.get('members', []) if '.' in str(x)], 'n': int(b.get('n', 0) or 0)} for bid, b in raw.items()}
    sym_boards: dict[str, list[str]] = defaultdict(list)
    for bid, b in boards.items():
        if len(b['members']) < 8:
            continue
        for sym in b['members']:
            sym_boards[sym].append(bid)
    return boards, dict(sym_boards)


def load_all_bars(sym_boards: dict[str, list[str]]) -> dict[str, list[dict[str, Any]]]:
    out = {}
    for p in glob.glob(str(KLINE_DIR / '*_daily_750.json')):
        sym = symbol_from_path(p)
        if sym not in sym_boards:
            continue
        try:
            arr = json.loads(Path(p).read_text())
        except Exception:
            continue
        bars = []
        for b in arr:
            c = fnum(b.get('c'))
            if c > 0:
                bars.append({'t': str(b.get('t', b.get('date', '')))[:8], 'o': fnum(b.get('o')), 'h': fnum(b.get('h')), 'l': fnum(b.get('l')), 'c': c, 'v': fnum(b.get('v'))})
        if len(bars) >= 120:
            out[sym] = bars
    return out


def build_board_features(symbol_bars: dict[str, list[dict[str, Any]]], sym_boards: dict[str, list[str]], boards: dict[str, dict[str, Any]]) -> dict[tuple[str, str], dict[str, float]]:
    agg: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {'n': 0, 'ret5': 0.0, 'ret20': 0.0, 'above20': 0, 'above60': 0, 'limitup': 0, 'turnover': 0.0})
    for sym, bars in symbol_bars.items():
        closes = [b['c'] for b in bars]
        bids = sym_boards.get(sym, [])
        if not bids:
            continue
        for i in range(60, len(bars)):
            c = closes[i]
            ma20 = sum(closes[i-19:i+1]) / 20
            ma60 = sum(closes[i-59:i+1]) / 60
            ret5 = (c / closes[i-5] - 1) * 100
            ret20 = (c / closes[i-20] - 1) * 100
            limitup = int(c / closes[i-1] - 1 >= 0.095)
            turnover = c * bars[i]['v']
            for bid in bids:
                a = agg[(bid, bars[i]['t'])]
                a['n'] += 1; a['ret5'] += ret5; a['ret20'] += ret20; a['above20'] += int(c > ma20); a['above60'] += int(c > ma60); a['limitup'] += limitup; a['turnover'] += turnover
    feats: dict[tuple[str, str], dict[str, float]] = {}
    by_date: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for key, a in agg.items():
        n = max(a['n'], 1)
        if n < 8:
            continue
        f = {
            'board_id': key[0], 'board_name': boards.get(key[0], {}).get('name', key[0]), 'board_n': n,
            'board_ret5': a['ret5'] / n, 'board_ret20': a['ret20'] / n,
            'board_breadth20': a['above20'] / n * 100, 'board_breadth60': a['above60'] / n * 100,
            'board_limitup_pct': a['limitup'] / n * 100, 'board_turnover': a['turnover'],
        }
        feats[key] = f; by_date[key[1]].append((key[0], f))
    for date, rows in by_date.items():
        for col, rank_col in [('board_ret5', 'board_rank_ret5'), ('board_ret20', 'board_rank_ret20'), ('board_turnover', 'board_rank_turnover')]:
            for rank, (bid, _) in enumerate(sorted(rows, key=lambda x: x[1][col], reverse=True), 1):
                feats[(bid, date)][rank_col] = rank
    return feats


def best_board_feature(sym: str, date: str, sym_boards: dict[str, list[str]], feats: dict[tuple[str, str], dict[str, float]]) -> dict[str, Any] | None:
    cand = [feats[(bid, date)] for bid in sym_boards.get(sym, []) if (bid, date) in feats]
    if not cand:
        return None
    # prioritize real rotation: rank + breadth + limit-up participation
    return sorted(cand, key=lambda f: (-(1000 - f.get('board_rank_ret5', 999)), f.get('board_breadth20', 0), f.get('board_limitup_pct', 0), f.get('board_ret5', 0)), reverse=True)[0]


def generate(symbol_bars: dict[str, list[dict[str, Any]]], sym_boards: dict[str, list[str]], feats: dict[tuple[str, str], dict[str, float]]) -> pd.DataFrame:
    rows = []
    for sym, bars in symbol_bars.items():
        closes = [b['c'] for b in bars]; vols = [b['v'] for b in bars]
        for i in range(80, len(bars) - 2):
            event = bars[i]
            bf = best_board_feature(sym, event['t'], sym_boards, feats)
            if not bf or bf.get('board_n', 0) < 8:
                continue
            # prefilter source layer before stock pattern: top thematic rotation or broad board participation
            if not (bf.get('board_rank_ret5', 999) <= 25 or (bf.get('board_breadth20', 0) >= 60 and bf.get('board_ret5', 0) >= 2.0)):
                continue
            prev40_high = max(x['h'] for x in bars[i-40:i])
            prev20_low = min(x['l'] for x in bars[i-20:i])
            if event['c'] <= prev40_high:
                continue
            event_ret = (event['c'] / closes[i-1] - 1) * 100
            if event_ret < 2.5:
                continue
            zone_low = prev40_high; zone_high = event['c']
            zone_width = (zone_high / max(zone_low, 1e-9) - 1) * 100
            if zone_width <= 0 or zone_width > 16:
                continue
            for r in range(i + 1, min(i + 9, len(bars) - 1)):
                rb = bars[r]
                touched = rb['l'] <= zone_high and rb['l'] >= zone_low * 0.985
                reclaimed = rb['c'] > (zone_low + zone_high) / 2 and rb['c'] > rb['o']
                if not (touched and reclaimed):
                    continue
                entry_idx = r + 1; entry = bars[entry_idx]; entry_price = entry['o']
                retest_low = min(x['l'] for x in bars[i+1:r+1])
                sl = min(zone_low, retest_low) * 0.99
                risk_pct = (entry_price / max(sl, 1e-9) - 1) * 100
                if risk_pct <= 1.0 or risk_pct > 8.0:
                    continue
                tp = entry_price + (entry_price - sl) * 1.8
                ex = simulate_exit(bars, entry_idx, entry_price, sl, tp)
                pre_vol20 = sum(vols[i-20:i]) / 20
                row = {
                    'symbol': sym, 'event_type': 'EASTMONEY_BOARD_ROTATION_BREAK_RETEST', 'event_date': event['t'], 'event_idx': i,
                    'reclaim_date': rb['t'], 'reclaim_idx': r, 'entry_idx': entry_idx, 'entry_date': entry['t'], 'entry_date_s': entry['t'], 'entry_price': round(entry_price, 4),
                    'event_ret_pct': round(event_ret, 4), 'event_body_pct': round((event['c'] - event['o']) / max(event['h'] - event['l'], 1e-9) * 100, 4),
                    'event_volr20': round(event['v'] / max(pre_vol20, 1e-9), 4), 'prev20_range_pct': round((max(x['h'] for x in bars[i-20:i]) / max(prev20_low, 1e-9) - 1) * 100, 4),
                    'zone_width_pct': round(zone_width, 4), 'pullback_depth_pct': round((zone_high / max(retest_low, 1e-9) - 1) * 100, 4),
                    'event_to_reclaim_bars': r - i, 'reclaim_close_pos_pct': round((rb['c'] - rb['l']) / max(rb['h'] - rb['l'], 1e-9) * 100, 4),
                    'entry_chase_vs_zone_high_pct': round((entry_price / max(zone_high, 1e-9) - 1) * 100, 4), 'risk_pct': round(risk_pct, 4), 'tp': round(tp, 4), 'sl': round(sl, 4),
                    'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
                    **{k: round(v, 4) if isinstance(v, float) else v for k, v in bf.items()}, **ex,
                }
                row['_key'] = row['symbol'] + '|' + row['entry_date_s']
                rows.append(row)
                break
    return pd.DataFrame(rows).drop_duplicates('_key', keep='first') if rows else pd.DataFrame()


def mask(df: pd.DataFrame, preds: tuple[tuple[str, str, Any], ...]) -> pd.Series:
    m = pd.Series(True, index=df.index)
    for col, op, val in preds:
        x = pd.to_numeric(df[col], errors='coerce')
        if op == '>=': m &= x >= float(val)
        elif op == '<=': m &= x <= float(val)
    return m


def frontier(child: pd.DataFrame, base: pd.DataFrame) -> pd.DataFrame:
    atoms = [
        ('board_rank_ret5', '<=', 5), ('board_rank_ret5', '<=', 10), ('board_rank_ret5', '<=', 20), ('board_rank_ret20', '<=', 15), ('board_rank_turnover', '<=', 20),
        ('board_ret5', '>=', 2.0), ('board_ret5', '>=', 4.0), ('board_ret20', '>=', 5.0), ('board_breadth20', '>=', 55), ('board_breadth20', '>=', 70), ('board_breadth60', '>=', 45),
        ('board_limitup_pct', '>=', 3.0), ('event_ret_pct', '>=', 5.0), ('event_body_pct', '>=', 60), ('event_volr20', '>=', 1.2), ('zone_width_pct', '<=', 10),
        ('pullback_depth_pct', '<=', 8), ('event_to_reclaim_bars', '<=', 5), ('reclaim_close_pos_pct', '>=', 60), ('entry_chase_vs_zone_high_pct', '<=', 3), ('risk_pct', '<=', 5),
    ]
    combos = [(a,) for a in atoms] + list(combinations(atoms, 2)) + list(combinations(atoms, 3))
    rows = []
    for preds in combos:
        s = child[mask(child, preds)].copy()
        if len(s) < 20:
            continue
        sm = metrics(s)
        if sm.get('wr', 0) < 55 or sm.get('avg', -99) < 1.0:
            continue
        cm = metrics(pd.concat([base, s], ignore_index=True, sort=False).drop_duplicates('_key', keep='first'))
        rows.append({'rule': ' AND '.join(f'{c} {op} {v}' for c, op, v in preds), 'pred_count': len(preds), 'child_n': sm.get('n'), 'child_wr': sm.get('wr'), 'child_avg': sm.get('avg'), 'combined_n': cm.get('n'), 'combined_wr': cm.get('wr'), 'combined_avg': cm.get('avg'), 'combined_min_year_n': cm.get('min_year_n'), 'combined_all_year_wr_min': cm.get('all_year_wr_min'), 'combined_micro': cm.get('micro'), 'combined_weak_month_count': cm.get('weak_month_count'), 'combined_prod_pass': pass_gate(cm, PROD), 'combined_research_pass': pass_gate(cm, RESEARCH)})
    fr = pd.DataFrame(rows)
    return fr.sort_values(['combined_prod_pass', 'combined_research_pass', 'combined_wr', 'combined_avg', 'child_wr'], ascending=[False, False, False, False, False]) if not fr.empty else fr


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    boards, sym_boards = load_board_maps()
    bars = load_all_bars(sym_boards)
    feats = build_board_features(bars, sym_boards, boards)
    base = add_key(pd.read_csv(BASELINE, low_memory=False))
    all_df = generate(bars, sym_boards, feats)
    if all_df.empty:
        raise SystemExit('no candidates generated')
    child = all_df[~all_df['_key'].isin(set(base['_key']))].copy()
    latest = str(all_df['entry_date_s'].max())
    cut = str((pd.to_datetime(latest) - pd.Timedelta(days=45)).strftime('%Y%m%d'))
    current = child[child['entry_date_s'] >= cut].copy()
    fr = frontier(child, base)
    all_df.to_csv(OUT / 'v268_all_board_rotation_retest_candidates.csv', index=False)
    current.to_csv(OUT / 'v268_current_recent45_candidates.csv', index=False)
    fr.to_csv(OUT / 'v268_frontier.csv', index=False)
    raw_combined = pd.concat([base, child], ignore_index=True, sort=False).drop_duplicates('_key', keep='first')
    summary = {
        'version': 'V268_EASTMONEY_BOARD_ROTATION_RETEST_SOURCE_NO_WRITE', 'generated_at': datetime.now().isoformat(timespec='seconds'), 'out_dir': str(OUT), 'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'inputs': {'baseline': str(BASELINE), 'board_cache': str(BOARD), 'boards': len(boards), 'symbols_with_boards': len(sym_boards), 'kline_files': len(bars)}, 'gates': {'production': PROD, 'research': RESEARCH},
        'baseline_metrics': metrics(base), 'generated': {'all_candidates': int(len(all_df)), 'historical_nonoverlap_vs_baseline': int(len(child)), 'current_recent45_candidates': int(len(current)), 'latest_entry_date': latest, 'current_cut': cut},
        'raw_generator_metrics': {'child': metrics(child), 'combined': metrics(raw_combined)}, 'rules_tested_after_prefilter': int(len(fr)), 'production_pass_count': int(fr['combined_prod_pass'].sum()) if not fr.empty else 0, 'research_pass_count': int(fr['combined_research_pass'].sum()) if not fr.empty else 0,
        'top_candidates': fr.head(20).to_dict('records') if not fr.empty else [],
        'current_breakdown': {'by_board_top10': current['board_name'].value_counts().head(10).to_dict() if not current.empty else {}, 'avg_board_ret5': round(pd.to_numeric(current['board_ret5'], errors='coerce').mean(), 4) if not current.empty else None, 'avg_board_breadth20': round(pd.to_numeric(current['board_breadth20'], errors='coerce').mean(), 4) if not current.empty else None},
        'decision': 'NO_PROMOTION__EASTMONEY_BOARD_ROTATION_RETEST_DOES_NOT_PASS_FRONTIER',
        'next_research_direction': ['If V268 fails like V267, daily-derived sector/theme rotation proxies are exhausted.', 'Next concrete source must be real historical intraday/board-fund/auction data; otherwise continue only with V185 production monitoring and weak-month diagnostics.'],
    }
    if summary['production_pass_count'] > 0 and summary['generated']['current_recent45_candidates'] > 0:
        summary['decision'] = 'HISTORICAL_FRONTIER_FOUND__REQUIRES_INDEPENDENT_AUDIT_AND_CURRENT_SELECTOR_SMOKE__NO_WRITE'
    elif summary['research_pass_count'] > 0:
        summary['decision'] = 'RESEARCH_FRONTIER_ONLY__NO_WRITE'
    (OUT / 'v268_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
