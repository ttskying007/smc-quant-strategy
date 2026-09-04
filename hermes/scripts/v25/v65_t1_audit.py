#!/usr/bin/env python3
"""V65 T+1 hard audit: A-share trades must not exit on entry date."""
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path('/root/.hermes')
TRADE=ROOT/'smc_opt_v65/v65_trades.json'
OUT=ROOT/'smc_audit/v65_t1_audit.json'

def d(x):
    return ''.join(ch for ch in str(x or '') if ch.isdigit())[:8]

def main():
    rows=json.loads(TRADE.read_text()) if TRADE.exists() else []
    violations=[]
    for t in rows:
        ed=d(t.get('entry_date'))
        xd=d(t.get('exit_date') or t.get('entry_date'))
        if ed and xd and ed==xd:
            violations.append({
                'symbol':t.get('symbol'), 'entry_date':t.get('entry_date'), 'exit_date':t.get('exit_date'),
                'entry_index':t.get('entry_index'), 'exit_index':t.get('exit_index'), 'exit_reason':t.get('exit_reason'),
                'pnl_pct':t.get('pnl_pct'), 'family':t.get('v59_setup_family') or t.get('trade_role')
            })
    out={'trade_file':str(TRADE),'n_trades':len(rows),'violation_count':len(violations),'pass':len(violations)==0,'violations':violations[:200]}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2))
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
