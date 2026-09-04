#!/usr/bin/env python3
from __future__ import annotations

import json, math, statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

import sys
sys.path.insert(0, '/root/.hermes/scripts/v25')
from v98_reachable_5r_probability_gate import structural_sl, structural_targets, classify, simulate, MAX_HOLD
from v85_mixed_accumulation_generator import zone_width_pct
from v91_shadow_zone_entry_scanner import bar_date, date_key, num, price_in_bar

ROOT = Path('/root/.hermes')
TRADE_PATH = ROOT / 'smc_opt_v98_reachable_5r_probability_gate' / 'v98_structural_trades.json'
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_opt_v98_reachable_5r_probability_gate' / 'v98_shadow_fix_matrix.json'


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def kline(symbol: str):
    stem = symbol.replace('.', '_')
    for suffix in ('daily_750','daily_300'):
        p = KLINE_DIR / f'{stem}_{suffix}.json'
        if p.exists(): return load(p, [])
    return []


def n(x, default=0.0): return num(x, default)

def yr(r):
    d = date_key(r.get('entry_date'))
    return d[:4] if d else 'UNKNOWN'

def pct(a,b): return round(a/b*100,2) if b else 0.0

def stat(rows: List[Dict[str,Any]]):
    pnls=[n(r.get('pnl_pct')) for r in rows]
    wins=sum(1 for r in rows if n(r.get('pnl_pct'))>0)
    return {
        'n':len(rows),'wr':pct(wins,len(rows)),'sl_rate':pct(sum(1 for r in rows if r.get('exit_reason')=='SL_HIT'),len(rows)),
        'tp2_rate':pct(sum(1 for r in rows if r.get('exit_reason')=='TP2_MAIN_HIT'),len(rows)),
        'avg_pnl':round(sum(pnls)/len(rows),4) if rows else 0,'cum_pnl':round(sum(pnls),4),
        'avg_hold':round(sum(n(r.get('hold_bars_realized')) for r in rows)/len(rows),2) if rows else 0,
        'exit_counts':dict(Counter(r.get('exit_reason') for r in rows))
    }

def by_year(rows):
    g=defaultdict(list)
    for r in rows: g[yr(r)].append(r)
    return {k:stat(v) for k,v in sorted(g.items())}

def fill_from(ks, start, end, price):
    start=max(1,start); end=min(len(ks)-2,end)
    for i in range(start,end+1):
        if price_in_bar(ks[i], price): return i
    return -1

def rebuild(row, ks, fill_idx, entry_price, variant):
    zl=n(row.get('zone_low')); zh=n(row.get('zone_high'))
    if fill_idx < 1 or fill_idx >= len(ks)-2 or not entry_price: return None
    pick_date=date_key(row.get('pick_date') or row.get('select_date') or row.get('event_date'))
    join_date=bar_date(ks[fill_idx])
    if not pick_date or not join_date or pick_date == join_date: return None
    sl, sl_mode, sl_ref=structural_sl(ks, fill_idx, entry_price, zl)
    risk=entry_price-sl
    if risk <= 0: return None
    targets=structural_targets(ks, fill_idx, entry_price, sl)
    tp1=next((x for x in targets if x['rr']>=2), None) or (targets[0] if targets else None)
    tp2=next((x for x in targets if x['rr']>=5), None)
    tp3=next((x for x in targets if x['rr']>=8), None)
    if tp2 is None and targets: tp2=targets[-1]
    if tp3 is None and targets: tp3=targets[-1]
    rr2=n(tp2.get('rr')) if tp2 else 0; rr3=n(tp3.get('rr')) if tp3 else 0
    grade=classify(rr2,rr3,not sl_mode.startswith('FALLBACK'),tp2.get('target_type','') if tp2 else '',tp3.get('target_type','') if tp3 else '',row.get('pd_zone') or '',zone_width_pct(row) or 0,row.get('market_state') or '')
    if grade != 'A_PRODUCTION': return None
    r=dict(row)
    r.update({'variant':variant,'entry_idx':fill_idx,'entry_date':join_date,'join_date':join_date,'entry_price':round(entry_price,4),'price':round(entry_price,4),'sl':round(sl,4),'sl_price':round(sl,4),'risk_abs':round(risk,4),'risk_pct':round((entry_price/sl-1)*100,4),'tp1':round(n(tp1.get('price')) if tp1 else 0,4),'tp2':round(n(tp2.get('price')) if tp2 else 0,4),'tp3':round(n(tp3.get('price')) if tp3 else 0,4),'tp':round(n(tp2.get('price')) if tp2 else 0,4),'tp1_rr':round(n(tp1.get('rr')) if tp1 else 0,4),'tp2_rr':round(rr2,4),'tp3_rr':round(rr3,4),'rr':round(rr2,4),'tp1_target_type':tp1.get('target_type','') if tp1 else '', 'tp2_target_type':tp2.get('target_type','') if tp2 else '', 'tp3_target_type':tp3.get('target_type','') if tp3 else '', 'structural_targets':targets[:20], 'structural_sl_ref':sl_ref})
    return simulate(ks,r)

