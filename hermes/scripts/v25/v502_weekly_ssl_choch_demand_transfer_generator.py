#!/usr/bin/env python3
"""V502 outcome-blind weekly SSL -> bull CHOCH -> demand-OB -> daily transfer generator."""
from __future__ import annotations
import csv, json, math
from collections import Counter
from datetime import datetime
from pathlib import Path

ROOT=Path('/root/.hermes'); KDIR=ROOT/'kline_cache'; AUD=ROOT/'smc_audit'
OUT=AUD/f"v502_weekly_ssl_choch_demand_transfer_no_write_{datetime.now():%Y%m%d_%H%M%S}"
LATEST=AUD/'v502_weekly_ssl_choch_demand_transfer_latest.json'; YEARS=('2023','2024','2025','2026')


def f(x):
    try:
        v=float(x); return v if math.isfinite(v) else 0.0
    except (TypeError,ValueError): return 0.0


def ds(x): return ''.join(c for c in str(x or '') if c.isdigit())[:8]


def load(path):
    try: raw=json.loads(path.read_text())
    except (OSError,json.JSONDecodeError): return []
    out=[]
    for b in raw:
        r={k:f(b.get(k)) for k in ('o','h','l','c')}; d=ds(b.get('t') or b.get('date'))
        if d and min(r.values())>0: r['t']=d; out.append(r)
    return sorted(out,key=lambda x:x['t'])


def symbol(path):
    code,ex=path.name.removesuffix('_daily_750.json').split('_'); return f'{code}.{ex}'


def weeks(daily):
    groups=[]; key=None
    for b in daily:
        d=datetime.strptime(b['t'],'%Y%m%d').date(); k=d.isocalendar()[:2]
        if k!=key: groups.append([]); key=k
        groups[-1].append(b)
    return [{'start_date':g[0]['t'],'end_date':g[-1]['t'],'o':g[0]['o'],'h':max(x['h'] for x in g),'l':min(x['l'] for x in g),'c':g[-1]['c']} for g in groups[:-1] if g]


def pivots(ws,field,greater):
    out=[]
    for i in range(2,len(ws)-2):
        vals=[ws[j][field] for j in range(i-2,i+3) if j!=i]
        if (ws[i][field]>max(vals)) if greater else (ws[i][field]<min(vals)):
            out.append((i,i+2,ws[i][field]))
    return out


def lifecycle(daily,choch_date,zl,zh):
    start=next((i for i,b in enumerate(daily) if b['t']>choch_date),None)
    if start is None: return None,'NO_DAILY_AFTER_CHOCH'
    touch=reclaim=None
    for i in range(start,min(len(daily),start+41)):
        b=daily[i]
        if b['c']<zl: return None,'DEMAND_OB_INVALIDATED_BEFORE_HOLD'
        if touch is None:
            if b['l']<=zh and b['h']>=zl: touch=i
            continue
        if reclaim is None:
            if i>touch and b['c']>zh: reclaim=i
            continue
        if i>reclaim and b['c']>zh and b['l']>=zl:
            return (touch,reclaim,i,i+1 if i+1<len(daily) else None),'PASS'
    if touch is None: return None,'NO_TOUCH_40D'
    if reclaim is None: return None,'NO_RECLAIM_40D'
    return None,'NO_HOLD_40D'


def generate(sym,daily):
    ws=weeks(daily); lows=pivots(ws,'l',False); highs=pivots(ws,'h',True)
    rows=[]; rejects=Counter(); raw=0; used=set()
    for raid in range(4,len(ws)):
        ssl_candidates=[x for x in lows if x[1]<=raid and x[0]<raid and ws[raid]['l']<x[2]*.997 and ws[raid]['c']>x[2]]
        if not ssl_candidates: continue
        ssl_i,ssl_confirm,ssl_level=max(ssl_candidates,key=lambda x:x[0])
        bsl_candidates=[x for x in highs if x[1]<=raid and x[0]<raid]
        if not bsl_candidates: rejects['NO_PRE_RAID_CONFIRMED_SWING_HIGH']+=1; continue
        sh_i,sh_confirm,break_level=max(bsl_candidates,key=lambda x:x[0])
        choch=next((j for j in range(raid+1,min(len(ws),raid+13)) if ws[j]['c']>break_level*1.003),None)
        if choch is None: rejects['NO_BULL_CHOCH_12W']+=1; continue
        ob=next((j for j in range(choch-1,max(raid-1,choch-7),-1) if ws[j]['c']<ws[j]['o']),None)
        if ob is None: rejects['NO_POST_RAID_BEARISH_OB_SOURCE']+=1; continue
        identity=(raid,choch,ob)
        if identity in used: continue
        zl=ws[ob]['l']; zh=max(ws[ob]['o'],ws[ob]['c']); raw+=1; used.add(identity)
        life,reason=lifecycle(daily,ws[choch]['end_date'],zl,zh)
        if life is None: rejects[reason]+=1; continue
        touch,reclaim,hold,eligible=life
        if eligible is None: rejects['ENTRY_RIGHT_EDGE']+=1; continue
        order=(ssl_i<ssl_confirm<=raid<choch and sh_i<sh_confirm<=raid and raid<=ob<choch and ws[choch]['end_date']<daily[touch]['t']<daily[reclaim]['t']<daily[hold]['t']<daily[eligible]['t'] and eligible==hold+1)
        rows.append({'symbol':sym,'ontology':'WEEKLY_SSL_BULL_CHOCH_DEMAND_OB_DAILY_TRANSFER',
          'weekly_ssl_idx':ssl_i,'weekly_ssl_confirm_idx':ssl_confirm,'weekly_ssl_level':round(ssl_level,6),
          'weekly_raid_idx':raid,'weekly_raid_end_date':ws[raid]['end_date'],'weekly_raid_low':round(ws[raid]['l'],6),
          'weekly_swing_high_idx':sh_i,'weekly_swing_high_confirm_idx':sh_confirm,'weekly_choch_break_level':round(break_level,6),
          'weekly_choch_idx':choch,'weekly_choch_end_date':ws[choch]['end_date'],'weekly_demand_ob_idx':ob,'weekly_demand_ob_end_date':ws[ob]['end_date'],
          'zone_low':round(zl,6),'zone_high':round(zh,6),'touch_idx':touch,'touch_date':daily[touch]['t'],
          'reclaim_idx':reclaim,'reclaim_date':daily[reclaim]['t'],'hold_idx':hold,'hold_date':daily[hold]['t'],
          'eligible_entry_idx':eligible,'eligible_entry_date':daily[eligible]['t'],'semantic_order_valid':order,
          'tradable':False,'buy_enabled':False,'no_outcome_fields':True})
    return rows,rejects,raw


