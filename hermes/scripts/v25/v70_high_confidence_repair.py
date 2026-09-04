#!/usr/bin/env python3
"""V70 full repair candidate search.

Fix scope:
- Start from V69 best structural combo: FVG_Demand + reclaim_close + swing_low SL + BSL TP.
- Remove duplicate/similar signal-combo clusters per symbol (same story overlapping in time/zone).
- Search only pre-entry features; no exit/hold/outcome leakage.
- Full market run, audit, loser review, and promotion gate >=90% WR with >=100 trades.

No frontend/production sync in this script.
"""
from __future__ import annotations

import json, importlib.util, statistics, math
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/v69_unique_ld_matrix.py')
spec = importlib.util.spec_from_file_location('v69m', BASE)
v69 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v69)

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v70_high_confidence')
OUT_DIR.mkdir(parents=True, exist_ok=True)
PROMOTE_WR = 90.0
PROMOTE_MIN_N = 100


def f(x, default=0.0):
    try:
        if x is None or x == '': return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default


def date_of(ks, idx):
    return v69.d(ks[idx]) if 0 <= idx < len(ks) else ''


def load_ks(kf):
    try: ks = json.loads(kf.read_text())
    except Exception: return None
    if len(ks) < 180: return None
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k] = f(b[k])
    return ks


def market_features(ks, idx):
    # all known at entry close
    c = f(ks[idx].get('c'))
    ma20 = sum(f(ks[i].get('c')) for i in range(max(0, idx-19), idx+1)) / min(20, idx+1)
    ma60 = sum(f(ks[i].get('c')) for i in range(max(0, idx-59), idx+1)) / min(60, idx+1)
    high60 = max(f(ks[i].get('h')) for i in range(max(0, idx-59), idx+1))
    low20 = min(f(ks[i].get('l')) for i in range(max(0, idx-19), idx+1))
    a = v69.atr(ks, idx)
    return {
        'ma20_slope': (ma20 / (sum(f(ks[i].get('c')) for i in range(max(0, idx-24), max(0, idx-4)+1)) / max(1, len(range(max(0, idx-24), max(0, idx-4)+1)))) - 1) * 100 if idx >= 24 else 0,
        'above_ma20_pct': (c/ma20-1)*100 if ma20 else 0,
        'above_ma60_pct': (c/ma60-1)*100 if ma60 else 0,
        'dist_high60_pct': (c/high60-1)*100 if high60 else 0,
        'bounce_low20_atr': (c-low20)/a if a else 0,
        'atr_pct': a/c*100 if c else 0,
    }


def make_trade(symbol, ks, setup):
    if setup.get('zone_type') != 'FVG_Demand':
        return None
    ev = v69.entry_variant(ks, setup, 'reclaim_close')
    if not ev: return None
    eidx, ep = ev['entry_idx'], ev['entry_price']
    sv = v69.sl_variant(ks, setup, eidx, ep, 'swing_low')
    if not sv: return None
    tv = v69.tp_variant(setup, ep, sv['sl'], 'bsl')
    if not tv: return None
    sim = v69.simulate(ks, eidx, ep, sv['sl'], tv['tp1'])
    if not sim: return None
    zl, zh = f(setup['zone_low']), f(setup['zone_high'])
    risk = sv['risk_pct']
    entry_bar = ks[eidx]
    body = abs(f(entry_bar.get('c')) - f(entry_bar.get('o')))
    rng = max(f(entry_bar.get('h')) - f(entry_bar.get('l')), 1e-9)
    mfe_pre = 0.0
    # features known at entry, not after entry
    row = {
        'symbol': symbol,
        'engine': 'V70_HIGH_CONFIDENCE_REPAIR_SEARCH',
        'definition_version': 'FVG_reclaim_swingSL_BSLTP_similarity_dedup_preentry_filters',
        'setup_id': setup['setup_id'],
        'zone_type': setup['zone_type'],
        'entry_method': 'reclaim_close',
        'sl_method': 'swing_low',
        'tp_method': 'bsl',
        'sequence': setup['sequence'],
        'liq_date': setup['liq_date'], 'confirm_date': setup['confirm_date'], 'zone_date': setup['zone_date'], 'entry_date': date_of(ks, eidx),
        'pick_date': date_of(ks, eidx), 'join_date': date_of(ks, eidx),
        'liq_bar': setup['liq_bar'], 'confirm_bar': setup['confirm_bar'], 'zone_bar': setup['zone_bar'], 'entry_idx': eidx,
        'entry_delay': eidx - int(setup['confirm_bar']),
        'zone_age': eidx - int(setup['zone_bar']),
        'liq_to_confirm': int(setup['confirm_bar']) - int(setup['liq_bar']),
        'zone_low': round(zl,4), 'zone_high': round(zh,4), 'zone_width_pct': round((zh/zl-1)*100,3) if zl else 0,
        'entry_price': round(ep,4), 'price': round(ep,4), 'smart_money_cost': round(ep,4), 'cost_line': round(ep,4),
        'sl': round(sv['sl'],4), 'tp1': round(tv['tp1'],4), 'risk_pct': round(risk,3), 'volatility_pct': round(risk,3),
        'rr_realized': round(tv['rr_realized'],3),
        'tp_distance_pct': round((tv['tp1']/ep-1)*100,3),
        'retrace_pct': round(v69.retrace_pct(ks, setup, eidx),2),
        'pierce_atr': setup['pierce_atr'], 'disp_atr': setup['disp_atr'],
        'entry_body_ratio': round(body/rng,3),
        'entry_close_pos': round((f(entry_bar.get('c'))-f(entry_bar.get('l')))/rng,3),
        'gap_from_confirm_pct': round((ep / f(ks[int(setup['confirm_bar'])].get('c')) - 1)*100,3) if f(ks[int(setup['confirm_bar'])].get('c')) else 0,
        **market_features(ks, eidx),
        'semantic_order_pass': int(setup['liq_bar']) < int(setup['confirm_bar']) <= int(setup['zone_bar']) < eidx,
        't_plus_1_pass': str(sim['exit_date']) > date_of(ks, eidx),
        **sim,
    }
    return row