def runner_reprice(row, ks):
    # Current entry/SL/TP, but planned legs: 20% TP1 + 50% TP2 + 30% runner to TP3 or SL after TP2.
    ep=n(row.get('entry_price')); sl=n(row.get('sl')); tp1=n(row.get('tp1')); tp2=n(row.get('tp2')); tp3=n(row.get('tp3'))
    ei=int(n(row.get('entry_idx'),-1)); risk=ep-sl
    if ei<0 or risk<=0: return None
    hit1=False; hit2=False; runner_exit=ep; exit_idx=min(len(ks)-1,ei+MAX_HOLD); reason='TIME_STOP'
    for i in range(ei+1,min(len(ks),ei+MAX_HOLD+1)):
        h=n(ks[i].get('h')); l=n(ks[i].get('l')); c=n(ks[i].get('c'))
        if not hit2 and l<=sl:
            exit_idx=i; runner_exit=sl; reason='SL_HIT'; break
        if tp1 and h>=tp1: hit1=True
        if tp2 and h>=tp2: hit2=True
        if hit2:
            if tp3 and h>=tp3:
                exit_idx=i; runner_exit=tp3; reason='TP3_RUNNER_HIT'; break
            if l<=ep:  # after TP2 protect runner at breakeven, not original SL
                exit_idx=i; runner_exit=ep; reason='RUNNER_BE_AFTER_TP2'; break
        runner_exit=c
    if not hit2:
        pnl=(runner_exit/ep-1)*100
    else:
        tp1_pnl=(tp1/ep-1)*100 if hit1 and tp1 else 0
        tp2_pnl=(tp2/ep-1)*100
        run_pnl=(runner_exit/ep-1)*100
        pnl=0.2*tp1_pnl+0.5*tp2_pnl+0.3*run_pnl
    r=dict(row); r.update({'variant':'exit_20_50_30_runner_be_after_tp2','exit_idx':exit_idx,'exit_date':bar_date(ks[exit_idx]),'exit_price':round(runner_exit,4),'exit_reason':reason,'pnl_pct':round(pnl,4),'hit_tp1':hit1,'hit_tp2':hit2,'hold_bars_realized':exit_idx-ei})
    return r

def main():
    rows=[r for r in load(TRADE_PATH,[]) if r.get('production_grade')=='A_PRODUCTION']
    kc={}
    variants=defaultdict(list)
    variants['current']=rows
    for r in rows:
        sym=r.get('symbol')
        if sym not in kc: kc[sym]=kline(sym)
        ks=kc[sym]
        if not ks: continue
        zl=n(r.get('zone_low')); zh=n(r.get('zone_high')); mid=(zl+zh)/2 if zl and zh else n(r.get('entry_price'))
        reclaim=int(n(r.get('reclaim_idx'),-1)); touch=int(n(r.get('touch_idx'),-1))
        if reclaim>=0:
            # Fix candidate 1: semantic next-open after reclaim, no pre-confirmation fill.
            idx=reclaim+1
            if idx < len(ks)-2:
                entry=n(ks[idx].get('o')) or n(ks[idx].get('c'))
                x=rebuild(r,ks,idx,entry,'entry_next_open_after_reclaim')
                if x: variants['entry_next_open_after_reclaim'].append(x)
            # Fix candidate 2: wait for post-reclaim retest of zone mid within 6 bars.
            idx=fill_from(ks,reclaim+1,reclaim+6,mid)
            if idx>=0:
                x=rebuild(r,ks,idx,mid,'entry_zone_mid_retest_after_reclaim')
                if x: variants['entry_zone_mid_retest_after_reclaim'].append(x)
            # Fix candidate 3: post-reclaim deeper zone_low retest.
            idx=fill_from(ks,reclaim+1,reclaim+8,zl)
            if idx>=0:
                x=rebuild(r,ks,idx,zl,'entry_zone_low_retest_after_reclaim')
                if x: variants['entry_zone_low_retest_after_reclaim'].append(x)
        x=runner_reprice(r,ks)
        if x: variants['exit_runner_after_tp2'].append(x)
    report={}
    for name,rs in variants.items():
        report[name]={'overall':stat(rs),'yearly':by_year(rs)}
    # combined: safer entry retest + runner exit on that population
    combo=[]
    for r in variants['entry_zone_mid_retest_after_reclaim']:
        sym=r.get('symbol')
        ks=kc.get(sym) or kline(sym)
        x=runner_reprice(r,ks)
        if x:
            x['variant']='entry_mid_after_reclaim_plus_runner'
            combo.append(x)
    report['entry_mid_after_reclaim_plus_runner']={'overall':stat(combo),'yearly':by_year(combo)}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2)[:12000])
    print('WROTE',OUT)

if __name__=='__main__': main()
