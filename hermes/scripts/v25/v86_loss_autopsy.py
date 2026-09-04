#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List

from v81_contextual_smc_generator import f
from v81_full_market_scan import KLINE_DIR, load_json, metrics, symbol_from_path

TRADES = Path('/root/.hermes/smc_opt_v85_production_gate/v85_trades.json')
OUT = Path('/root/.hermes/smc_opt_v86_loss_autopsy')
OUT.mkdir(parents=True, exist_ok=True)


def kline_path(symbol: str) -> Path:
    return KLINE_DIR / f"{symbol.replace('.', '_')}_daily_750.json"


def pct(a: float, b: float) -> float:
    return round(a / b * 100, 4) if b else 0.0


def safe_date(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '')[:8]


def bucket(rows: Iterable[Dict[str, Any]], key) -> Dict[str, Any]:
    g: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        g[str(key(r))].append(r)
    return {k: metrics(v) for k, v in sorted(g.items())}


def enrich_trade(t: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    r = dict(t)
    ei = int(f(r.get('entry_idx'), -1))
    xi = int(f(r.get('exit_idx'), -1))
    zl = f(r.get('zone_low'))
    zh = f(r.get('zone_high'))
    entry = f(r.get('entry_price'))
    exitp = f(r.get('exit_price'))
    pre = ks[max(0, ei - 5):ei] if ei >= 0 else []
    post = ks[ei:min(len(ks), ei + 6)] if ei >= 0 else []
    horizon = ks[ei:min(len(ks), ei + 21)] if ei >= 0 else []
    r['zone_width_pct_calc'] = round((zh / zl - 1) * 100, 4) if zl and zh else 999
    r['entry_above_zone_high_pct'] = round((entry / zh - 1) * 100, 4) if entry and zh else 999
    r['entry_above_cost_pct'] = round((entry / f(r.get('smart_money_cost'), entry) - 1) * 100, 4) if entry else 999
    r['pre5_low_vs_zone_low_pct'] = round((min((f(b.get('l')) for b in pre), default=zl) / zl - 1) * 100, 4) if zl else 999
    r['post3_min_low_vs_zone_low_pct'] = round((min((f(b.get('l')) for b in post[:3]), default=zl) / zl - 1) * 100, 4) if zl else 999
    r['post3_close_break'] = any(f(b.get('c')) < zl for b in post[:3]) if zl else False
    r['post5_close_break'] = any(f(b.get('c')) < zl for b in post[:5]) if zl else False
    r['mfe_20_pct'] = round((max((f(b.get('h')) for b in horizon), default=entry) / entry - 1) * 100, 4) if entry else 0
    r['mae_20_pct'] = round((min((f(b.get('l')) for b in horizon), default=entry) / entry - 1) * 100, 4) if entry else 0
    r['mfe_to_r'] = round(r['mfe_20_pct'] / max(f(r.get('risk_pct')), 0.0001), 4)
    r['mae_to_r'] = round(abs(r['mae_20_pct']) / max(f(r.get('risk_pct')), 0.0001), 4)
    r['exit_gap_from_zone_low_pct'] = round((exitp / zl - 1) * 100, 4) if exitp and zl else 999
    r['bar_after_entry_close_gt_entry'] = bool(len(post) > 1 and f(post[1].get('c')) > entry)
    r['entry_bar_red'] = bool(0 <= ei < len(ks) and f(ks[ei].get('c')) < f(ks[ei].get('o')))
    r['takeover_to_entry_bars'] = int(f(r.get('entry_idx'), 0) - f(r.get('v83_takeover_idx'), r.get('reclaim_idx') or 0))
    r['touch_to_reclaim_bars'] = int(f(r.get('reclaim_idx'), 0) - f(r.get('touch_idx'), 0))
    return r


def quantile(vals: List[float], q: float) -> float:
    if not vals:
        return 0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round((len(s)-1)*q))))
    return round(s[idx], 4)


def numeric_split(rows: List[Dict[str, Any]], field: str, cuts: List[float]) -> Dict[str, Any]:
    out = {}
    last = None
    for c in cuts + [None]:
        if last is None and c is not None:
            sub = [r for r in rows if f(r.get(field), 999999) <= c]
            label = f'{field}<= {c}'
        elif c is None:
            sub = [r for r in rows if f(r.get(field), -999999) > last]
            label = f'{field}> {last}'
        else:
            sub = [r for r in rows if last < f(r.get(field), 999999) <= c]
            label = f'{last}< {field}<= {c}'
        out[label] = metrics(sub)
        last = c if c is not None else last
    return out


