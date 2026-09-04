#!/usr/bin/env python3
from __future__ import annotations
import csv, json
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime

ROOT=Path('/root/.hermes')
SRC=ROOT/'smc_audit/v128_parallel_scanner_candidate_audit_20260620/v128_parallel_shadow_backtest_all.csv'
KLINE=ROOT/'kline_cache'
OUT=ROOT/'smc_audit/v129_v128_exit_target_diagnostic_20260622'
OUT.mkdir(parents=True, exist_ok=True)

def num(x, default=0.0):
    try:
        if x in (None,''):
            return default
        return float(x)
    except Exception:
        return default

def date_key(x):
    s=str(x or '').replace('-','')[:8]
    return s

def bar_date(b): return date_key(b.get('t') or b.get('date'))
def v(b,k): return num(b.get(k))

def load_ks(sym):
    p=KLINE/f"{sym.replace('.','_')}_daily_750.json"
    return json.loads(p.read_text()) if p.exists() else []

def known_bsl(ks, entry_idx, entry_price, lookback=60):
    start=max(0,entry_idx-lookback)
    highs=[]
    for i in range(start, entry_idx):
        h=v(ks[i],'h')
        if h <= entry_price: continue
        left=ks[max(0,i-2):i]; right=ks[i+1:min(entry_idx,i+3)]
        swing=bool(left and right and h>=max(v(x,'h') for x in left) and h>=max(v(x,'h') for x in right))
        highs.append((i,h,bar_date(ks[i]), 'PRIOR_SWING_HIGH_BSL' if swing else 'PRIOR_HIGH_BSL'))
    if not highs:
        return (0.0,-1,'','NO_PRIOR_BSL_ABOVE_ENTRY')
    return min(highs, key=lambda x:(x[1]-entry_price, entry_idx-x[0]))

def simulate_target(row, ks):
    r=dict(row)
    ei=int(num(r.get('entry_idx'),-1)); entry=num(r.get('entry_price')); zl=num(r.get('zone_low'))
    if ei<0 or ei>=len(ks) or entry<=0 or zl<=0:
        r.update(valid_v129=False, invalid_v129='BAD_ENTRY')
        return r
    bidx,bsl,bdate,btyp=known_bsl(ks,ei,entry)
    risk_abs=max(entry-zl, entry*0.01, 1e-9)
    fixed_15r=entry+risk_abs*1.5
    if bsl and bsl>entry:
        target=bsl; target_type=btyp; target_rr=(target-entry)/risk_abs
    else:
        target=fixed_15r; target_type='FIXED_1_5R_NO_PRIOR_BSL'; target_rr=1.5
    exit_idx=None; exit_date=''; exit_price=0.0; reason=''
    # T+1: start from next bar after entry; horizon 20 trading bars after entry
    for i in range(ei+1, min(len(ks), ei+21)):
        b=ks[i]
        # same ordering as existing semantic: TP before close damage, but no same-day exit because i>=ei+1
        if v(b,'h') >= target:
            exit_idx=i; exit_date=bar_date(b); exit_price=target; reason='TAKE_PROFIT_KNOWN_BSL_OR_1_5R'; break
        if v(b,'c') < zl:
            exit_idx=i; exit_date=bar_date(b); exit_price=v(b,'c'); reason='EXIT_POI_CLOSE_BREAK'; break
    if exit_idx is None:
        exit_idx=min(len(ks)-1, ei+20)
        b=ks[exit_idx]
        exit_date=bar_date(b); exit_price=v(b,'c'); reason='TIME_STOP_NO_TARGET_OR_BREAK'
    r.update({
        'v129_target':round(target,6),'v129_target_type':target_type,'v129_target_rr':round(target_rr,4),
        'v129_known_bsl_target':round(bsl,6) if bsl else '', 'v129_known_bsl_date':bdate, 'v129_known_bsl_idx':bidx,
        'v129_exit_idx':exit_idx,'v129_exit_date':exit_date,'v129_exit_price':round(exit_price,6),'v129_exit_reason':reason,
        'v129_pnl_pct':round((exit_price/entry-1)*100,4),'v129_hold_bars':exit_idx-ei,
        'valid_v129':True,'invalid_v129':''
    })
    return r

