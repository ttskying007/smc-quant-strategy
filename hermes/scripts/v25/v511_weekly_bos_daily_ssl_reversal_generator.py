#!/usr/bin/env python3
"""V511 outcome-blind weekly-BOS context -> daily SSL/CHOCH/demand lifecycle."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v511_weekly_bos_daily_ssl_reversal_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v511_weekly_bos_daily_ssl_reversal_latest.json'; YEARS=('2023','2024','2025','2026')


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


def weekly_bos_contexts(ws):
    highs=pivots(ws,'h',2,2,True); lows=pivots(ws,'l',2,2,False)
    events=[]; broken=set()
    for i in range(5,len(ws)):
        visible=[x for x in highs if x[1]<i and x[0] not in broken and ws[i]['c']>x[2]*1.003]
        if not visible: continue
        high=max(visible,key=lambda x:x[0]); broken.add(high[0])
        protected=[x for x in lows if x[1]<i]
        if not protected: continue
        low=max(protected,key=lambda x:x[0])
        invalid=next((j for j in range(i+1,len(ws)) if ws[j]['c']<low[2]),None)
        events.append({'bos_idx':i,'bos_date':ws[i]['end'],'broken_high_idx':high[0],'broken_high_confirm_idx':high[1],
                       'broken_high':high[2],'protected_low_idx':low[0],'protected_low_confirm_idx':low[1],
                       'protected_low':low[2],'invalid_idx':invalid,'invalid_date':ws[invalid]['end'] if invalid is not None else ''})
    return events


def active_context(contexts,date):
    valid=[x for x in contexts if x['bos_date']<date and (not x['invalid_date'] or date<=x['invalid_date'])]
    return max(valid,key=lambda x:x['bos_idx']) if valid else None


def lifecycle(daily,choch,zl,zh):
    touch=reclaim=None
    for i in range(choch+1,min(len(daily),choch+21)):
        b=daily[i]
        if b['c']<zl: return None,'DAILY_DEMAND_INVALIDATED'
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
            continue
        if i>reclaim and b['c']>zh and b['l']>=zl:
            return (touch,reclaim,i,i+1 if i+1<len(daily) else None),'PASS'
    if touch is None: return None,'NO_TOUCH_20D'
    if reclaim is None: return None,'NO_RECLAIM_20D'
    return None,'NO_HOLD_20D'


def generate(sym,daily):
    ws=weeks(daily); contexts=weekly_bos_contexts(ws)
    lows=pivots(daily,'l',3,3,False); highs=pivots(daily,'h',3,3,True)
    rows=[]; rejects=Counter(); consumed=set(); raw=0
    for raid in range(7,len(daily)):
        context=active_context(contexts,daily[raid]['t'])
        if context is None: continue
        eligible=[x for x in lows if x[1]<=raid and x[0]<raid and x[0] not in consumed and daily[raid]['l']<x[2]*.997 and daily[raid]['c']>x[2]]
        if not eligible: continue
        ssl=max(eligible,key=lambda x:x[0]); consumed.add(ssl[0])
        visible_highs=[x for x in highs if x[1]<=raid and x[0]<raid]
        if not visible_highs: rejects['NO_PRE_RAID_DAILY_SWING_HIGH']+=1; continue
        sh=max(visible_highs,key=lambda x:x[0])
        choch=next((j for j in range(raid+1,min(len(daily),raid+11)) if daily[j]['c']>sh[2]*1.002),None)
        if choch is None: rejects['NO_DAILY_BULL_CHOCH_10D']+=1; continue
        ob=next((j for j in range(choch-1,max(raid-1,choch-7),-1) if daily[j]['c']<daily[j]['o']),None)
        if ob is None: rejects['NO_RAID_TO_CHOCH_BEARISH_OB']+=1; continue
        raw+=1; zl=daily[ob]['l']; zh=max(daily[ob]['o'],daily[ob]['c'])
        life,reason=lifecycle(daily,choch,zl,zh)
        if life is None: rejects[reason]+=1; continue
        touch,reclaim,hold,eligible_entry=life
        if eligible_entry is None: rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=(context['broken_high_idx']<context['broken_high_confirm_idx']<context['bos_idx'] and
               context['protected_low_idx']<context['protected_low_confirm_idx']<context['bos_idx'] and
               context['bos_date']<daily[raid]['t'] and (not context['invalid_date'] or daily[raid]['t']<=context['invalid_date']) and
               ssl[0]<ssl[1]<=raid<choch and sh[0]<sh[1]<=raid and raid<=ob<choch<touch<reclaim<hold<eligible_entry and eligible_entry==hold+1)
        rows.append({'symbol':sym,'ontology':'WEEKLY_BULL_BOS_CONTEXT__DAILY_SSL_CHOCH_DEMAND_OB_TRANSFER',
          'weekly_bos_idx':context['bos_idx'],'weekly_bos_end_date':context['bos_date'],'weekly_broken_high_idx':context['broken_high_idx'],
          'weekly_broken_high_confirm_idx':context['broken_high_confirm_idx'],'weekly_broken_high':round(context['broken_high'],6),
          'weekly_protected_low_idx':context['protected_low_idx'],'weekly_protected_low_confirm_idx':context['protected_low_confirm_idx'],
          'weekly_protected_low':round(context['protected_low'],6),'weekly_context_invalid_idx':context['invalid_idx'] if context['invalid_idx'] is not None else '',
          'weekly_context_invalid_date':context['invalid_date'],'daily_ssl_idx':ssl[0],'daily_ssl_confirm_idx':ssl[1],
          'daily_ssl_level':round(ssl[2],6),'daily_raid_idx':raid,'daily_raid_date':daily[raid]['t'],'daily_raid_low':round(daily[raid]['l'],6),
          'daily_swing_high_idx':sh[0],'daily_swing_high_confirm_idx':sh[1],'daily_choch_break_level':round(sh[2],6),
          'daily_choch_idx':choch,'daily_choch_date':daily[choch]['t'],'daily_demand_ob_idx':ob,'daily_demand_ob_date':daily[ob]['t'],
          'zone_low':round(zl,6),'zone_high':round(zh,6),'touch_idx':touch,'touch_date':daily[touch]['t'],
          'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],'hold_idx':hold,'hold_date':daily[hold]['t'],
          'eligible_entry_idx':eligible_entry,'eligible_entry_date':daily[eligible_entry]['t'],'semantic_order_valid':order,
          'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects,raw,len(contexts)


def main():
    OUT.mkdir(parents=True,exist_ok=True); all_rows=[]; rejects=Counter(); scanned=raw_n=context_n=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        daily=load(path)
        if len(daily)<150: continue
        scanned+=1; rows,bad,raw,ctx=generate(symbol(path),daily); all_rows.extend(rows); rejects.update(bad); raw_n+=raw; context_n+=ctx
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(all_rows)}),flush=True)
    dedup={}
    for r in all_rows:
        key=(r['symbol'],r['eligible_entry_date']); old=dedup.get(key)
        if old is None or r['daily_choch_idx']<old['daily_choch_idx']: dedup[key]=r
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v511_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    inv={'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)}
    ok=support and not inv['semantic_order_failures'] and not inv['duplicate_symbol_entry']
    result={'version':'V511_WEEKLY_BOS_DAILY_SSL_REVERSAL_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'active confirmed weekly bull BOS with protected weekly swing low -> daily confirmed SSL raid 0.3% and close-back -> break raid-time visible daily swing high by close 0.2% within 10 sessions -> backward nearest bearish candle within 6 bars as demand OB -> first touch -> later reclaim -> later hold -> next-open eligibility; weekly close below protected low or daily close below OB cancels',
      'distinct_information':'Cross-timeframe permission transfer: a still-valid weekly bullish structure permits a lower-timeframe daily liquidity reversal. It is neither weekly POI transfer nor an unconditioned daily R1 reversal.',
      'planned_execution_if_oracle_passes':'next open; SL=daily raid low*0.99; TP=nearest higher confirmed weekly swing high visible by hold; time30; fee0.2%; serial strict T+1; one replay',
      'promotion_gate':{'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':0.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':0.7,'t1_violations':0},
      'symbols_scanned':scanned,'weekly_bos_context_count':context_n,'raw_complete_setups':raw_n,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':inv,
      'decision':'WEEKLY_BOS_DAILY_SSL_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if ok else 'WEEKLY_BOS_DAILY_SSL_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v511_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