def similar(a,b):
    if a['symbol'] != b['symbol']: return False
    if abs(a['entry_idx'] - b['entry_idx']) <= 5: return True
    # overlapping zone in nearby time = same signal story
    if abs(a['zone_bar'] - b['zone_bar']) <= 10:
        lo = max(a['zone_low'], b['zone_low']); hi = min(a['zone_high'], b['zone_high'])
        if hi > lo:
            overlap = (hi-lo) / max(min(a['zone_high']-a['zone_low'], b['zone_high']-b['zone_low']), 1e-9)
            return overlap >= 0.5
    return False


def quality_key(t):
    # pre-entry quality only: stronger displacement, closer/cleaner entry, lower risk, narrower zone
    return (f(t['disp_atr']), -abs(f(t['gap_from_confirm_pct'])), -f(t['risk_pct']), -f(t['zone_width_pct']), -f(t['entry_delay']))


def dedup_similar(rows):
    out=[]
    for t in sorted(rows, key=lambda x:(x['symbol'], x['entry_idx'])):
        placed=False
        for i,o in enumerate(out):
            if similar(t,o):
                if quality_key(t) > quality_key(o): out[i]=t
                placed=True; break
        if not placed: out.append(t)
    return out


def metrics(rows):
    if not rows: return {'n':0}
    pnls=[f(r['pnl_pct']) for r in rows]; wins=[p for p in pnls if p>0]; losses=[p for p in pnls if p<=0]
    return {
        'n': len(rows), 'wr': round(len(wins)/len(rows)*100,2), 'avg_pnl': round(statistics.mean(pnls),4),
        'median_pnl': round(statistics.median(pnls),4), 'cum_pnl': round(sum(pnls),2),
        'sl_rate': round(sum(r['exit_reason']=='SL_HIT' for r in rows)/len(rows)*100,2),
        'tp_rate': round(sum(r['exit_reason']=='TP1_HIT' for r in rows)/len(rows)*100,2),
        'avg_win': round(statistics.mean(wins),4) if wins else 0,
        'avg_loss': round(statistics.mean(losses),4) if losses else 0,
        'avg_hold': round(statistics.mean([int(f(r['hold_bars'])) for r in rows]),2),
        'exit_counts': dict(Counter(r['exit_reason'] for r in rows)),
    }


