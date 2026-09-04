#!/usr/bin/env python3
"""V562 no-outcome seed: industry BOS -> constituent M15 SSL sweep/CHOCH.

Frozen exploratory ontology using existing source-isolated Sina 2025-2026 data:
1. An ex-stock daily industry composite breaks its latest *confirmed* 3L/3R
   swing high (bullish BOS) on date D.
2. On D the constituent independently performs a M15 sell-side liquidity
   sweep, reclaims that low, then closes through a pre-sweep confirmed lower
   high (CHOCH). The confirmed anchor must be known before the sweep.
3. The only eligible execution is D+1 daily open; this generator never reads
   daily bars at/after D+1, exit data, PnL, MFE, MAE, or prior replay rows.

This is a new cross-security parent-event generator, not a filter on V541,
V545, V551, V557, or their outcome rows.  It is exploratory because the
available source range is 2025-2026; its research support gate follows the
user's standing target: aggregate >=1000 and >=300 in each available year.
"""
from __future__ import annotations
import bisect, csv, gzip, json, math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes')
AUD=ROOT/'smc_audit'
DAILY=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/daily'
M15=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
INDMAP=AUD/'v225_baostock_industry_participation_probe_20260627_031854/baostock_stock_industry.json'
OUT=AUD/f'v562_industry_bos_m15_ssl_choch_seed_no_outcome_{datetime.now():%Y%m%d_%H%M%S}'
LATEST=AUD/'v562_industry_bos_m15_ssl_choch_seed_latest.json'
YEARS=('2025','2026')
MIN_PEERS=15


def f(x):
    try:
        v=float(x)
        return v if math.isfinite(v) and v>0 else None
    except (TypeError,ValueError):
        return None


