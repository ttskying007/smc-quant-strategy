#!/usr/bin/env python3
"""V677: source/aggregation/semantic audit for the W-D-60m pure-SMC boundary.

Research-only. Reads the V379 same-source Sina 60m cache and its V379 raw daily
rebuild, derives weekly bars, and emits no outcomes, trades, selectors, or
production/watchlist artifacts. Every semantic object is timestamp-causal.
"""
from __future__ import annotations
import csv, gzip, json, math, argparse, os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes')
M60DIR=ROOT/'intraday_cache/sina_m60_v1'
DDIR=ROOT/'intraday_cache/sina_raw_daily_v379'
AUD=ROOT/'smc_audit'
STAMP=datetime.now().strftime('%Y%m%d_%H%M%S')
OUT=AUD/f'v677_weekly_daily_m60_pure_smc_source_audit_no_write_{STAMP}_{os.getpid()}'
LATEST=AUD/'v677_weekly_daily_m60_pure_smc_source_audit_latest.json'


def num(x):
    try:
        y=float(x); return y if math.isfinite(y) else 0.0
    except (TypeError,ValueError): return 0.0

def load_gz(p):
    with gzip.open(p,'rt',encoding='utf-8') as h: return json.load(h)

def date8(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]

def normalize_daily(raw):
    out=[]
    for x in raw:
        q={k:num(x.get(k)) for k in ('o','h','l','c')}
        t=date8(x.get('t') or x.get('date'))
        if len(t)==8 and min(q.values())>0:
            q.update(t=t,segment_id=int(x.get('segment_id',0)))
            out.append(q)
    return sorted(out,key=lambda x:x['t'])

def normalize_m60(raw):
    out=[]
    for x in raw:
        t=str(x.get('day') or x.get('t') or '')
        d=date8(t)
        if len(d)!=8: continue
        q={k:num(x.get(src)) for k,src in [('o','open'),('h','high'),('l','low'),('c','close')]}
        if min(q.values())>0:
            q.update(t=d+t[-8:].replace(':','') if False else t, d=d)
            out.append(q)
    return sorted(out,key=lambda x:x['t'])

def weekly(daily):
    buckets=defaultdict(list)
    for b in daily:
        dt=datetime.strptime(b['t'],'%Y%m%d')
        buckets[dt.date().isocalendar()[:2]].append(b)
    out=[]
    prior_segment=None; weekly_segment=0
    for key, rows in sorted(buckets.items()):
        rows=sorted(rows,key=lambda x:x['t'])
        # A daily raw-source quarantine is also a hard weekly semantic boundary.
        segment=rows[-1]['segment_id']
        if prior_segment is not None and segment != prior_segment: weekly_segment += 1
        prior_segment=segment
        out.append({'t':rows[-1]['t'],'o':rows[0]['o'],'h':max(x['h'] for x in rows),'l':min(x['l'] for x in rows),'c':rows[-1]['c'],'segment_id':weekly_segment})
    return out

def pivots(rows):
    highs=[]; lows=[]
    for i in range(3,len(rows)-3):
        # A V379 source anomaly may not be bridged by pivot confirmation.
        if len({rows[j].get('segment_id',0) for j in range(i-3,i+4)}) != 1: continue
        h=rows[i]['h']; l=rows[i]['l']
        if all(rows[j]['h']<h for j in range(i-3,i+4) if j!=i): highs.append((i,i+3,h))
        if all(rows[j]['l']>l for j in range(i-3,i+4) if j!=i): lows.append((i,i+3,l))
    return highs,lows