def per_trade_diagnosis(r: Dict[str, Any]) -> str:
    if r.get('exit_reason') == 'EXIT_TREND_STRUCTURE_DAMAGE':
        if r.get('market_state') == 'RECOVERY':
            return 'RECOVERY_TREND_DAMAGE_WEAK_ENV'
        return 'TREND_DAMAGE_AFTER_ENTRY'
    if r.get('exit_reason') == 'EXIT_POI_CLOSE_BREAK':
        if r.get('market_state') == 'RECOVERY':
            return 'RECOVERY_POI_CLOSE_BREAK'
        if f(r.get('entry_above_zone_high_pct')) > 0.4:
            return 'ENTRY_TOO_FAR_ABOVE_POI_THEN_BREAK'
        if r.get('post3_close_break'):
            return 'EARLY_POI_CLOSE_BREAK_WITHIN_3BARS'
        return 'LATE_POI_CLOSE_BREAK'
    if f(r.get('pnl_pct')) <= 0:
        return 'OTHER_LOSS'
    return 'WIN'


def main() -> None:
    rows = load_json(TRADES)
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    enriched = []
    for t in rows:
        sym = str(t.get('symbol'))
        if sym not in kcache:
            p = kline_path(sym)
            kcache[sym] = load_json(p) if p.exists() else []
        r = enrich_trade(t, kcache[sym])
        r['v86_loss_diagnosis'] = per_trade_diagnosis(r)
        enriched.append(r)

    losses = [r for r in enriched if f(r.get('pnl_pct')) <= 0]
    wins = [r for r in enriched if f(r.get('pnl_pct')) > 0]
    report = {
        'engine': 'V86_LOSS_AUTOPSY_FOR_V85',
        'source': str(TRADES),
        'all_metrics': metrics(enriched),
        'loss_metrics': metrics(losses),
        'loss_count': len(losses),
        'win_count': len(wins),
        'loss_by_diagnosis': bucket(losses, lambda r: r.get('v86_loss_diagnosis')),
        'loss_by_exit_reason': bucket(losses, lambda r: r.get('exit_reason')),
        'loss_by_year': bucket(losses, lambda r: str(r.get('entry_date',''))[:4]),
        'loss_by_path': bucket(losses, lambda r: r.get('v85_path')),
        'loss_by_market_state': bucket(losses, lambda r: r.get('market_state')),
        'loss_by_substate': bucket(losses, lambda r: r.get('v85_market_substate')),
        'all_by_market_state': bucket(enriched, lambda r: r.get('market_state')),
        'all_by_path': bucket(enriched, lambda r: r.get('v85_path')),
        'all_by_exit_reason': bucket(enriched, lambda r: r.get('exit_reason')),
        'numeric_buckets': {
            'zone_width': numeric_split(enriched, 'v85_zone_width_pct', [1.2, 1.5, 1.8, 2.0]),
            'risk_pct': numeric_split(enriched, 'risk_pct', [1.1, 1.2, 1.3, 1.4, 1.5]),
            'entry_above_zone_high_pct': numeric_split(enriched, 'entry_above_zone_high_pct', [0, 0.2, 0.4, 0.8, 1.2]),
            'mfe_to_r': numeric_split(enriched, 'mfe_to_r', [1, 2, 3, 5, 8]),
        },
        'loss_numeric_summary': {
            k: {
                'loss_avg': round(mean([f(r.get(k)) for r in losses]), 4) if losses else 0,
                'win_avg': round(mean([f(r.get(k)) for r in wins]), 4) if wins else 0,
                'loss_q25': quantile([f(r.get(k)) for r in losses], 0.25),
                'loss_q50': quantile([f(r.get(k)) for r in losses], 0.50),
                'loss_q75': quantile([f(r.get(k)) for r in losses], 0.75),
            }
            for k in ['v85_zone_width_pct','risk_pct','entry_above_zone_high_pct','mfe_20_pct','mae_20_pct','mfe_to_r','takeover_to_entry_bars','touch_to_reclaim_bars']
        },
        'top_losses': sorted(losses, key=lambda r: f(r.get('pnl_pct')))[:80],
        'all_trades_enriched_path': str(OUT / 'v86_v85_trades_enriched.json'),
    }
    (OUT / 'v86_v85_trades_enriched.json').write_text(json.dumps(enriched, ensure_ascii=False))
    (OUT / 'v86_loss_autopsy.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({k: report[k] for k in ['engine','all_metrics','loss_count','loss_by_diagnosis','loss_by_market_state','loss_numeric_summary']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
