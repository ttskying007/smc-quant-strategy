#!/usr/bin/env python3
"""Remove duplicate OPEN monitor positions for the same symbol/pick_date/zone."""
from __future__ import annotations
import json, pathlib, shutil, datetime

MON = pathlib.Path('/root/.hermes/smc_monitor')
STAMP = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

def dk(v):
    s=''.join(ch for ch in str(v or '') if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def load(name):
    p=MON/name
    return json.loads(p.read_text()) if p.exists() else []

def save(name, data):
    (MON/name).write_text(json.dumps(data, ensure_ascii=False, indent=2))

def backup(name):
    p=MON/name
    b=MON/f'{name}.{STAMP}.dedupe.bak'
    shutil.copy2(p,b)
    return str(b)

positions=load('positions.json')
ledger=load('trade_ledger.json')
backups={n:backup(n) for n in ['positions.json','trade_ledger.json']}
seen={}
remove_ids=set()
for p in positions:
    if p.get('status')!='OPEN':
        continue
    key=(p.get('symbol'), dk(p.get('pick_date')), p.get('zone_type'))
    if key not in seen:
        seen[key]=p
        continue
    # keep earliest real import; remove later duplicate/manual_daily
    keep=seen[key]
    if str(p.get('created_at','')) < str(keep.get('created_at','')):
        remove_ids.add(keep.get('id'))
        seen[key]=p
    else:
        remove_ids.add(p.get('id'))

positions2=[p for p in positions if p.get('id') not in remove_ids]
ledger2=[r for r in ledger if not (r.get('action')=='BUY' and r.get('position_id') in remove_ids)]
save('positions.json',positions2)
save('trade_ledger.json',ledger2)
print(json.dumps({'backups':backups,'removed_open_positions':len(remove_ids),'removed_buy_ledger':len(ledger)-len(ledger2),'removed_ids':sorted(remove_ids)},ensure_ascii=False,indent=2))