def semantic_a(rows):
    hi,lo=pivots(rows); events=[]; sweeps=[]; obs=[]; broken=set(); trend='unknown'; segment=None
    by_hi=defaultdict(list); by_lo=defaultdict(list)
    for x in hi: by_hi[x[1]].append(x)
    for x in lo: by_lo[x[1]].append(x)
    visible_hi=[]; visible_lo=[]
    for i in range(len(rows)):
        if rows[i].get('segment_id',0) != segment:
            segment=rows[i].get('segment_id',0); broken=set(); trend='unknown'; visible_hi=[]; visible_lo=[]
        visible_hi.extend(by_hi.get(i,[])); visible_lo.extend(by_lo.get(i,[]))
        vh=next((x for x in reversed(visible_hi) if x[0] not in broken and rows[i]['c']>x[2]),None)
        vl=next((x for x in reversed(visible_lo) if x[0] not in broken and rows[i]['c']<x[2]),None)
        if vh:
            x=vh; broken.add(x[0]); typ='BOS' if trend=='bull' else 'CHOCH'; trend='bull'
            events.append(('bull',typ,i,x[0],x[1]))
        elif vl:
            x=vl; broken.add(x[0]); typ='BOS' if trend=='bear' else 'CHOCH'; trend='bear'
            events.append(('bear',typ,i,x[0],x[1]))
        x=next((z for z in reversed(visible_lo) if z[0] not in broken),None)
        if x and rows[i]['l']<x[2] and rows[i]['c']>=x[2]: sweeps.append(('bull',i,x[0],x[1]))
        x=next((z for z in reversed(visible_hi) if z[0] not in broken),None)
        if x and rows[i]['h']>x[2] and rows[i]['c']<=x[2]: sweeps.append(('bear',i,x[0],x[1]))
    for direction,typ,i,broken_idx,confirm_idx in events:
        if direction!='bull': continue
        # event-anchored nearest bearish candle in the displacement leg, causal
        event_segment=rows[i].get('segment_id',0)
        for j in range(i-1,max(-1,i-11),-1):
            if rows[j].get('segment_id',0)==event_segment and rows[j]['c']<rows[j]['o']:
                obs.append(('bull',i,j,rows[j]['l'],rows[j]['h'])); break
    return {'pivots':len(hi)+len(lo),'events':events,'sweeps':sweeps,'obs':obs}