def metrics(rows, pnl='v129_pnl_pct', reason='v129_exit_reason'):
    rows=list(rows); n=len(rows)
    if not n: return {'n':0,'wr':0,'avg':0,'loss':0,'hard':0,'cum':0}
    vals=[num(r.get(pnl)) for r in rows]
    hard=[r for r in rows if ('BREAK' in str(r.get(reason)) or 'DAMAGE' in str(r.get(reason)) or str(r.get(reason)).startswith('SL') or '_SL' in str(r.get(reason)))]
    return {'n':n,'wr':round(sum(x>0 for x in vals)/n*100,2),'avg':round(sum(vals)/n,4),'loss':round(sum(x<=0 for x in vals)/n*100,2),'hard':round(len(hard)/n*100,2),'cum':round(sum(vals),4)}

def bucket(rows, key):
    g=defaultdict(list)
    for r in rows: g[str(key(r))].append(r)
    return {k:metrics(v) for k,v in sorted(g.items())}

rows=[]
with SRC.open(newline='', encoding='utf-8') as f:
    for r in csv.DictReader(f): rows.append(r)
ks_cache={}
out=[]
for r in rows:
    sym=r.get('symbol')
    if sym not in ks_cache: ks_cache[sym]=load_ks(sym)
    out.append(simulate_target(r, ks_cache[sym]))
valid=[r for r in out if r.get('valid_v129')]
recent=[r for r in valid if 0<=num(r.get('bars_since_entry'),9999)<=45]
v125=[r for r in valid if str(r.get('v125_contract_shadow_pass')).lower()=='true']
summary={
 'decision':'V129_DIAGNOSTIC_ONLY_REEVALUATE_V128_WITH_PRE_ENTRY_BSL_OR_1_5R_TARGET_NO_PRODUCTION_WRITE',
 'run_at':datetime.now().isoformat(timespec='seconds'),
 'rows':len(out),'valid':len(valid),'recent45':len(recent),
 'overall_v128_original':metrics(valid,'pnl_pct','exit_reason'),
 'overall_v129_target_exit':metrics(valid),
 'recent45_v129':metrics(recent),
 'v125_contract_v129':metrics(v125),
 'by_source_v129':bucket(valid, lambda r:r.get('poi_source')),
 'by_family_v129':bucket(valid, lambda r:r.get('combo_family')),
 'by_market_state_v129':bucket(valid, lambda r:r.get('market_state')),
 'by_exit_reason_v129':bucket(valid, lambda r:r.get('v129_exit_reason')),
 'by_year_v129':bucket(valid, lambda r:date_key(r.get('entry_date'))[:4]),
 'target_type_counts':dict(Counter(str(r.get('v129_target_type')) for r in valid)),
 't1_violations':sum(1 for r in valid if date_key(r.get('entry_date'))==date_key(r.get('v129_exit_date'))),
}
# top losses and v125 rows
fields=sorted({k for r in out for k in r.keys()})
for name, data in [('v129_v128_target_exit_all.csv', valid), ('v129_recent45.csv', recent), ('v129_top_losses.csv', sorted([r for r in valid if num(r.get('v129_pnl_pct'))<=0], key=lambda r:num(r.get('v129_pnl_pct')))[:300]), ('v129_v125_contract.csv', v125)]:
    with (OUT/name).open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(data)
(OUT/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
lines=['# V129 V128 exit target diagnostic','',f"Decision: `{summary['decision']}`。只重评估V128 shadow，不写生产。",'', '## 核心对比', '|口径|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for name,m in [('V128_original_no_target',summary['overall_v128_original']),('V129_pre_entry_BSL_or_1.5R',summary['overall_v129_target_exit']),('V129_recent45',summary['recent45_v129']),('V129_V125_contract',summary['v125_contract_v129'])]:
    lines.append(f"|{name}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines += ['', '## 按source(V129)', '|source|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for k,m in summary['by_source_v129'].items(): lines.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines += ['', '## 按market_state(V129)', '|state|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for k,m in summary['by_market_state_v129'].items(): lines.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines += ['', '## 退出原因(V129)', '|reason|n|WR|Avg|Loss|HardExit|Cum|','|---|---:|---:|---:|---:|---:|---:|']
for k,m in summary['by_exit_reason_v129'].items(): lines.append(f"|{k}|{m['n']}|{m['wr']}|{m['avg']}|{m['loss']}|{m['hard']}|{m['cum']}|")
lines += ['', '## 文件', f'- {OUT}/summary.json', f'- {OUT}/v129_v128_target_exit_all.csv', f'- {OUT}/v129_recent45.csv', f'- {OUT}/v129_top_losses.csv', f'- {OUT}/v129_v125_contract.csv']
(OUT/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
print(json.dumps({'out':str(OUT),'summary':summary}, ensure_ascii=False, indent=2))