def bucket(rows, fn):
    g=defaultdict(list)
    for r in rows: g[fn(r)].append(r)
    return {str(k): metrics(v) for k,v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def filter_search(rows):
    """Beam-search pre-entry gates instead of cartesian brute force.

    This deliberately avoids outcome fields. It finds whether 90% is reachable
    with a readable gate stack rather than an overfit 10-dimensional grid.
    """
    if not rows:
        return []
    gates=[]
    def add(name, fn, cfg):
        gates.append((name, fn, cfg))
    for lo,hi in [(0,4),(0,6),(2,8),(4,10),(6,14),(0,14)]: add(f'risk_{lo}_{hi}', lambda r,lo=lo,hi=hi: lo<=f(r['risk_pct'])<hi, {'risk':(lo,hi)})
    for lo,hi in [(0,40),(20,60),(30,70),(40,80),(50,100),(0,100)]: add(f'retr_{lo}_{hi}', lambda r,lo=lo,hi=hi: lo<=f(r['retrace_pct'])<hi, {'retr':(lo,hi)})
    for lo in [0.8,1.2,1.8,2.5,3.5]: add(f'disp_ge_{lo}', lambda r,lo=lo: f(r['disp_atr'])>=lo, {'disp_lo':lo})
    for lo in [0.3,0.8,1.2]: add(f'pierce_ge_{lo}', lambda r,lo=lo: f(r['pierce_atr'])>=lo, {'pierce_lo':lo})
    for lo,hi in [(1,3),(1,5),(2,8),(4,12),(1,12)]: add(f'delay_{lo}_{hi}', lambda r,lo=lo,hi=hi: lo<=int(f(r['entry_delay']))<=hi, {'delay':(lo,hi)})
    for lo in [-3,0,2,5]: add(f'above_ma20_ge_{lo}', lambda r,lo=lo: f(r['above_ma20_pct'])>=lo, {'above_ma20_lo':lo})
    for lo in [-20,-10,-5,-2]: add(f'dist_high60_ge_{lo}', lambda r,lo=lo: f(r['dist_high60_pct'])>=lo, {'dist_high60_lo':lo})
    for hi in [8,6,4,3]: add(f'atr_le_{hi}', lambda r,hi=hi: f(r['atr_pct'])<=hi, {'atr_hi':hi})
    for hi in [10,6,3,1.5]: add(f'zone_width_le_{hi}', lambda r,hi=hi: f(r['zone_width_pct'])<=hi, {'zone_width_hi':hi})
    for hi in [3,2,1.5,1.2]: add(f'rr_le_{hi}', lambda r,hi=hi: f(r['rr_realized'])<=hi, {'rr_hi':hi})

    def score(sel):
        m=metrics(sel)
        return (m['wr'], min(m['n'],500), m['avg_pnl'])
    beam=[([], rows, {})]
    results=[]
    for depth in range(1,7):
        nxt=[]
        for names, subset, cfg in beam:
            used=set(names)
            for name, fn, delta in gates:
                if name in used:
                    continue
                sel=[r for r in subset if fn(r)]
                if len(sel)<20:
                    continue
                newcfg=dict(cfg); newcfg.update(delta)
                m=metrics(sel)
                item={'cfg':newcfg,'metrics':m,'gates':names+[name]}
                if m['wr']>=90 or (m['n']>=100 and m['wr']>=85) or (m['n']>=300 and m['wr']>=80):
                    results.append(item)
                nxt.append((names+[name], sel, newcfg))
        nxt.sort(key=lambda x: score(x[1]), reverse=True)
        # remove duplicate gate-name sets and keep top beam
        seen=set(); beam=[]
        for item in nxt:
            k=tuple(sorted(item[0]))
            if k in seen: continue
            seen.add(k); beam.append(item)
            if len(beam)>=160: break
    # Always include best beam endpoints for diagnostics.
    for names, sel, cfg in beam[:50]:
        results.append({'cfg':cfg,'metrics':metrics(sel),'gates':names})
    results.sort(key=lambda x:(x['metrics']['wr'], min(x['metrics']['n'],500), x['metrics']['avg_pnl']), reverse=True)
    return results


def audit(rows):
    fails=[]
    req=('symbol','setup_id','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1','pnl_pct')
    for r in rows:
        issues=[]
        if not r.get('semantic_order_pass'): issues.append('semantic_order')
        if not r.get('t_plus_1_pass'): issues.append('t_plus_1')
        if r.get('zone_type')!='FVG_Demand': issues.append('not_fvg')
        if any(r.get(k) in (None,'',0,0.0) for k in req if k not in ('pnl_pct',)): issues.append('missing_field')
        if issues: fails.append({'symbol':r.get('symbol'),'entry_date':r.get('entry_date'),'issues':issues})
    return {'n':len(rows),'fail_count':len(fails),'pass_count':len(rows)-len(fails),'semantic_order_fail':sum('semantic_order' in x['issues'] for x in fails),'t_plus_1_fail':sum('t_plus_1' in x['issues'] for x in fails),'field_contract_fail':sum('missing_field' in x['issues'] for x in fails),'sample_fails':fails[:20]}


def apply_cfg(rows,cfg):
    risk_lo,risk_hi=cfg['risk']; retr_lo,retr_hi=cfg['retr']; delay_lo,delay_hi=cfg['delay']
    return [r for r in rows if risk_lo<=f(r['risk_pct'])<risk_hi and retr_lo<=f(r['retrace_pct'])<retr_hi and f(r['disp_atr'])>=cfg['disp_lo'] and f(r['pierce_atr'])>=cfg['pierce_lo'] and delay_lo<=int(f(r['entry_delay']))<=delay_hi and f(r['above_ma20_pct'])>=cfg['above_ma20_lo'] and f(r['dist_high60_pct'])>=cfg['dist_high60_lo'] and f(r['atr_pct'])<=cfg['atr_hi'] and f(r['zone_width_pct'])<=cfg['zone_width_hi'] and f(r['rr_realized'])<=cfg['rr_hi']]


def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    all_rows=[]
    print(f'V70 high-confidence repair run {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for i,kf in enumerate(files,1):
        sym=kf.stem.replace('_daily_750','')
        symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
        ks=load_ks(kf)
        if not ks: continue
        setups=v69.build_unique_setups(symbol, ks)
        rows=[]
        for s in setups:
            t=make_trade(symbol,ks,s)
            if t: rows.append(t)
        all_rows.extend(dedup_similar(rows))
        if i%500==0: print(f'  {i}/{len(files)} rows={len(all_rows)}', flush=True)
    all_rows=dedup_similar(all_rows)
    (OUT_DIR/'v70_all_trades.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2))
    print(f'  extraction_done rows={len(all_rows)} search_start={datetime.now():%H:%M:%S}', flush=True)
    cands=filter_search(all_rows)
    best_cfg = cands[0]['cfg'] if cands else None
    best_rows = apply_cfg(all_rows,best_cfg) if best_cfg else []
    report={
        'generated_at':datetime.now().isoformat(timespec='seconds'),
        'n_stocks':len(files),
        'base_after_similarity_dedup':metrics(all_rows),
        'base_audit':audit(all_rows),
        'leaderboard_top50':cands[:50],
        'best_cfg':best_cfg,
        'best_metrics':metrics(best_rows),
        'best_audit':audit(best_rows),
        'promotion_gate':{'min_wr':PROMOTE_WR,'min_n':PROMOTE_MIN_N},
        'decision':'PROMOTION_ELIGIBLE' if best_rows and metrics(best_rows)['wr']>=PROMOTE_WR and len(best_rows)>=PROMOTE_MIN_N and audit(best_rows)['fail_count']==0 else 'NO_PROMOTION_BELOW_90_OR_TOO_SMALL',
        'buckets_base':{
            'risk':bucket(all_rows, lambda r: '<4' if f(r['risk_pct'])<4 else ('4-8' if f(r['risk_pct'])<8 else '8+')),
            'retrace':bucket(all_rows, lambda r: '<40' if f(r['retrace_pct'])<40 else ('40-70' if f(r['retrace_pct'])<70 else '70+')),
            'delay':bucket(all_rows, lambda r: '1-3' if int(f(r['entry_delay']))<=3 else ('4-8' if int(f(r['entry_delay']))<=8 else '9+')),
            'disp':bucket(all_rows, lambda r: '<1.2' if f(r['disp_atr'])<1.2 else ('1.2-2.5' if f(r['disp_atr'])<2.5 else '2.5+')),
            'exit':bucket(all_rows, lambda r: r['exit_reason']),
            'year':bucket(all_rows, lambda r: r['entry_date'][:4]),
        },
        'buckets_best':{
            'exit':bucket(best_rows, lambda r: r['exit_reason']),
            'year':bucket(best_rows, lambda r: r['entry_date'][:4]),
            'risk':bucket(best_rows, lambda r: '<4' if f(r['risk_pct'])<4 else ('4-8' if f(r['risk_pct'])<8 else '8+')),
        },
        'loser_samples_best': [r for r in best_rows if f(r['pnl_pct'])<=0][:200],
    }
    (OUT_DIR/'v70_all_trades.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2))
    (OUT_DIR/'v70_best_trades.json').write_text(json.dumps(best_rows,ensure_ascii=False,indent=2))
    (OUT_DIR/'v70_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ['base_after_similarity_dedup','best_cfg','best_metrics','best_audit','decision']},ensure_ascii=False,indent=2))
    print('Saved',OUT_DIR)

if __name__=='__main__': main()
