import json
from collections import defaultdict, Counter

IN='/root/.hermes/smc_opt_v98_reachable_5r_probability_gate/v98_structural_trades.json'
OUT='/root/.hermes/smc_opt_v98_reachable_5r_probability_gate/v99_high_wr_gate_search.json'
rows=json.load(open(IN))
A=[r for r in rows if r.get('production_grade')=='A_PRODUCTION']
N=len(A)

def fnum(x,d=0.0):
    try:
        if x in (None,''): return d
        return float(x)
    except Exception:
        return d

def year(r): return str(r.get('entry_date') or '')[:4] or 'NA'
def won(r): return fnum(r.get('pnl_pct'))>0
wins=[won(r) for r in A]
sl=[r.get('exit_reason')=='SL_HIT' for r in A]
pnls=[fnum(r.get('pnl_pct')) for r in A]
years=[year(r) for r in A]
main_years=['2023','2024','2025','2026']

def calc(idx):
    idx=list(idx); n=len(idx)
    if not n: return None
    w=sum(wins[i] for i in idx); s=sum(sl[i] for i in idx); p=sum(pnls[i] for i in idx)
    yd={}
    for y in sorted(set(years[i] for i in idx)):
        ii=[i for i in idx if years[i]==y]
        if not ii: continue
        yd[y]={'n':len(ii),'wr':round(sum(wins[j] for j in ii)/len(ii)*100,2),'sl_rate':round(sum(sl[j] for j in ii)/len(ii)*100,2),'avg_pnl':round(sum(pnls[j] for j in ii)/len(ii),4)}
    wr=round(w/n*100,2)
    return {'n':n,'wr':wr,'sl_rate':round(s/n*100,2),'avg_pnl':round(p/n,4),'cum_pnl':round(p,4),'min_year_n':min(yd.get(y,{}).get('n',0) for y in main_years),'worst_year_wr':min(yd.get(y,{}).get('wr',0) for y in main_years if yd.get(y,{}).get('n',0)>0),'years':yd}

preds=[]
def add(name, fn):
    idx=frozenset(i for i,r in enumerate(A) if fn(r))
    if 100<=len(idx)<N:
        st=calc(idx)
        # keep predicates that improve or isolate meaningful population
        if st and (st['wr']>=60 or len(idx)>=1000): preds.append((name,idx,st))

cats=['market_state','pd_zone','event_type','poi_type','v91_gate_reason','v85_path','v85_market_substate','v90_recovery_substate','trend_regime','environment_permission','sl_mode','tp2_target_type','tp3_target_type','environment_allows_demand']
for c in cats:
    vals=Counter(str(r.get(c,'')) for r in A)
    for v,n in vals.items():
        if n>=100:
            add(f'{c}=={v}', lambda r,c=c,v=v: str(r.get(c,''))==v)
            add(f'{c}!={v}', lambda r,c=c,v=v: str(r.get(c,''))!=v)
thresholds={
 'risk_pct':[0.6,0.8,1.0,1.2,1.5,2.0,2.5,3.0],
 'volatility_pct':[0.8,1.0,1.2,1.5,2.0,2.5,3.0,4.0,5.0],
 'v85_zone_width_pct':[0.3,0.5,0.8,1.0,1.2,1.5,2.0,2.5,3.0],
 'tp2_rr':[5,5.5,6,6.5,7,8,9,10,12],
 'tp3_rr':[8,9,10,12,14,16,20],
}
for c,ths in thresholds.items():
    for t in ths:
        add(f'{c}<={t}', lambda r,c=c,t=t: fnum(r.get(c),999)<=t)
        add(f'{c}>={t}', lambda r,c=c,t=t: fnum(r.get(c),-999)>=t)

# rank atomic predicates
preds=sorted(preds,key=lambda x:(x[2]['wr'],x[2]['worst_year_wr'],x[2]['n']),reverse=True)[:160]
allres=[]
beam=[([name],idx,st) for name,idx,st in preds]
allres.extend({'rules':n,**st} for n,idx,st in beam)
for depth in range(2,6):
    new=[]; seen=set()
    for names,idx,st in beam[:100]:
        for name2,idx2,_ in preds:
            if name2 in names: continue
            key=tuple(sorted(names+[name2]))
            if key in seen: continue
            seen.add(key)
            inter=idx & idx2
            if len(inter)<100: continue
            st2=calc(inter)
            if st2['min_year_n']<10: continue
            if st2['wr']<68: continue
            new.append((list(key),inter,st2))
            allres.append({'rules':list(key),**st2})
    beam=sorted(new,key=lambda x:(x[2]['wr'],x[2]['worst_year_wr'],x[2]['n']),reverse=True)[:120]
    if not beam: break

# de-duplicate by rules
uniq={tuple(r['rules']):r for r in allres}.values()
robust=sorted([r for r in uniq if r['n']>=300 and r['min_year_n']>=20],key=lambda x:(x['wr'],x['worst_year_wr'],x['n']),reverse=True)[:80]
large=sorted([r for r in uniq if r['n']>=800 and r['min_year_n']>=50],key=lambda x:(x['wr'],x['worst_year_wr'],x['n']),reverse=True)[:80]
atomic=sorted([{'rule':n,**st} for n,idx,st in preds],key=lambda x:(x['wr'],x['worst_year_wr'],x['n']),reverse=True)[:80]
out={'base':calc(range(N)),'atomic_top':atomic,'robust_top':robust,'large_top':large}
json.dump(out,open(OUT,'w'),ensure_ascii=False,indent=2)
print('BASE',out['base']['n'],out['base']['wr'],out['base']['sl_rate'])
print('ROBUST TOP')
for r in robust[:25]: print(r['n'],r['wr'],r['sl_rate'],r['worst_year_wr'],r['rules'])
print('LARGE TOP')
for r in large[:25]: print(r['n'],r['wr'],r['sl_rate'],r['worst_year_wr'],r['rules'])
print('WROTE',OUT)