def daily_bars(sym):
    try:
        with gzip.open(DAILY/f'{sym.replace(".","_")}_daily.json.gz','rt',encoding='utf-8') as h: raw=json.load(h)
    except (OSError,ValueError):
        return []
    rows=[]
    for x in raw if isinstance(raw,list) else []:
        vals=[f(x.get(k)) for k in ('o','h','l','c')]; d=str(x.get('t') or '')[:8]
        if len(d)==8 and all(v is not None for v in vals): rows.append({'t':d,'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(rows,key=lambda r:r['t'])


def m15_bars(sym):
    try:
        with gzip.open(M15/f'{sym.replace(".","_")}_m15.json.gz','rt',encoding='utf-8') as h: raw=json.load(h)
    except (OSError,ValueError):
        return []
    rows=[]
    for x in raw if isinstance(raw,list) else []:
        vals=[f(x.get(k)) for k in ('o','h','l','c')]; t=str(x.get('t') or '')
        if len(t)==14 and all(v is not None for v in vals): rows.append({'t':t,'d':t[:8],'o':vals[0],'h':vals[1],'l':vals[2],'c':vals[3]})
    return sorted(rows,key=lambda r:r['t'])


def swing_high(xs,i):
    return i>=3 and i+3<len(xs) and xs[i]['h']>max(x['h'] for x in xs[i-3:i]) and xs[i]['h']>=max(x['h'] for x in xs[i+1:i+4])


def swing_low(xs,i):
    return i>=3 and i+3<len(xs) and xs[i]['l']<min(x['l'] for x in xs[i-3:i]) and xs[i]['l']<=min(x['l'] for x in xs[i+1:i+4])


def build_industry_source():
    mapping={r['symbol']:r['industry'] for r in json.loads(INDMAP.read_text()) if r.get('symbol') and r.get('industry')}
    sums=defaultdict(lambda:defaultdict(lambda:[0.0,0.0,0.0,0.0,0]))
    own={}; loaded=0
    for path in DAILY.glob('*_daily.json.gz'):
        stem=path.name.replace('_daily.json.gz','').split('_',1)
        if len(stem)!=2: continue
        sym=f'{stem[0]}.{stem[1]}'
        ind=mapping.get(sym)
        if not ind: continue
        bars=daily_bars(sym)
        if len(bars)<80: continue
        loaded+=1; ratios={}
        for a,b in zip(bars,bars[1:]):
            vals=[b[k]/a['c'] for k in ('o','h','l','c')]
            if any(v<=0 or not math.isfinite(v) for v in vals): continue
            logs=[math.log(v) for v in vals]; ratios[b['t']]=logs; acc=sums[ind][b['t']]
            for j,v in enumerate(logs): acc[j]+=v
            acc[4]+=1
        own[sym]=ratios
    return mapping,sums,own,loaded


def ex_stock_industry(sym,ind,sums,own):
    level=100.; mine=own.get(sym,{}); rows=[]
    for d in sorted(sums.get(ind,{})):
        acc=sums[ind][d]; logs=list(acc[:4]); n=acc[4]
        if d in mine:
            n-=1
            for j in range(4): logs[j]-=mine[d][j]
        if n<MIN_PEERS: continue
        vals=[level*math.exp(v/n) for v in logs]; o,h,l,c=vals; h=max(h,o,c); l=min(l,o,c)
        rows.append({'t':d,'o':o,'h':h,'l':l,'c':c,'components':n}); level=c
    return rows


def industry_bos_by_date(xs):
    highs=[i for i in range(3,len(xs)-3) if swing_high(xs,i)]
    out={}
    for i,b in enumerate(xs):
        # A pivot is usable only after its three right-side bars have closed.
        known=[j for j in highs if j+3<i]
        if not known: continue
        anchor=known[-1]
        if b['c']>xs[anchor]['h']*1.001:
            out[b['t']]={'industry_bos_date':b['t'],'industry_bos_idx':i,'industry_anchor_idx':anchor,
                         'industry_anchor_date':xs[anchor]['t'],'industry_anchor_confirm_date':xs[anchor+3]['t'],
                         'industry_anchor_high':round(xs[anchor]['h'],8),'industry_bos_close':round(b['c'],8),
                         'industry_components':b['components']}
    return out


def stock_m15_event(session):
    if len(session)<8: return None,'M15_SHORT_SESSION'
    lows=[i for i in range(3,len(session)-3) if swing_low(session,i)]
    highs=[i for i in range(3,len(session)-3) if swing_high(session,i)]
    for raid,b in enumerate(session):
        known_lows=[i for i in lows if i+3<raid]
        if not known_lows: continue
        low=known_lows[-1]
        if b['l']>=session[low]['l']*.997 or b['c']<=session[low]['l']: continue
        reclaim=raid
        known_highs=[i for i in highs if i+3<raid]
        if len(known_highs)<2: continue
        anchor=next((j for j in reversed(known_highs[1:]) if session[j]['h']<session[known_highs[known_highs.index(j)-1]]['h']),None)
        if anchor is None: continue
        choch=next((j for j in range(reclaim+1,len(session)) if session[j]['c']>session[anchor]['h']*1.001),None)
        if choch is None: continue
        if any(x['c']<session[low]['l'] for x in session[choch:]): continue
        return {'m15_ssl_idx':low,'m15_ssl_time':session[low]['t'],'m15_ssl_confirm_time':session[low+3]['t'],
                'm15_ssl_low':round(session[low]['l'],8),'m15_raid_time':b['t'],'m15_raid_low':round(b['l'],8),
                'm15_reclaim_time':session[reclaim]['t'],'m15_lh_anchor_time':session[anchor]['t'],
                'm15_lh_confirm_time':session[anchor+3]['t'],'m15_lh_high':round(session[anchor]['h'],8),
                'm15_choch_time':session[choch]['t']},'PASS'
    return None,'NO_CONFIRMED_M15_SSL_SWEEP_CHOCH'


def main():
    # No audit/trade/replay artifact is opened; only raw source plus immutable industry map.
    mapping,sums,own,mapped=build_industry_source()
    OUT.mkdir(parents=True,exist_ok=False); rows=[]; reject=Counter(); scanned=0
    for path in DAILY.glob('*_daily.json.gz'):
        stem=path.name.replace('_daily.json.gz','').split('_',1)
        if len(stem)!=2: continue
        sym=f'{stem[0]}.{stem[1]}'; ind=mapping.get(sym)
        if not ind: continue
        ibos=industry_bos_by_date(ex_stock_industry(sym,ind,sums,own))
        if not ibos: continue
        m15=m15_bars(sym); byday=defaultdict(list)
        for b in m15: byday[b['d']].append(b)
        dates=[b['t'] for b in daily_bars(sym)]; next_date={a:b for a,b in zip(dates,dates[1:])}
        for d,ctx in ibos.items():
            if d[:4] not in YEARS: continue
            event,status=stock_m15_event(byday.get(d,[])); reject[status]+=1
            entry=next_date.get(d)
            if event is None: continue
            if not entry: reject['NO_NEXT_DAILY_SESSION']+=1; continue
            assert ctx['industry_anchor_confirm_date']<d
            assert event['m15_ssl_confirm_time']<event['m15_raid_time']<event['m15_choch_time'][:14]<entry+'000000'
            rows.append({'symbol':sym,'industry':ind,'event_date':d,'eligible_entry_date':entry,
                         'ontology':'INDUSTRY_BOS_TO_CONSTITUENT_M15_SSL_CHOCH','tradable':'false','buy_enabled':'false',
                         'no_outcome_fields':'true',**ctx,**event})
        scanned+=1
        if scanned%500==0: print(json.dumps({'symbols':scanned,'seeds':len(rows)},ensure_ascii=False),flush=True)
    rows.sort(key=lambda r:(r['eligible_entry_date'],r['symbol'],r['event_date']))
    unique={(r['symbol'],r['eligible_entry_date']) for r in rows}; yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    fields=sorted({k for r in rows for k in r}) if rows else ['symbol','ontology']
    seed_path=OUT/'v562_seeds.csv'
    with seed_path.open('w',newline='',encoding='utf-8') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    support=len(unique)>=1000 and all(yearly.get(y,0)>=300 for y in YEARS)
    report={'version':'V562_INDUSTRY_BOS_M15_SSL_CHOCH_SEED_NO_OUTCOME','generated_at':datetime.now().isoformat(timespec='seconds'),
      'research_only':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'source_contract':'Sina source-isolated daily and M15 raw cache plus immutable Baostock industry map; 2025-2026 exploratory range; no cross-source bar substitution.',
      'frozen_ontology':'ex-stock industry confirmed-swing BOS on D -> constituent confirmed M15 SSL sweep/reclaim/CHOCH on D -> D+1 daily-open eligible',
      'causality':'Industry swing has three completed right-side daily bars before D. Constituent SSL and LH anchors each have three completed right-side M15 bars before their respective raid; CHOCH completes before D+1. No replay/outcome file is read.',
      'source_mapped_symbols':mapped,'symbols_with_parent_bos_scanned':scanned,'raw_seed_count':len(rows),'unique_symbol_entry_count':len(unique),'yearly_seed_count':dict(sorted(yearly.items())),
      'support_gate':{'unique_n_min':1000,'each_available_year_n_min':300,'pass':support},
      'invariants':{'no_outcome_files_read':True,'all_nontradable':all(r['tradable']=='false' and r['buy_enabled']=='false' for r in rows),'all_entry_after_choch':all(r['m15_choch_time'][:8]<r['eligible_entry_date'] for r in rows),'duplicate_symbol_entry_count':len(rows)-len(unique)},
      'rejection_counts':dict(reject),'decision':'SEED_GATE_PASS__INDEPENDENT_ORACLE_REQUIRED_NEXT' if support else 'SEED_SUPPORT_INSUFFICIENT__NO_OUTCOMES_OPENED__NO_REPLAY',
      'artifacts':{'out_dir':str(OUT),'seeds':str(seed_path),'latest':str(LATEST)}}
    text=json.dumps(report,ensure_ascii=False,indent=2); (OUT/'v562_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
