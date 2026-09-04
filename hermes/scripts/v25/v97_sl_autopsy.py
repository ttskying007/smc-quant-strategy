#!/usr/bin/env python3
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple

from v81_full_market_scan import KLINE_DIR, load_json
from v91_shadow_zone_entry_scanner import bar_date, date_key, num

BASE = Path('/root/.hermes/smc_opt_v97_structural_rr_contract')
TRADES = BASE / 'v97_structural_trades.json'
OUT = BASE / 'v97_sl_autopsy.json'
MAX_HOLD = 80

def f(x: Any, default: float = 0.0) -> float:
    return num(x, default)

def kline_path(symbol: str) -> Path:
    code, ex = symbol.split('.')
    return KLINE_DIR / f'{code}_{ex}_daily_750.json'

def pct(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0

def metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    wins = [r for r in rows if f(r.get('pnl_pct')) > 0]
    sls = [r for r in rows if r.get('exit_reason') == 'SL_HIT']
    return {
        'n': n,
        'wr': pct(len(wins), n),
        'sl_rate': pct(len(sls), n),
        'avg_pnl': round(sum(f(r.get('pnl_pct')) for r in rows) / n, 4) if n else 0,
        'avg_tp2_rr': round(sum(f(r.get('tp2_rr')) for r in rows) / n, 4) if n else 0,
        'avg_risk_pct': round(sum(f(r.get('risk_pct')) for r in rows) / n, 4) if n else 0,
    }

def bucket(rows: List[Dict[str, Any]], key: str, min_n: int = 20) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[str(r.get(key) or 'EMPTY')].append(r)
    out = []
    for k, rs in groups.items():
        if len(rs) >= min_n:
            m = metrics(rs)
            m[key] = k
            out.append(m)
    return sorted(out, key=lambda x: (-x['sl_rate'], -x['n']))

def replay_sl(row: Dict[str, Any], ks: List[Dict[str, Any]]) -> Dict[str, Any]:
    entry_idx = int(f(row.get('entry_idx'), -1))
    exit_idx = int(f(row.get('exit_idx'), -1))
    ep = f(row.get('entry_price'))
    sl = f(row.get('sl'))
    tp2 = f(row.get('tp2'))
    tp3 = f(row.get('tp3'))
    zl = f(row.get('zone_low'))
    zh = f(row.get('zone_high'))
    risk = ep - sl
    if entry_idx < 0 or entry_idx >= len(ks) or risk <= 0:
        return {'root_bucket': 'BAD_DATA'}
    end = min(len(ks) - 1, entry_idx + MAX_HOLD)
    pre_exit = ks[entry_idx + 1:max(entry_idx + 1, min(exit_idx, end) + 1)] if exit_idx > entry_idx else []
    post_exit = ks[exit_idx + 1:end + 1] if 0 <= exit_idx < end else []
    first5 = ks[entry_idx + 1:min(len(ks), entry_idx + 6)]
    max_h_pre = max([ep] + [f(b.get('h')) for b in pre_exit])
    min_l_pre = min([ep] + [f(b.get('l')) for b in pre_exit])
    mfe_before_sl = (max_h_pre - ep) / risk
    mae_before_sl = (ep - min_l_pre) / risk
    would_hit_tp2_after_sl = any(f(b.get('h')) >= tp2 for b in post_exit) if tp2 else False
    would_hit_tp3_after_sl = any(f(b.get('h')) >= tp3 for b in post_exit) if tp3 else False
    close_below_zone_before_sl = any(zl and f(b.get('c')) < zl for b in pre_exit)
    close_below_sl_before_sl = any(f(b.get('c')) < sl for b in pre_exit)
    close_recovered_next2 = False
    if 0 <= exit_idx < len(ks) - 2:
        close_recovered_next2 = any(f(ks[j].get('c')) > max(sl, zl or sl) for j in range(exit_idx, min(len(ks), exit_idx + 3)))
    first5_max_r = (max([ep] + [f(b.get('h')) for b in first5]) - ep) / risk
    first5_min_r = (ep - min([ep] + [f(b.get('l')) for b in first5])) / risk
    entry_zone_pos = (ep - zl) / (zh - zl) if zh > zl else None
    bars_to_sl = exit_idx - entry_idx if exit_idx >= entry_idx else None
    # Root-cause precedence: actual price path first, then design/context buckets.
    if would_hit_tp2_after_sl and not close_below_zone_before_sl and close_recovered_next2:
        root = 'SL_TOO_TIGHT_WICK_SWEEP_THEN_RECOVER'
    elif close_below_zone_before_sl or close_below_sl_before_sl:
        root = 'POI_INVALIDATED_TRUE_ZONE_DEATH'
    elif bars_to_sl is not None and bars_to_sl <= 3 and first5_max_r < 0.5:
        root = 'ENTRY_TOO_EARLY_NO_REACTION'
    elif mfe_before_sl < 1.0:
        root = 'PATH_NO_UPSIDE_REACTION_TO_5R'
    elif mfe_before_sl >= 2.0 and not would_hit_tp2_after_sl:
        root = 'PATH_STALLED_BEFORE_5R_REVERSAL'
    else:
        root = 'MIXED_PATH_FAILURE'
    return {
        'root_bucket': root,
        'bars_to_sl': bars_to_sl,
        'mfe_before_sl': round(mfe_before_sl, 4),
        'mae_before_sl': round(mae_before_sl, 4),
        'first5_max_r': round(first5_max_r, 4),
        'first5_min_r': round(first5_min_r, 4),
        'would_hit_tp2_after_sl': would_hit_tp2_after_sl,
        'would_hit_tp3_after_sl': would_hit_tp3_after_sl,
        'close_below_zone_before_sl': close_below_zone_before_sl,
        'close_below_sl_before_sl': close_below_sl_before_sl,
        'close_recovered_next2': close_recovered_next2,
        'entry_zone_pos': round(entry_zone_pos, 4) if entry_zone_pos is not None else None,
    }

def main() -> None:
    rows = json.loads(TRADES.read_text())
    prod = [r for r in rows if r.get('production_grade') == 'A_PRODUCTION']
    sls = [r for r in prod if r.get('exit_reason') == 'SL_HIT']
    enriched = []
    kcache: Dict[str, List[Dict[str, Any]]] = {}
    for r in sls:
        sym = r.get('symbol')
        if sym not in kcache:
            kcache[sym] = load_json(kline_path(sym))
        e = dict(r)
        e.update(replay_sl(r, kcache[sym]))
        enriched.append(e)
    root_counts = Counter(e['root_bucket'] for e in enriched)
    # Counterfactual candidate filters: pure structural/non-symbol-specific gates.
    filter_defs = {
        'keep_non_mixed_market_state': lambda r: r.get('market_state') != 'MIXED',
        'keep_discount_only': lambda r: r.get('pd_zone') == 'DISCOUNT',
        'keep_non_risk_gate': lambda r: r.get('v91_gate_reason') != 'RISK',
        'keep_recovery_mixed_only': lambda r: r.get('v90_recovery_substate') == 'MIXED',
        'keep_risk_1_5_to_3_0': lambda r: 1.5 <= f(r.get('risk_pct')) <= 3.0,
        'keep_zone_width_0_8_to_2_5': lambda r: 0.8 <= f(r.get('v85_zone_width_pct') or r.get('volatility_pct')) <= 2.5,
        'keep_tp2_5_to_12': lambda r: 5 <= f(r.get('tp2_rr')) <= 12,
        'keep_mfe1_reaction_for_research_only': lambda r: f(r.get('mfe_r')) >= 1.0,
    }
    filter_metrics = []
    for name, fn in filter_defs.items():
        kept = [r for r in prod if fn(r)]
        rejected = [r for r in prod if not fn(r)]
        km = metrics(kept); rm = metrics(rejected)
        km['filter'] = name; km['kept'] = len(kept); km['rejected'] = len(rejected)
        km['rejected_sl_rate'] = rm['sl_rate']; km['rejected_wr'] = rm['wr']; km['rejected_avg_pnl'] = rm['avg_pnl']
        filter_metrics.append(km)
    combo = prod
    for fn in [filter_defs['keep_discount_only'], filter_defs['keep_risk_1_5_to_3_0'], filter_defs['keep_zone_width_0_8_to_2_5'], filter_defs['keep_tp2_5_to_12']]:
        combo = [r for r in combo if fn(r)]
    combo_m = metrics(combo); combo_m['filter'] = 'COMBO_discount+risk1.5-3+zone0.8-2.5+tp2_5-12'; combo_m['kept'] = len(combo)
    result = {
        'population': {'production': metrics(prod), 'sl_hit': len(sls)},
        'sl_root_counts': dict(root_counts),
        'sl_root_pct': {k: pct(v, len(enriched)) for k, v in root_counts.items()},
        'root_bucket_metrics': bucket(enriched, 'root_bucket', 1),
        'bucket_by_market_state': bucket(prod, 'market_state'),
        'bucket_by_pd_zone': bucket(prod, 'pd_zone'),
        'bucket_by_poi_type': bucket(prod, 'poi_type'),
        'bucket_by_event_type': bucket(prod, 'event_type'),
        'bucket_by_v91_gate_reason': bucket(prod, 'v91_gate_reason'),
        'bucket_by_recovery_substate': bucket(prod, 'v90_recovery_substate'),
        'bucket_by_v85_path': bucket(prod, 'v85_path'),
        'candidate_filter_metrics': sorted(filter_metrics + [combo_m], key=lambda x: (-x.get('wr', 0), -x.get('kept', x.get('n', 0)))),
        'samples_by_root': {k: [
            {kk: r.get(kk) for kk in ['symbol','entry_date','exit_date','market_state','pd_zone','poi_type','event_type','v91_gate_reason','v90_recovery_substate','risk_pct','tp2_rr','mfe_before_sl','bars_to_sl','close_below_zone_before_sl','would_hit_tp2_after_sl']}
            for r in [x for x in enriched if x['root_bucket'] == k][:8]
        ] for k in root_counts},
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({
        'production': result['population']['production'],
        'sl_hit': len(sls),
        'sl_root_pct': result['sl_root_pct'],
        'top_filters': result['candidate_filter_metrics'][:10],
    }, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