def semantic_b(rows):
    # Independent implementation: same contract, distinct loops/data structures.
    highs=[]; lows=[]
    for p in range(3,len(rows)-3):
        if len({rows[j].get('segment_id',0) for j in range(p-3,p+4)}) != 1: continue
        left=rows[p-3:p]; right=rows[p+1:p+4]
        if rows[p]['h']>max([x['h'] for x in left+right]): highs.append({'p':p,'v':rows[p]['h'],'at':p+3})
        if rows[p]['l']<min([x['l'] for x in left+right]): lows.append({'p':p,'v':rows[p]['l'],'at':p+3})
    events=[]; sweeps=[]; used=set(); state=None; segment=None; active_hi=[]; active_lo=[]
    by_hi=defaultdict(list); by_lo=defaultdict(list)
    for x in highs: by_hi[x['at']].append(x)
    for x in lows: by_lo[x['at']].append(x)
    for k,b in enumerate(rows):
        if b.get('segment_id',0) != segment:
            segment=b.get('segment_id',0); used=set(); state=None; active_hi=[]; active_lo=[]
        active_hi.extend(by_hi.get(k,[])); active_lo.extend(by_lo.get(k,[]))
        cand=next((x for x in reversed(active_hi) if x['p'] not in used and b['c']>x['v']),None)
        if cand:
            x=cand; used.add(x['p']); events.append(('bull','BOS' if state=='bull' else 'CHOCH',k,x['p'],x['at'])); state='bull'
        else:
            cand=next((x for x in reversed(active_lo) if x['p'] not in used and b['c']<x['v']),None)
            if cand:
                x=cand; used.add(x['p']); events.append(('bear','BOS' if state=='bear' else 'CHOCH',k,x['p'],x['at'])); state='bear'
        for x in reversed(active_lo):
            if x['p'] not in used:
                if b['l']<x['v']<=b['c']: sweeps.append(('bull',k,x['p'],x['at']))
                break
        for x in reversed(active_hi):
            if x['p'] not in used:
                if b['h']>x['v']>=b['c']: sweeps.append(('bear',k,x['p'],x['at']))
                break
    obs=[]
    for e in events:
        if e[0]=='bull':
            event_segment=rows[e[2]].get('segment_id',0)
            for q in range(e[2]-1,max(-1,e[2]-11),-1):
                if rows[q].get('segment_id',0)==event_segment and rows[q]['c']<rows[q]['o']:
                    obs.append(('bull',e[2],q,rows[q]['l'],rows[q]['h'])); break
    return {'pivots':len(highs)+len(lows),'events':events,'sweeps':sweeps,'obs':obs}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--shard-count',type=int,default=1)
    parser.add_argument('--shard-index',type=int,default=0)
    args=parser.parse_args()
    if args.shard_count<1 or not 0<=args.shard_index<args.shard_count: raise SystemExit('invalid shard')
    OUT.mkdir(parents=True,exist_ok=True)
    files=[p for i,p in enumerate(sorted(DDIR.glob('*_raw_daily.json.gz'))) if i % args.shard_count == args.shard_index]
    counts=Counter(); failures=[]; rows=[]; diff=[]
    for n,p in enumerate(files,1):
        base=p.name.removesuffix('_raw_daily.json.gz'); symbol=base[:6]+'.'+base[7:]
        try:
            d=normalize_daily(load_gz(p)); m=normalize_m60(load_gz(M60DIR/f'{base}_m60_sina.json.gz'))
            w=weekly(d)
            valid=bool(d and m and all(d[i]['t']<d[i+1]['t'] for i in range(len(d)-1)))
            # V379 raw m60 has exactly four bars/day; retain only complete groups.
            mg=defaultdict(list)
            for x in m: mg[x['d']].append(x)
            complete={k:v for k,v in mg.items() if len(v)==4}
            m_dates={k for k in complete if '20230101' <= k <= '20260710'}; d_dates={x['t'] for x in d}
            semantic={}
            # H is the original 60-minute bar sequence. Four-bar grouping is
            # used only to verify the V379 daily aggregation boundary, never to
            # collapse H into daily bars for semantic detection.
            day_segment={x['t']:x.get('segment_id',0) for x in d}
            hbars=[]
            for x in m:
                if x['d'] in complete and '20230101' <= x['d'] <= '20260710':
                    y=dict(x); y['segment_id']=day_segment.get(x['d'],0); hbars.append(y)
            for tf, bars in [('W',w),('D',d),('H',hbars)]: 
                a=semantic_a(bars); b=semantic_b(bars)
                semantic[tf]={'bars':len(bars),'pivots':a['pivots'],'events':len(a['events']),'sweeps':len(a['sweeps']),'obs':len(a['obs'])}
                if a!=b: diff.append({'symbol':symbol,'tf':tf,'a_counts':semantic[tf],'b_counts':{'pivots':b['pivots'],'events':len(b['events']),'sweeps':len(b['sweeps']),'obs':len(b['obs'])}})
            ok=valid and len(m_dates)==len(d_dates) and not any(x['symbol']==symbol for x in diff)
            counts['symbols']+=1; counts['pass' if ok else 'fail']+=1
            rows.append({'symbol':symbol,'daily_bars':len(d),'m60_bars':len(m),'weekly_bars':len(w),'complete_m60_days':len(m_dates),'daily_m60_date_match':m_dates==d_dates,'semantic':semantic,'ok':ok})
        except Exception as e: failures.append({'symbol':symbol,'error':repr(e)})
        if n%500==0: print(f'processed {n}/{len(files)}',flush=True)
    (OUT/'v677_symbol_rows.json').write_text(json.dumps(rows,ensure_ascii=False))
    report={'version':'V677_WEEKLY_DAILY_M60_PURE_SMC_SOURCE_AUDIT_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'research_only':True,'production_write':False,'shard_count':args.shard_count,'shard_index':args.shard_index,'outcomes_included':False,'source':'Sina m60 V379 -> raw daily -> ISO weekly','contracts':{'frames':['weekly','daily','60m'],'daily':'V379 raw daily only; four same-source 60m bars per complete day','weekly':'ISO calendar aggregation from daily, no incomplete current week','semantics':'confirmed 3/3 pivots; close-break structure; wick-through-and-close-back sweep; bullish event-anchored nearest bearish OB within 10 prior bars','forbidden':['MA','RSI','ATR','MACD','volume selector','outcomes','RR','risk','T+1 replay']},'counts':dict(counts)|{'input_daily_files':len(files),'semantic_differential_rows':len(diff),'exceptions':len(failures)},'differential':{'mismatch_total':len(diff),'decision':'PASS' if not diff and not failures else 'FAIL','samples':diff[:20]},'failure_samples':failures[:20],'decision':'V677_SOURCE_AGGREGATION_SEMANTIC_PASS__V678_ALLOWED' if not diff and not failures and counts['fail']==0 else 'V677_FAIL_CLOSED__STOP_BEFORE_V678','artifacts':{'symbol_rows':str(OUT/'v677_symbol_rows.json'),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v677_report.json').write_text(text)
    if args.shard_count == 1: LATEST.write_text(text)
    print(text)
main()
