#!/usr/bin/env python3
"""Export bounded, outcome-free bar windows for V603 manual chain verification."""
from __future__ import annotations
import csv, gzip, json
from pathlib import Path

ROOT=Path('/root/.hermes')
AUDIT=ROOT/'smc_audit'
RAW=ROOT/'intraday_cache/raw_multitf_v536/source_raw/sina/m15'
REPORT=json.loads((AUDIT/'v603_reversal_ssl_choch_displacement_state_machine_latest.json').read_text())
OUT=Path(REPORT['artifacts']['dir'])/'v603_manual_chain_windows.json'

def bars(symbol):
    p=RAW/f"{symbol.replace('.', '_')}_m15.json.gz"
    with gzip.open(p,'rt',encoding='utf-8') as f: raw=json.load(f)
    return sorted([{'t':str(x['t']),'o':float(x['o']),'h':float(x['h']),'l':float(x['l']),'c':float(x['c'])} for x in raw],key=lambda x:x['t'])

def read(path):
    return list(csv.DictReader(open(path,encoding='utf-8')))

valid=read(Path(REPORT['artifacts']['valid']))
cancelled=read(Path(REPORT['artifacts']['cancelled']))
groups={
 'VALID_CHAIN':valid[:5],
 'CANCEL_FIRST_TOUCH_FAILED':[x for x in cancelled if x['cancel_reason']=='CANCEL_FIRST_TOUCH_FAILED_RECLAIM'][:5],
 'CANCEL_ZONE_INVALIDATED':[x for x in cancelled if x['cancel_reason'] in {'CANCEL_ZONE_INVALIDATED_FIRST_TOUCH','CANCEL_ZONE_INVALIDATED_DURING_HOLD'}][:5],
}
out={}
for name, chains in groups.items():
    rendered=[]
    for chain in chains:
        rs=bars(chain['symbol']); ix={x['t']:i for i,x in enumerate(rs)}
        # Valid chains stop at HOLD: entry is only a next-bar execution identity,
        # so its completed OHLC is not inspected or exported.
        terminal=chain['hold_time'] if name=='VALID_CHAIN' else chain['invalidated_time']
        start=max(0,ix[chain['ssl_pivot_time']]-12); end=ix[terminal]+1
        rendered.append({'chain':chain,'window_start':rs[start]['t'],'window_end':rs[end-1]['t'],'bars_through_decision_only':rs[start:end]})
    out[name]=rendered
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2))
assert all(len(x)==5 for x in out.values())
print(json.dumps({'path':str(OUT),'groups':{k:len(v) for k,v in out.items()},'no_completed_entry_bar_exported_for_valid':True},ensure_ascii=False))
