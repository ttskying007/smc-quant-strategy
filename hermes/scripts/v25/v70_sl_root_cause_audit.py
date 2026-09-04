#!/usr/bin/env python3
"""V70 root-cause audit for V68/V69 failures.

Diagnoses every V68 SL and TP trade against the raw daily K-line cache.
Focus: zone_dead root cause, signal accuracy, trend context, entry timing,
position in zone, and TP/SL geometry. No production writes.
"""
from __future__ import annotations
import json, statistics, math
from pathlib import Path
from collections import Counter, defaultdict
from typing import Any, Dict, List

ROOT = Path('/root/.hermes')
TRADES = ROOT / 'smc_opt_v68_strict_ld' / 'v68_trades.json'
KLINE = ROOT / 'kline_cache'
OUT_DIR = ROOT / 'smc_opt_v70_root_cause'
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT = OUT_DIR / 'v70_sl_root_cause_audit.json'
MD = OUT_DIR / 'v70_sl_root_cause_audit.md'
MAX_HOLD = 60

def f(x: Any, default: float=0.0) -> float:
    try:
        if x is None or x == '': return default
        v = float(x)
        return v if math.isfinite(v) else default
    except Exception:
        return default

def ma(vals, n):
    if len(vals) < n: return None
    return sum(vals[-n:]) / n

def load_ks(symbol: str):
    fn = symbol.replace('.SH','_SH').replace('.SZ','_SZ').replace('.BJ','_BJ') + '_daily_750.json'
    p = KLINE / fn
    if not p.exists(): return None
    ks = json.loads(p.read_text())
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k] = f(b[k])
    return ks

def date_idx(ks, date):
    sd = str(date)[:8]
    for i,b in enumerate(ks):
        if str(b.get('t') or b.get('date') or '')[:8] == sd:
            return i
    return None

def atr(ks, idx, n=14):
    trs=[]
    for i in range(max(1,idx-n+1), idx+1):
        h,l,pc=f(ks[i].get('h')),f(ks[i].get('l')),f(ks[i-1].get('c'))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.0

def swing_low(ks, i, left=3, right=3):
    if i-left < 0 or i+right >= len(ks): return False
    lo=f(ks[i].get('l'))
    return all(f(ks[j].get('l')) > lo for j in range(i-left,i)) and all(f(ks[j].get('l')) >= lo for j in range(i+1,i+right+1))

def swing_high(ks, i, left=3, right=3):
    if i-left < 0 or i+right >= len(ks): return False
    hi=f(ks[i].get('h'))
    return all(f(ks[j].get('h')) < hi for j in range(i-left,i)) and all(f(ks[j].get('h')) <= hi for j in range(i+1,i+right+1))

def recent_structure(ks, idx, lookback=80):
    lows=[]; highs=[]
    for i in range(max(3, idx-lookback), max(3, idx-3)+1):
        if swing_low(ks,i): lows.append((i,f(ks[i].get('l'))))
        if swing_high(ks,i): highs.append((i,f(ks[i].get('h'))))
    return lows, highs

def trend_context(ks, idx):
    closes=[f(b.get('c')) for b in ks[:idx+1]]
    c=closes[-1]
    m20=ma(closes,20); m60=ma(closes,60); m120=ma(closes,120)
    ret20=(c/closes[-21]-1)*100 if len(closes)>21 and closes[-21] else 0
    ret60=(c/closes[-61]-1)*100 if len(closes)>61 and closes[-61] else 0
    hi60=max(f(b.get('h')) for b in ks[max(0,idx-60):idx+1])
    lo60=min(f(b.get('l')) for b in ks[max(0,idx-60):idx+1])
    pos60=(c-lo60)/max(hi60-lo60,1e-9)*100
    if m20 and m60 and c>m20>m60 and ret20>0: state='TREND_UP'
    elif m20 and m60 and c<m20<m60 and ret20<0: state='TREND_DOWN'
    elif ret60 < -8: state='DOWN_60'
    elif ret20 > 5 and pos60 > 75: state='EXTENDED_UP'
    else: state='RANGE_TRANSITION'
    return {'trend_state':state,'ret20':round(ret20,2),'ret60':round(ret60,2),'pos60':round(pos60,1),'above_ma20': bool(m20 and c>m20),'above_ma60': bool(m60 and c>m60)}

