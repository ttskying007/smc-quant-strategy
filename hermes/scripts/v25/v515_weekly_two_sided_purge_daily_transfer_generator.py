#!/usr/bin/env python3
"""V515 outcome-blind weekly two-sided liquidity purge -> daily CHOCH/OB lifecycle."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v515_weekly_two_sided_purge_daily_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v515_weekly_two_sided_purge_daily_transfer_latest.json'; YEARS=('2023','2024','2025','2026')


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    rows=[]
    for b in raw:
        q={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and min(q.values())>0: q['t']=d; rows.append(q)
    return sorted(rows,key=lambda x:x['t'])


def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'


def weeks(daily):
    groups=[]; key=None
    for b in daily:
        k=datetime.strptime(b['t'],'%Y%m%d').date().isocalendar()[:2]
        if k!=key: groups.append([]); key=k
        groups[-1].append(b)
    return [{'start':g[0]['t'],'end':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1] if g]


def pivots(rows,field,left,right,greater):
    out=[]
    for i in range(left,len(rows)-right):
        peers=[rows[j][field] for j in range(i-left,i+right+1) if j!=i]
        if (rows[i][field]>max(peers)) if greater else (rows[i][field]<min(peers)):
            out.append((i,i+right,rows[i][field]))
    return out


def purge_events(ws):
    highs=pivots(ws,'h',2,2,True); lows=pivots(ws,'l',2,2,False); events=[]
    for bsl in range(5,len(ws)):
        ph=[p for p in highs if p[1]<bsl and p[0]<bsl and ws[bsl]['h']>p[2]*1.003 and ws[bsl]['c']<p[2]]
        pl=[p for p in lows if p[1]<bsl and p[0]<bsl]
        if not ph or not pl: continue
        hi=max(ph,key=lambda p:p[0]); lo=max(pl,key=lambda p:p[0])
        if lo[0]>=hi[0] or lo[2]>=hi[2]: continue
        for ssl in range(bsl+2,min(len(ws),bsl+13)):
            if any(ws[j]['c']>hi[2] or ws[j]['c']<lo[2] for j in range(bsl+1,ssl)): break
            if ws[ssl]['l']<lo[2]*.997 and ws[ssl]['c']>lo[2]:
                events.append({'range_high_idx':hi[0],'range_high_confirm_idx':hi[1],'range_high':hi[2],
                  'range_low_idx':lo[0],'range_low_confirm_idx':lo[1],'range_low':lo[2],
                  'weekly_bsl_raid_idx':bsl,'weekly_bsl_raid_date':ws[bsl]['end'],'weekly_bsl_raid_high':ws[bsl]['h'],
                  'weekly_ssl_raid_idx':ssl,'weekly_ssl_raid_date':ws[ssl]['end'],'weekly_ssl_raid_low':ws[ssl]['l']})
                break
    return events


def lifecycle(daily,choch,zl,zh):
    touch=reclaim=None
    for i in range(choch+1,min(len(daily),choch+21)):
        b=daily[i]
        if b['c']<zl: return None,'DAILY_DEMAND_INVALIDATED'
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
            continue
        if reclaim is None:
            if b['c']>zh: reclaim=i
            continue
        if b['c']>zh and b['l']>=zl:
            return (touch,reclaim,i,i+1 if i+1<len(daily) else None),'PASS'
    if touch is None: return None,'NO_TOUCH_20D'
    if reclaim is None: return None,'NO_RECLAIM_20D'
    return None,'NO_HOLD_20D'


def generate(sym,daily):
    ws=weeks(daily); events=purge_events(ws); highs=pivots(daily,'h',3,3,True)
    rows=[]; rejects=Counter(); raw=0
    for event in events:
        raid_date=event['weekly_ssl_raid_date']
        start=next((i for i,b in enumerate(daily) if b['t']>raid_date),None)
        if start is None: rejects['NO_POST_WEEK_DAILY_BAR']+=1; continue
        visible=[p for p in highs if p[1]<start and daily[p[1]]['t']<=raid_date]
        if not visible: rejects['NO_VISIBLE_DAILY_SWING_HIGH']+=1; continue
        sh=max(visible,key=lambda p:p[0])
        choch=next((i for i in range(start,min(len(daily),start+11)) if daily[i]['c']>sh[2]*1.002),None)
        if choch is None: rejects['NO_DAILY_CHOCH_10D']+=1; continue
        ob=next((i for i in range(choch-1,max(start-1,choch-7),-1) if daily[i]['c']<daily[i]['o']),None)
        if ob is None: rejects['NO_POST_PURGE_BEARISH_OB']+=1; continue
        raw+=1; zl=daily[ob]['l']; zh=max(daily[ob]['o'],daily[ob]['c'])
        life,reason=lifecycle(daily,choch,zl,zh)
        if life is None: rejects[reason]+=1; continue
        touch,reclaim,hold,entry=life
        if entry is None: rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=(event['range_high_idx']<event['range_high_confirm_idx']<event['weekly_bsl_raid_idx']<event['weekly_ssl_raid_idx'] and
          event['range_low_idx']<event['range_low_confirm_idx']<event['weekly_bsl_raid_idx'] and
          event['weekly_ssl_raid_date']<daily[start]['t'] and sh[0]<sh[1]<start<=ob<choch<touch<reclaim<hold<entry and entry==hold+1)
        rows.append({'symbol':sym,'ontology':'WEEKLY_BSL_THEN_SSL_PURGE__DAILY_CHOCH_DEMAND_TRANSFER',**event,
          'post_purge_start_idx':start,'daily_swing_high_idx':sh[0],'daily_swing_high_confirm_idx':sh[1],
          'daily_choch_break_level':round(sh[2],6),'daily_choch_idx':choch,'daily_choch_date':daily[choch]['t'],
          'daily_demand_ob_idx':ob,'daily_demand_ob_date':daily[ob]['t'],'zone_low':round(zl,6),'zone_high':round(zh,6),
          'touch_idx':touch,'touch_date':daily[touch]['t'],'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],
          'hold_idx':hold,'hold_date':daily[hold]['t'],'eligible_entry_idx':entry,'eligible_entry_date':daily[entry]['t'],
          'semantic_order_valid':order,'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects,raw,len(events)


def main():
    OUT.mkdir(parents=True,exist_ok=True); all_rows=[]; rejects=Counter(); scanned=raw_n=event_n=0
    paths=sorted(KDIR.glob('*_daily_750.json'))
    for n,path in enumerate(paths,1):
        daily=load(path)
        if len(daily)<150: continue
        scanned+=1; rows,bad,raw,events=generate(symbol(path),daily); all_rows.extend(rows); rejects.update(bad); raw_n+=raw; event_n+=events
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(all_rows)}),flush=True)
    dedup={}
    for r in all_rows:
        key=(r['symbol'],r['eligible_entry_date']); old=dedup.get(key)
        if old is None or r['daily_choch_idx']<old['daily_choch_idx']: dedup[key]=r
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v515_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h: w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    inv={'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)}
    ok=support and not inv['semantic_order_failures'] and not inv['duplicate_symbol_entry']
    result={'version':'V515_WEEKLY_TWO_SIDED_PURGE_DAILY_TRANSFER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'confirmed weekly range high/low -> weekly BSL wick raid 0.3% close-back -> 2..12 completed weeks later weekly SSL wick raid 0.3% close-back with no intervening close outside range -> after SSL week daily close breaks raid-time visible daily swing high 0.2% within 10 sessions -> nearest bearish daily candle in post-purge displacement leg -> first post-CHOCH touch -> reclaim -> hold -> next-open eligibility',
      'distinct_information':'Higher-timeframe directional liquidity path, not a filter: the weekly chart must consume both sides in BSL-then-SSL order before a new daily CHOCH/POI lifecycle can exist. This differs from daily two-sided purge, weekly SSL-only reversal, weekly BOS permission, and weekly POI transfer.',
      'planned_execution_if_oracle_passes':'next open; SL=weekly SSL raid low*0.99; TP=weekly BSL raid high; time30; fee0.2%; serial strict T+1; one replay',
      'promotion_gate':{'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':0.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':0.7,'t1_violations':0},
      'symbols_scanned':scanned,'weekly_purge_event_count':event_n,'raw_complete_setups':raw_n,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':inv,
      'decision':'WEEKLY_TWO_SIDED_PURGE_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if ok else 'WEEKLY_TWO_SIDED_PURGE_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v515_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
