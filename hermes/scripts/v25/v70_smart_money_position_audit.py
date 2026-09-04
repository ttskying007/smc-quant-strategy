#!/usr/bin/env python3
"""V70 Smart Money Position Audit for V68 L→D/FVG trades.

Purpose: verify Lei's hypothesis:
- 97% zone-dead means price did not really enter/hold a smart-money position.
- The failure may be trend/context detection or signal semantics: FVG fill != smart money demand.

Audits every V68 trade using only information up to entry bar:
1) Premium/discount/OTE position of entry relative to sweep-low -> displacement-high impulse.
2) Whether FVG is merely filled/mitigated instead of reacting.
3) Whether there is OB/body confluence near the FVG.
4) Whether post-touch reaction confirmation exists before entry.
5) Whether structure/trend context is already broken before entry.

No production writes.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path('/root/.hermes')
TRADES = ROOT/'smc_opt_v68_strict_ld'/'v68_trades.json'
KLINE = ROOT/'kline_cache'
OUT_DIR = ROOT/'smc_opt_v70_root_cause'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR/'v70_smart_money_position_audit.json'
MD = OUT_DIR/'v70_smart_money_position_audit.md'

def f(x: Any, default: float=0.0) -> float:
    try:
        if x is None or x == '': return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default

def d(b: Dict[str, Any]) -> str:
    return str(b.get('t') or b.get('date') or '')[:8]

def load_ks(symbol: str):
    p = KLINE/(symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_750.json')
    if not p.exists(): return None
    try: ks=json.loads(p.read_text())
    except Exception: return None
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    return ks

def atr(ks, idx, n=14):
    trs=[]
    for i in range(max(1,idx-n+1), idx+1):
        h,l,pc=f(ks[i].get('h')),f(ks[i].get('l')),f(ks[i-1].get('c'))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.0

def is_swing_low(ks,i,L=3,R=3):
    if i-L<0 or i+R>=len(ks): return False
    lo=f(ks[i].get('l'))
    return all(f(ks[j].get('l'))>lo for j in range(i-L,i)) and all(f(ks[j].get('l'))>=lo for j in range(i+1,i+R+1))

def is_swing_high(ks,i,L=3,R=3):
    if i-L<0 or i+R>=len(ks): return False
    hi=f(ks[i].get('h'))
    return all(f(ks[j].get('h'))<hi for j in range(i-L,i)) and all(f(ks[j].get('h'))<=hi for j in range(i+1,i+R+1))

def recent_swings(ks, idx, lookback=80):
    lows=[]; highs=[]
    for i in range(max(3,idx-lookback), max(3,idx-3)+1):
        if is_swing_low(ks,i): lows.append((i,f(ks[i].get('l'))))
        if is_swing_high(ks,i): highs.append((i,f(ks[i].get('h'))))
    return lows, highs

def find_last_down_candle(ks, lbar, dbar):
    for j in range(dbar-1, max(lbar-1,dbar-12), -1):
        op,cl=f(ks[j].get('o')),f(ks[j].get('c'))
        if cl < op:
            return {'bar':j,'low':f(ks[j].get('l')),'high':max(op,cl),'body_low':cl,'body_high':op}
    return None

def overlap_ratio(a_low,a_high,b_low,b_high):
    lo=max(a_low,b_low); hi=min(a_high,b_high)
    if hi<=lo: return 0.0
    return (hi-lo)/max(min(a_high-a_low,b_high-b_low),1e-9)

def impulse_position(ks, t):
    lbar=int(t.get('liq_bar')); dbar=int(t.get('confirm_bar')); eidx=int(t.get('entry_idx'))
    # use actual sweep low and displacement high; if sweep low unavailable fallback to liq price/zone low.
    low=f(ks[lbar].get('l')) if 0<=lbar<len(ks) else f(t.get('zone_low'))
    high=max(f(ks[i].get('h')) for i in range(lbar, dbar+1)) if 0<=lbar<=dbar<len(ks) else f(ks[dbar].get('h'))
    ep=f(t.get('entry_price'))
    rng=max(high-low,1e-9)
    pos=(ep-low)/rng*100
    # For long, discount is below EQ: <50%. OTE is 21-38.2% from low if measured low->high (equivalent 61.8-79% retracement from high).
    if pos <= 21: zone='DEEP_DISCOUNT_OR_BREAK'
    elif pos <= 38.2: zone='OTE_DISCOUNT'
    elif pos <= 50: zone='DISCOUNT'
    elif pos <= 61.8: zone='EQUILIBRIUM_PREMIUM_EDGE'
    else: zone='PREMIUM_CHASE'
    return {'impulse_low':low,'impulse_high':high,'impulse_pos_pct':round(pos,2),'pd_zone':zone}

def reaction_before_entry(ks,t):
    zl,zh=f(t.get('zone_low')),f(t.get('zone_high'))
    dbar=int(t.get('confirm_bar')); zbar=int(t.get('zone_bar')); eidx=int(t.get('entry_idx'))
    touch=None; close_below=False; reclaim_high=False; two_bar=False
    for i in range(max(dbar+1,zbar+1), eidx+1):
        lo,hi,op,cl=f(ks[i].get('l')),f(ks[i].get('h')),f(ks[i].get('o')),f(ks[i].get('c'))
        if touch is None and lo<=zh and hi>=zl:
            touch=i
        if touch is not None:
            if cl < zl: close_below=True
            if i < eidx and cl > zh and cl > op: reclaim_high=True
            if i-1 >= touch and i < eidx:
                prev=f(ks[i-1].get('c'))
                if prev >= zl and cl > zh and cl > op: two_bar=True
    return {'touch_idx':touch,'touch_before_entry':touch is not None and touch<=eidx,'closed_below_zone_before_entry':close_below,'reclaim_high_before_entry':reclaim_high,'two_bar_reaction_before_entry':two_bar}

def trend_context(ks, idx):
    closes=[f(b.get('c')) for b in ks[:idx+1]]
    c=closes[-1]
    m20=sum(closes[-20:])/20 if len(closes)>=20 else None
    m60=sum(closes[-60:])/60 if len(closes)>=60 else None
    ret20=(c/closes[-21]-1)*100 if len(closes)>21 and closes[-21] else 0
    ret60=(c/closes[-61]-1)*100 if len(closes)>61 and closes[-61] else 0
    if m20 and m60 and c>m20>m60 and ret20>0: state='UP_CONTEXT'
    elif m20 and m60 and c<m20<m60 and ret20<0: state='DOWN_CONTEXT'
    elif ret60 < -8: state='DOWN_60'
    else: state='RANGE_OR_TRANSITION'
    return {'trend_context':state,'ret20':round(ret20,2),'ret60':round(ret60,2)}

def audit_trade(t):
    ks=load_ks(t['symbol'])
    if not ks: return None
    eidx=int(t.get('entry_idx')); lbar=int(t.get('liq_bar')); dbar=int(t.get('confirm_bar'))
    zl,zh=f(t.get('zone_low')),f(t.get('zone_high')); ep=f(t.get('entry_price'))
    pos=impulse_position(ks,t)
    react=reaction_before_entry(ks,t)
    tr=trend_context(ks,eidx)
    ob=find_last_down_candle(ks,lbar,dbar)
    ob_overlap=overlap_ratio(zl,zh,ob['low'],ob['high']) if ob else 0
    body_overlap=overlap_ratio(zl,zh,ob['body_low'],ob['body_high']) if ob else 0
    lows, highs=recent_swings(ks,eidx,80)
    last_low = lows[-1][1] if lows else 0
    last_high = highs[-1][1] if highs else 0
    structure_ok = ep > last_low if last_low else True
    # core SMC correctness: not just FVG filled; must be discount/OTE + OB/confluence + reaction + not down context.
    fails=[]
    if pos['pd_zone'] in ('EQUILIBRIUM_PREMIUM_EDGE','PREMIUM_CHASE'):
        fails.append('NOT_DISCOUNT_SM_POSITION')
    if pos['pd_zone']=='DEEP_DISCOUNT_OR_BREAK':
        fails.append('TOO_DEEP_OR_STRUCTURE_BREAK_RISK')
    if ob_overlap < 0.25 and body_overlap < 0.10:
        fails.append('NO_OB_SMART_MONEY_CONFLUENCE')
    if not react['reclaim_high_before_entry'] and not react['two_bar_reaction_before_entry']:
        fails.append('NO_REACTION_CONFIRMATION')
    if react['closed_below_zone_before_entry']:
        fails.append('ZONE_ALREADY_MITIGATED_OR_DEAD')
    if tr['trend_context'] in ('DOWN_CONTEXT','DOWN_60'):
        fails.append('TREND_CONTEXT_WRONG')
    if not structure_ok:
        fails.append('PRE_ENTRY_STRUCTURE_BROKEN')
    if f(t.get('retrace_pct')) >= 90:
        fails.append('FVG_FULLY_FILLED_NOT_SM_ENTRY')
    primary='VALID_SM_POSITION' if not fails else fails[0]
    # outcome zone dead after entry
    xi=int(t.get('exit_idx', -1)) if t.get('exit_idx') is not None else -1
    exit_close=f(ks[xi].get('c')) if 0<=xi<len(ks) else 0
    zone_dead_after = t.get('exit_reason')=='SL_HIT' and exit_close < zl
    return {
        'symbol':t['symbol'],'entry_date':t.get('entry_date'),'exit_date':t.get('exit_date'),'exit_reason':t.get('exit_reason'),'pnl_pct':f(t.get('pnl_pct')),
        'won':f(t.get('pnl_pct'))>0,'zone_dead_after':zone_dead_after,
        'risk_pct':f(t.get('risk_pct')),'retrace_pct':f(t.get('retrace_pct')),'entry_delay':eidx-dbar,
        'zone_low':zl,'zone_high':zh,'entry_price':ep,
        'ob_overlap':round(ob_overlap,3),'ob_body_overlap':round(body_overlap,3),'last_swing_low':last_low,'last_swing_high':last_high,
        **pos,**react,**tr,
        'sm_fail_reasons':fails,'primary_sm_failure':primary,
    }

def metrics(rows):
    if not rows: return {'n':0}
    wins=sum(r['won'] for r in rows); sl=sum(r['exit_reason']=='SL_HIT' for r in rows); zd=sum(r['zone_dead_after'] for r in rows)
    return {'n':len(rows),'wr':round(wins/len(rows)*100,2),'avg_pnl':round(sum(r['pnl_pct'] for r in rows)/len(rows),4),'sl_rate':round(sl/len(rows)*100,2),'zone_dead_rate':round(zd/len(rows)*100,2)}

def bucket(rows,fn):
    g=defaultdict(list)
    for r in rows: g[fn(r)].append(r)
    return {str(k):metrics(v) for k,v in sorted(g.items(),key=lambda kv:str(kv[0]))}

def main():
    raw=json.loads(TRADES.read_text())
    rows=[]
    for i,t in enumerate(raw,1):
        r=audit_trade(t)
        if r: rows.append(r)
        if i%1000==0: print('audited',i,flush=True)
    sl=[r for r in rows if r['exit_reason']=='SL_HIT']
    zd=[r for r in rows if r['zone_dead_after']]
    reason_counts=Counter(reason for r in rows for reason in r['sm_fail_reasons'])
    primary_all=Counter(r['primary_sm_failure'] for r in rows)
    primary_sl=Counter(r['primary_sm_failure'] for r in sl)
    primary_zd=Counter(r['primary_sm_failure'] for r in zd)
    report={
        'generated_at':__import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'source':str(TRADES),'overall':metrics(rows),'sl':metrics(sl),'zone_dead_after_sl':metrics(zd),
        'primary_failure_all':dict(primary_all.most_common()),
        'primary_failure_sl':dict(primary_sl.most_common()),
        'primary_failure_zone_dead':dict(primary_zd.most_common()),
        'all_reason_counts':dict(reason_counts.most_common()),
        'buckets':{
            'pd_zone':bucket(rows,lambda r:r['pd_zone']),
            'trend_context':bucket(rows,lambda r:r['trend_context']),
            'reaction_confirmation':bucket(rows,lambda r:'HAS_REACTION' if (r['reclaim_high_before_entry'] or r['two_bar_reaction_before_entry']) else 'NO_REACTION'),
            'ob_confluence':bucket(rows,lambda r:'OB_CONFLUENCE' if (r['ob_overlap']>=0.25 or r['ob_body_overlap']>=0.1) else 'NO_OB_CONFLUENCE'),
            'sm_validity':bucket(rows,lambda r:'VALID_SM_POSITION' if not r['sm_fail_reasons'] else 'INVALID_SM_POSITION'),
            'primary_failure':bucket(rows,lambda r:r['primary_sm_failure']),
        },
        'zone_dead_samples':zd[:100],
        'valid_sm_samples':[r for r in rows if not r['sm_fail_reasons']][:100],
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=['# V70 Smart Money Position Audit','','## 总览','| scope | n | WR | avg | SL率 | ZoneDead率 |','|---|---:|---:|---:|---:|---:|']
    for name,obj in [('all',report['overall']),('SL',report['sl']),('ZoneDead SL',report['zone_dead_after_sl'])]:
        lines.append(f"| {name} | {obj['n']} | {obj['wr']} | {obj['avg_pnl']} | {obj['sl_rate']} | {obj['zone_dead_rate']} |")
    lines += ['','## ZoneDead主因','| reason | count | pct of zone-dead |','|---|---:|---:|']
    for k,v in primary_zd.most_common(): lines.append(f'| {k} | {v} | {round(v/max(len(zd),1)*100,1)} |')
    lines += ['','## 所有交易SMC失败标签','| reason | count | pct all |','|---|---:|---:|']
    for k,v in reason_counts.most_common(): lines.append(f'| {k} | {v} | {round(v/max(len(rows),1)*100,1)} |')
    lines += ['','## 分桶','### PD位置','| bucket | n | WR | avg | SL | ZoneDead |','|---|---:|---:|---:|---:|---:|']
    for k,m in report['buckets']['pd_zone'].items(): lines.append(f"| {k} | {m['n']} | {m['wr']} | {m['avg_pnl']} | {m['sl_rate']} | {m['zone_dead_rate']} |")
    lines += ['','### 反应确认','| bucket | n | WR | avg | SL | ZoneDead |','|---|---:|---:|---:|---:|---:|']
    for k,m in report['buckets']['reaction_confirmation'].items(): lines.append(f"| {k} | {m['n']} | {m['wr']} | {m['avg_pnl']} | {m['sl_rate']} | {m['zone_dead_rate']} |")
    MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'overall':report['overall'],'zone_dead_primary':report['primary_failure_zone_dead'],'buckets':{k:report['buckets'][k] for k in ['pd_zone','reaction_confirmation','ob_confluence','sm_validity']},'outputs':{'json':str(OUT),'md':str(MD)}},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