def classify_trade(t):
    ks=load_ks(t['symbol'])
    if not ks: return None
    ei = int(t.get('entry_idx') if t.get('entry_idx') is not None else date_idx(ks,t.get('entry_date')) or -1)
    xi = int(t.get('exit_idx') if t.get('exit_idx') is not None else date_idx(ks,t.get('exit_date')) or -1)
    if ei<0 or xi<0 or ei>=len(ks) or xi>=len(ks): return None
    ep,sl,tp,zl,zh = map(f,[t.get('entry_price'),t.get('sl'),t.get('tp1'),t.get('zone_low'),t.get('zone_high')])
    R = ep-sl
    eb, xb = ks[ei], ks[xi]
    entry_low, entry_high, entry_close = f(eb.get('l')), f(eb.get('h')), f(eb.get('c'))
    exit_open, exit_low, exit_close, exit_high = f(xb.get('o')), f(xb.get('l')), f(xb.get('c')), f(xb.get('h'))
    lows, highs = recent_structure(ks, ei, 80)
    last_low_bar,last_low = lows[-1] if lows else (None,0)
    last_high_bar,last_high = highs[-1] if highs else (None,0)
    zone_width = zh-zl
    entry_zone_pos=(ep-zl)/max(zone_width,1e-9)*100
    entry_bar_zone_pierce=(zh-entry_low)/max(zone_width,1e-9)*100
    delay_confirm = ei-int(t.get('confirm_bar',ei))
    delay_zone = ei-int(t.get('zone_bar',ei))
    tr = trend_context(ks, ei)
    # MFE/MAE before exit
    mfe=0; mae=0; first_hit_halfR=None; first_close_below_zone=None
    for j in range(ei+1, min(len(ks), ei+MAX_HOLD+1)):
        hi=f(ks[j].get('h')); lo=f(ks[j].get('l')); cl=f(ks[j].get('c'))
        mfe=max(mfe, hi-ep); mae=max(mae, ep-lo)
        if first_hit_halfR is None and hi >= ep + 0.5*R: first_hit_halfR=j
        if first_close_below_zone is None and cl < zl: first_close_below_zone=j
        if j>=xi: break
    after_recover_tp=False; after_reclaim_zone=False
    for j in range(xi+1, min(len(ks), ei+MAX_HOLD+1)):
        if f(ks[j].get('h')) >= tp: after_recover_tp=True
        if f(ks[j].get('c')) >= zh: after_reclaim_zone=True
    tags=[]
    if t.get('exit_reason')=='SL_HIT':
        if exit_open < sl: tags.append('GAP_SL')
        elif exit_close > sl: tags.append('WICK_SL')
        else: tags.append('CLOSE_SL')
        if exit_close < zl: tags.append('ZONE_DEAD_CLOSE_BELOW_LOW')
        if exit_close < last_low and last_low>0: tags.append('STRUCTURE_BROKEN')
        if delay_confirm <= 2: tags.append('ENTRY_TOO_EARLY_AFTER_CONFIRM')
        if delay_confirm >= 9: tags.append('ENTRY_TOO_LATE_STALE')
        if entry_zone_pos >= 70: tags.append('ENTRY_TOO_HIGH_IN_ZONE')
        if entry_bar_zone_pierce >= 100: tags.append('DEEP_ZONE_PIERCE_ON_ENTRY')
        if tr['trend_state'] in ('TREND_DOWN','DOWN_60'): tags.append('TREND_WRONG')
        if tr['trend_state']=='EXTENDED_UP': tags.append('CHASED_EXTENDED_UP')
        if mfe/max(R,1e-9) >= 0.5: tags.append('TP_TOO_FAR_OR_NO_TRAIL')
        if after_recover_tp: tags.append('SL_TOO_TIGHT_RECOVERED')
        if first_close_below_zone is not None and first_close_below_zone-ei <= 3: tags.append('ZONE_FAILED_IMMEDIATELY')
    return {
        'symbol':t['symbol'],'entry_date':t.get('entry_date'),'exit_date':t.get('exit_date'),'exit_reason':t.get('exit_reason'),'pnl_pct':f(t.get('pnl_pct')),
        'risk_pct':f(t.get('risk_pct')),'retrace_pct':f(t.get('retrace_pct')),'pierce_atr':f(t.get('pierce_atr')),'disp_atr':f(t.get('disp_atr')),
        'delay_confirm':delay_confirm,'delay_zone':delay_zone,'entry_zone_pos':round(entry_zone_pos,1),'entry_bar_zone_pierce':round(entry_bar_zone_pierce,1),
        'mfe_r':round(mfe/max(R,1e-9),2),'mae_r':round(mae/max(R,1e-9),2),'first_halfR_bars': None if first_hit_halfR is None else first_hit_halfR-ei,
        'first_close_below_zone_bars': None if first_close_below_zone is None else first_close_below_zone-ei,
        'last_swing_low_distance': None if last_low_bar is None else ei-last_low_bar,'last_swing_high_distance': None if last_high_bar is None else ei-last_high_bar,
        **tr,'tags':tags,
        'primary_root': root_priority(tags, t.get('exit_reason')),
    }

