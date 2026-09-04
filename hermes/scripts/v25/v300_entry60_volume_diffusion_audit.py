#!/usr/bin/env python3
"""V300 no-write: entry-session 60m volume diffusion overlay on V299 strict lifecycle rows.

V299 showed stricter ACC->MAN->DIS lifecycle still failed weak months.  The next
concrete hypothesis is not another price-window tweak, but whether entry-session
volume/amount diffusion across market + industry can identify real board funds
continuation before an executable delayed entry.

This script:
  - uses V299 strict same-source 60m lifecycle rows only as source;
  - builds entry-day first/second/third 60m market+industry+stock volume context;
  - simulates delayed entries at the close of k-th 60m bar, with T+1 daily exits;
  - writes only audit artifacts under ~/.hermes/smc_audit.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

BASE = Path('/root/.hermes')
AUDIT = BASE / 'smc_audit'
V294_SCRIPT = BASE / 'scripts/v25/v294_entry60_persistence_audit.py'
V299_LATEST = AUDIT / 'v299_strict_60m_lifecycle_latest.json'
INDMAP = AUDIT / 'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
TS = datetime.now().strftime('%Y%m%d_%H%M%S')
OUT = AUDIT / f'v300_entry60_volume_diffusion_no_write_{TS}'
LATEST = AUDIT / 'v300_entry60_volume_diffusion_latest.json'


def load_core():
    spec = importlib.util.spec_from_file_location('v294_core_for_v300', V294_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


core = load_core()


def sf(x: Any, d: float = math.nan) -> float:
    return core.sf(x, d)


def dn(x: Any) -> str:
    return core.dn(x)


def load_source() -> tuple[list[dict[str, Any]], Path]:
    summary = json.loads(V299_LATEST.read_text())
    p = Path(summary['artifacts']['rows'])
    with p.open() as fh:
        return list(csv.DictReader(fh)), p


def mean(xs: list[float]) -> float:
    vals = [x for x in xs if not math.isnan(x)]
    return sum(vals) / len(vals) if vals else math.nan


def bret(x: float) -> str:
    if math.isnan(x):
        return 'RET_NA'
    if x < 0:
        return 'RET<0'
    if x < 0.5:
        return 'RET0_0.5'
    if x < 1:
        return 'RET0.5_1'
    return 'RET>=1'


def bvol(x: float) -> str:
    if math.isnan(x):
        return 'VOL_NA'
    if x < 0.8:
        return 'VOL<0.8'
    if x < 1.2:
        return 'VOL0.8_1.2'
    if x < 1.6:
        return 'VOL1.2_1.6'
    return 'VOL>=1.6'


def build_volume_context(sym_ind: dict[str, str], ks: tuple[int, ...] = (1, 2, 3)):
    stock: dict[tuple[str, str, int], dict[str, float]] = {}
    market_rows: dict[tuple[str, int], list[dict[str, float]]] = defaultdict(list)
    ind_rows: dict[tuple[str, str, int], list[dict[str, float]]] = defaultdict(list)
    seen: set[str] = set(); files: list[tuple[str, Path]] = []
    for d in core.K60_DIRS:
        for p in d.glob('*_60min_500.json'):
            sym = core.symbol_from_path(p)
            if sym and sym in sym_ind and sym not in seen:
                seen.add(sym); files.append((sym, p))
    for sym, p in files:
        ind = sym_ind[sym]
        byday: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for b in core.load_json(p):
            day = dn(b.get('t'))
            if day:
                byday[day].append(b)
        days = sorted(byday)
        day_vol_by_k: dict[tuple[str, int], float] = {}
        day_rec_by_k: dict[tuple[str, int], dict[str, float]] = {}
        for day in days:
            bars = sorted(byday[day], key=lambda x: str(x.get('t')))
            if not bars:
                continue
            open0 = sf(bars[0].get('o'))
            if open0 <= 0:
                continue
            for k in ks:
                if len(bars) < k:
                    continue
                part = bars[:k]
                close = sf(part[-1].get('c'))
                low = min(sf(b.get('l')) for b in part)
                high = max(sf(b.get('h')) for b in part)
                vol = sum(sf(b.get('v'), 0.0) for b in part)
                if close <= 0 or low <= 0 or vol <= 0:
                    continue
                day_vol_by_k[(day, k)] = vol
                day_rec_by_k[(day, k)] = {
                    'ret': (close / open0 - 1) * 100,
                    'close': close,
                    'low': low,
                    'high': high,
                    'vol': vol,
                }
        for idx, day in enumerate(days):
            for k in ks:
                rec = day_rec_by_k.get((day, k))
                if not rec:
                    continue
                prev_vols = [day_vol_by_k[(d, k)] for d in days[max(0, idx - 5):idx] if (d, k) in day_vol_by_k]
                base = median(prev_vols) if prev_vols else math.nan
                vol_ratio = rec['vol'] / base if base and base > 0 and not math.isnan(base) else math.nan
                full = dict(rec)
                full['vol_ratio'] = vol_ratio
                full['up_vol'] = float(rec['ret'] > 0 and vol_ratio >= 1.2)
                full['strong_up_vol'] = float(rec['ret'] >= 0.5 and vol_ratio >= 1.3)
                stock[(sym, day, k)] = full
                market_rows[(day, k)].append(full)
                ind_rows[(day, ind, k)].append(full)
    mctx: dict[tuple[str, int], dict[str, float]] = {}
    for key, rs in market_rows.items():
        mctx[key] = {
            'mkt_n': len(rs),
            'mkt_up': sum(r['ret'] > 0 for r in rs) / len(rs) * 100,
            'mkt_ret': median([r['ret'] for r in rs]),
            'mkt_vol_med': median([r['vol_ratio'] for r in rs if not math.isnan(r['vol_ratio'])]) if any(not math.isnan(r['vol_ratio']) for r in rs) else math.nan,
            'mkt_up_vol': sum(r['up_vol'] for r in rs) / len(rs) * 100,
            'mkt_strong_up_vol': sum(r['strong_up_vol'] for r in rs) / len(rs) * 100,
        }
    ictx: dict[tuple[str, str, int], dict[str, float]] = {}
    for key, rs in ind_rows.items():
        if len(rs) < 5:
            continue
        ictx[key] = {
            'ind_n': len(rs),
            'ind_up': sum(r['ret'] > 0 for r in rs) / len(rs) * 100,
            'ind_ret': median([r['ret'] for r in rs]),
            'ind_vol_med': median([r['vol_ratio'] for r in rs if not math.isnan(r['vol_ratio'])]) if any(not math.isnan(r['vol_ratio']) for r in rs) else math.nan,
            'ind_up_vol': sum(r['up_vol'] for r in rs) / len(rs) * 100,
            'ind_strong_up_vol': sum(r['strong_up_vol'] for r in rs) / len(rs) * 100,
        }
    return stock, mctx, ictx, len(files)


def enrich_rows(source: list[dict[str, Any]], sym_ind: dict[str, str], stock_ctx, mctx, ictx) -> list[dict[str, Any]]:
    cache_day: dict[str, list[dict[str, Any]]] = {}
    enriched: list[dict[str, Any]] = []
    for r in source:
        sym = r.get('symbol', '')
        day = dn(r.get('entry_date'))
        ind = sym_ind.get(sym, '')
        zl = sf(r.get('acc_lo') or r.get('zone_low'))
        zh = sf(r.get('acc_hi') or r.get('zone_high'))
        if not sym or not day or zl <= 0 or zh <= 0:
            continue
        for k in (1, 2, 3):
            sk = stock_ctx.get((sym, day, k), {})
            mk = mctx.get((day, k), {})
            ik = ictx.get((day, ind, k), {})
            if not sk or not mk or not ik:
                continue
            # executable confirmation: stock has not lost the zone and closes above ACC high.
            if sf(sk.get('low')) <= zl or sf(sk.get('close')) <= zh:
                continue
            entry = sf(sk.get('close'))
            sl = zl * 0.992
            res = core.replay(core.loadday(sym, cache_day), day, entry, sl)
            if not res:
                continue
            nr = dict(r)
            nr.update(res)
            nr.update({
                'confirm_k': k,
                'entry': round(entry, 4),
                'entry_mode': f'v300_k{k}_volume_diffusion',
                'risk_after_confirm': round((entry / sl - 1) * 100, 4) if sl > 0 else math.nan,
                'stock60_ret': round(sf(sk.get('ret')), 4),
                'stock60_vol_ratio': round(sf(sk.get('vol_ratio')), 4),
                'mkt_up': round(sf(mk.get('mkt_up')), 4),
                'mkt_ret': round(sf(mk.get('mkt_ret')), 4),
                'mkt_vol_med': round(sf(mk.get('mkt_vol_med')), 4),
                'mkt_up_vol': round(sf(mk.get('mkt_up_vol')), 4),
                'mkt_strong_up_vol': round(sf(mk.get('mkt_strong_up_vol')), 4),
                'ind_up': round(sf(ik.get('ind_up')), 4),
                'ind_ret': round(sf(ik.get('ind_ret')), 4),
                'ind_vol_med': round(sf(ik.get('ind_vol_med')), 4),
                'ind_up_vol': round(sf(ik.get('ind_up_vol')), 4),
                'ind_strong_up_vol': round(sf(ik.get('ind_strong_up_vol')), 4),
                'stock_vol_bucket': bvol(sf(sk.get('vol_ratio'))),
                'stock_ret_bucket': bret(sf(sk.get('ret'))),
                't1_violation': res['exit_date'] <= day,
            })
            enriched.append(nr)
    return enriched


def metric_rows(rows: list[dict[str, Any]], stock_count: int, source_n: int) -> dict[str, Any]:
    agg = core.blank()
    for r in rows:
        core.add(agg, r)
    return core.metrics(agg, stock_count, source_n)


def evaluate(enriched: list[dict[str, Any]], stock_count: int, source_n: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    variants: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for k in (1, 2, 3):
        base_k = [r for r in enriched if int(sf(r.get('confirm_k'), 0)) == k]
        for m_up in (50, 65):
            for i_up in (50, 65):
                for m_uv in (20, 35, 50):
                    for i_uv in (20, 35, 50):
                        for s_vol in (1.0, 1.3, 1.6):
                            for s_ret in (0.0, 0.5):
                                for rel in (False, True):
                                    kept = []
                                    for r in base_k:
                                        if sf(r.get('mkt_up')) < m_up or sf(r.get('ind_up')) < i_up:
                                            continue
                                        if sf(r.get('mkt_up_vol')) < m_uv or sf(r.get('ind_up_vol')) < i_uv:
                                            continue
                                        if sf(r.get('stock60_vol_ratio')) < s_vol or sf(r.get('stock60_ret')) < s_ret:
                                            continue
                                        if rel and (sf(r.get('ind_up_vol')) < sf(r.get('mkt_up_vol')) or sf(r.get('ind_vol_med')) < sf(r.get('mkt_vol_med'))):
                                            continue
                                        kept.append(r)
                                    if len(kept) < 80:
                                        continue
                                    m = metric_rows(kept, stock_count, source_n)
                                    if m.get('min_year_n', 0) < 20 or m.get('min_month_n', 0) < 5:
                                        continue
                                    m['variant'] = f"k{k}_mup{m_up}_iup{i_up}_muv{m_uv}_iuv{i_uv}_svol{s_vol}_sret{s_ret}_{'rellead' if rel else 'raw'}"
                                    m['config'] = {'k': k, 'm_up': m_up, 'i_up': i_up, 'm_up_vol': m_uv, 'i_up_vol': i_uv, 'stock_vol': s_vol, 'stock_ret': s_ret, 'industry_volume_leads_market': rel}
                                    m['t1_violations'] = sum(1 for x in kept if x.get('t1_violation'))
                                    variants.append((m, kept))
    variants.sort(key=lambda x: (x[0].get('min_month_wr', 0), x[0].get('min_year_wr', 0), x[0].get('wr', 0), x[0].get('avg', 0), x[0].get('n', 0)), reverse=True)
    return [v[0] for v in variants[:50]], variants[0][1] if variants else []


def decompose(rows: list[dict[str, Any]], stock_count: int, source_n: int) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        dims = {
            'confirm_k': str(r.get('confirm_k')),
            'stock_vol_bucket': r.get('stock_vol_bucket', ''),
            'stock_ret_bucket': r.get('stock_ret_bucket', ''),
            'reason': r.get('reason', ''),
        }
        for k, v in dims.items():
            groups[(k, str(v))].append(r)
    out = []
    for (dim, val), rs in groups.items():
        if len(rs) >= 50:
            out.append({'dimension': dim, 'value': val, **metric_rows(rs, stock_count, source_n)})
    out.sort(key=lambda x: (x['min_year_wr'], x['wr'], x['avg'], x['n']), reverse=True)
    return out[:120]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    source, source_path = load_source()
    stock_count = len({r['symbol'] for r in source})
    sym_ind = {r['symbol']: r.get('industry', '') for r in json.loads(INDMAP.read_text()) if r.get('symbol')}
    stock_ctx, mctx, ictx, files60 = build_volume_context(sym_ind)
    enriched = enrich_rows(source, sym_ind, stock_ctx, mctx, ictx)
    top_variants, best_rows = evaluate(enriched, stock_count, len(source))

    enriched_path = OUT / 'v300_enriched_rows.csv'
    if enriched:
        fields = []
        for r in enriched:
            for k in r:
                if k not in fields:
                    fields.append(k)
        with enriched_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(enriched)
    best_path = OUT / 'v300_best_rows.csv'
    if best_rows:
        fields = []
        for r in best_rows:
            for k in r:
                if k not in fields:
                    fields.append(k)
        with best_path.open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=fields)
            w.writeheader(); w.writerows(best_rows)

    summary = {
        'version': 'V300_ENTRY60_VOLUME_DIFFUSION_NO_WRITE',
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'no_write': True, 'production_write': False, 'frontend_write': False, 'watchlist_write': False,
        'hypothesis': 'Entry-session 60m market/industry/stock volume diffusion can separate real board-fund continuation from V299 false lifecycle takeovers.',
        'source': str(source_path),
        'source_n': len(source),
        'sixty_min_files': files60,
        'raw_v299_source': json.loads(V299_LATEST.read_text()).get('raw_strict_feature_rows'),
        'enriched_executable_rows': metric_rows(enriched, stock_count, len(source)),
        'best_variant': top_variants[0] if top_variants else None,
        'top_variants': top_variants[:20],
        'best_decomposition': decompose(best_rows, stock_count, len(best_rows)) if best_rows else [],
        't1_violations_enriched': sum(1 for r in enriched if r.get('t1_violation')),
        't1_violations_best': sum(1 for r in best_rows if r.get('t1_violation')),
        'artifacts': {'enriched_rows': str(enriched_path), 'best_rows': str(best_path), 'summary': str(OUT / 'v300_summary.json')},
    }
    (OUT / 'v300_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    LATEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps({'latest': str(LATEST), 'enriched': summary['enriched_executable_rows'], 'best': summary['best_variant'], 'top10': top_variants[:10], 't1_best': summary['t1_violations_best']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