def main():
    OUT.mkdir(parents=True,exist_ok=True); all_rows=[]; rejects=Counter(); scanned=raw_n=0
    for n,path in enumerate(sorted(KDIR.glob('*_daily_750.json')),1):
        daily=load(path)
        if len(daily)<150: continue
        scanned+=1; rows,bad,raw=generate(symbol(path),daily); all_rows.extend(rows); rejects.update(bad); raw_n+=raw
        if n%500==0: print(json.dumps({'progress':n,'seeds':len(all_rows)}),flush=True)
    dedup={}
    for r in all_rows:
        key=(r['symbol'],r['eligible_entry_date']); old=dedup.get(key)
        if old is None or r['weekly_choch_idx']<old['weekly_choch_idx']: dedup[key]=r
    rows=list(dedup.values()); yearly=Counter(r['eligible_entry_date'][:4] for r in rows)
    support=len(rows)>=300 and all(yearly.get(y,0)>=40 for y in YEARS)
    seed=OUT/'v502_semantic_seeds.csv'; fields=list(rows[0]) if rows else ['symbol','ontology']
    with seed.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader(); w.writerows(rows)
    inv={'semantic_order_failures':sum(not r['semantic_order_valid'] for r in rows),'duplicate_symbol_entry':len(rows)-len(set((r['symbol'],r['eligible_entry_date']) for r in rows)),'no_outcome_fields':all(r['no_outcome_fields'] for r in rows),'all_nontradable':all(not r['tradable'] and not r['buy_enabled'] for r in rows)}
    ok=support and not inv['semantic_order_failures'] and not inv['duplicate_symbol_entry']
    result={'version':'V502_WEEKLY_SSL_CHOCH_DEMAND_TRANSFER_NO_WRITE','generated_at':datetime.now().isoformat(timespec='seconds'),'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
      'frozen_contract':'confirmed weekly SSL -> later weekly wick raid >=0.3% and close-back -> break most-recent pre-raid confirmed weekly swing high by close >=0.3% within 12 weeks (bull CHOCH) -> nearest post-raid bearish weekly candle within 6 weeks as demand OB -> first post-CHOCH daily touch -> later reclaim -> later hold -> next-open eligibility; close below OB low cancels',
      'distinct_information':'Higher-timeframe reversal-state transfer. Unlike weekly rejection-block it requires a subsequent weekly CHOCH; unlike generic weekly BOS-demand it requires a prior confirmed SSL raid and uses only the post-raid displacement leg as the OB source.',
      'planned_execution_if_oracle_passes':'next open; SL=weekly raid low*0.99; TP=nearest higher confirmed weekly swing high visible by hold; time30; fee0.2%; serial strict T+1; one replay',
      'promotion_gate':{'n':300,'each_year_n':40,'gross_wr_pct':55.0,'avg_net_pnl_pct':0.5,'each_year_gross_wr_pct':50.0,'each_year_avg_net_pnl_pct':0.0,'profit_factor':1.15,'payoff_rr':0.7,'t1_violations':0},
      'symbols_scanned':scanned,'raw_complete_setups':raw_n,'seed_count':len(rows),'yearly_seed_count':dict(sorted(yearly.items())),'rejection_counts':dict(rejects),'support_gate_pass':support,'invariants':inv,
      'decision':'WEEKLY_SSL_CHOCH_DEMAND_SEEDS_READY__INDEPENDENT_ORACLE_NEXT' if ok else 'WEEKLY_SSL_CHOCH_DEMAND_SUPPORT_OR_SEMANTIC_FAIL__NO_REPLAY','artifacts':{'out_dir':str(OUT),'seeds':str(seed),'latest':str(LATEST)}}
    text=json.dumps(result,ensure_ascii=False,indent=2); (OUT/'v502_report.json').write_text(text); LATEST.write_text(text); print(text)

if __name__=='__main__': main()