def root_priority(tags, exit_reason):
    if exit_reason!='SL_HIT': return 'WIN_OR_TIME'
    order=['TREND_WRONG','ZONE_FAILED_IMMEDIATELY','ENTRY_TOO_HIGH_IN_ZONE','ENTRY_TOO_EARLY_AFTER_CONFIRM','ENTRY_TOO_LATE_STALE','TP_TOO_FAR_OR_NO_TRAIL','SL_TOO_TIGHT_RECOVERED','GAP_SL','WICK_SL','CLOSE_SL']
    for o in order:
        if o in tags: return o
    return 'UNCLASSIFIED_SL'

def metrics(rows):
    if not rows: return {'n':0}
    pnls=[r['pnl_pct'] for r in rows]
    wins=[p for p in pnls if p>0]
    return {'n':len(rows),'wr':round(len(wins)/len(rows)*100,2),'avg':round(sum(pnls)/len(pnls),4),'sl_rate':round(sum(1 for r in rows if r['exit_reason']=='SL_HIT')/len(rows)*100,2)}

def bucket(rows, field):
    g=defaultdict(list)
    for r in rows:
        v=r.get(field)
        if isinstance(v,float): v=round(v,2)
        g[str(v)].append(r)
    return {k:metrics(v) for k,v in sorted(g.items(), key=lambda kv: str(kv[0]))}

def main():
    raw=json.loads(TRADES.read_text())
    rows=[]
    for i,t in enumerate(raw,1):
        r=classify_trade(t)
        if r: rows.append(r)
        if i%1000==0: print('classified',i,flush=True)
    sl=[r for r in rows if r['exit_reason']=='SL_HIT']
    tp=[r for r in rows if r['exit_reason']=='TP1_HIT']
    tag_counts=Counter(tag for r in sl for tag in r['tags'])
    root_counts=Counter(r['primary_root'] for r in sl)
    report={
        'source':str(TRADES),'generated_at':__import__('datetime').datetime.now().isoformat(timespec='seconds'),
        'overall':metrics(rows),'sl_metrics':metrics(sl),'tp_metrics':metrics(tp),
        'sl_tag_counts':dict(tag_counts.most_common()),'sl_primary_root_counts':dict(root_counts.most_common()),
        'buckets':{
            'trend_state':bucket(rows,'trend_state'),'primary_root':bucket(rows,'primary_root'),
            'delay_confirm':bucket(rows,'delay_confirm'),'risk_pct_rounded':bucket([{**r,'risk_pct_rounded':int(r['risk_pct'])} for r in rows],'risk_pct_rounded'),
            'retrace_bin': bucket([{**r,'retrace_bin':'30-60' if r['retrace_pct']<60 else '60-90'} for r in rows],'retrace_bin'),
            'entry_zone_pos_bin': bucket([{**r,'entry_zone_pos_bin':'low<40' if r['entry_zone_pos']<40 else ('mid40-70' if r['entry_zone_pos']<70 else 'high>=70')} for r in rows],'entry_zone_pos_bin'),
            'mfe_r_bin': bucket([{**r,'mfe_r_bin':'<0.25R' if r['mfe_r']<0.25 else ('0.25-0.5R' if r['mfe_r']<0.5 else ('0.5-0.8R' if r['mfe_r']<0.8 else '>=0.8R'))} for r in rows],'mfe_r_bin'),
        },
        'sl_samples_by_root':{}, 'all_classified_count':len(rows)
    }
    for root,_ in root_counts.most_common():
        report['sl_samples_by_root'][root]=[r for r in sl if r['primary_root']==root][:30]
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    lines=['# V70 SL Root Cause Audit','','| scope | n | WR | avg | SL率 |','|---|---:|---:|---:|---:|',f"| all | {report['overall']['n']} | {report['overall']['wr']} | {report['overall']['avg']} | {report['overall']['sl_rate']} |",'', '## SL主因分布','| root | count | pct |','|---|---:|---:|']
    for k,v in root_counts.most_common(): lines.append(f'| {k} | {v} | {round(v/max(len(sl),1)*100,1)} |')
    lines += ['','## SL标签分布','| tag | count | pct |','|---|---:|---:|']
    for k,v in tag_counts.most_common(): lines.append(f'| {k} | {v} | {round(v/max(len(sl),1)*100,1)} |')
    lines += ['','## 趋势桶','| trend | n | WR | avg | SL率 |','|---|---:|---:|---:|---:|']
    for k,m in report['buckets']['trend_state'].items(): lines.append(f"| {k} | {m['n']} | {m['wr']} | {m['avg']} | {m['sl_rate']} |")
    MD.write_text('\n'.join(lines)+'\n')
    print(json.dumps({'overall':report['overall'],'sl_primary_root_counts':report['sl_primary_root_counts'],'sl_tag_counts':dict(tag_counts.most_common(12)),'outputs':{'json':str(OUT),'md':str(MD)}},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
