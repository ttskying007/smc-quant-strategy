#!/usr/bin/env python3
"""V327 no-write: executable replay of V326 current lineage rows.

V326 found one non-history <=10-bar row (688689.SH) on both V161/V175 lines.
This script applies the executable V175/V185-style T+1 contract before any
endpoint routing claim:
- SL = zone_low * 0.99;
- TP = entry + 1.5R;
- max_hold = 10 bars;
- T+1 exit only; same-bar SL first if both touch.

No production/frontend/watchlist writes.
"""
from __future__ import annotations

import json, math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path('/root/.hermes')
AUD = ROOT / 'smc_audit'
KDIR = ROOT / 'kline_cache'
V326 = AUD / 'v326_v246_lineage_current_supply_latest.json'
OUT = AUD / f"v327_v326_current_candidate_executable_replay_no_write_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
LATEST = AUD / 'v327_v326_current_candidate_executable_replay_latest.json'
MAX_HOLD = 10


def dn(x: Any) -> str:
    s=''.join(ch for ch in str(x or '').replace('-', '')[:10] if ch.isdigit())
    return s[:8] if len(s)>=8 else ''

def sf(x: Any, default: float|None=None) -> float|None:
    try:
        if x is None or x=='': return default
        v=float(x)
        if math.isnan(v) or math.isinf(v): return default
        return v
    except Exception:
        return default

def load_json(p: Path, default: Any) -> Any:
    try: return json.loads(p.read_text())
    except Exception: return default

def bars(symbol: str) -> list[dict[str, Any]]:
    p=KDIR / f"{symbol.replace('.', '_')}_daily_750.json"
    out=[]
    for b in load_json(p, []):
        d=dn(b.get('t') or b.get('date'))
        o,h,l,c=sf(b.get('o')),sf(b.get('h')),sf(b.get('l')),sf(b.get('c'))
        if d and None not in (o,h,l,c):
            out.append({'date':d,'o':o,'h':h,'l':l,'c':c})
    return sorted(out, key=lambda x:x['date'])

def replay(r: dict[str, Any]) -> dict[str, Any]:
    sym=str(r.get('symbol') or '')
    ed=dn(r.get('entry_date'))
    ep=sf(r.get('entry_price'))
    zl=sf(r.get('zone_low') or r.get('dz_low'))
    if not sym or not ed or ep is None or zl is None:
        return {'status':'REPLAY_FIELD_MISSING'}
    sl=zl*0.99
    tp=ep+(ep-sl)*1.5
    path=[b for b in bars(sym) if b['date']>ed]
    out={'status':'OPEN_UNEXPIRED','sl':round(sl,4),'tp':round(tp,4),'t1_path_bars':len(path),'latest_date':path[-1]['date'] if path else '', 'latest_close':round(path[-1]['c'],4) if path else None}
    for i,b in enumerate(path, start=1):
        reason=''; px=None
        if b['l']<=sl:
            reason='SL'; px=sl
        elif b['h']>=tp:
            reason='TP'; px=tp
        elif i>=MAX_HOLD:
            reason='TIME'; px=b['c']
        if reason:
            out.update({'status':'CLOSED_BY_EXECUTABLE_REPLAY','exit_reason':reason,'exit_date':b['date'],'exit_price':round(px,4),'hold_bars':i,'pnl_pct':round((px/ep-1)*100,4),'same_day_exit_violation':b['date']==ed})
            break
    if out['status']=='OPEN_UNEXPIRED' and len(path)>=MAX_HOLD:
        # Defensive; loop should close at max_hold.
        b=path[MAX_HOLD-1]
        out.update({'status':'CLOSED_BY_EXECUTABLE_REPLAY','exit_reason':'TIME','exit_date':b['date'],'exit_price':round(b['c'],4),'hold_bars':MAX_HOLD,'pnl_pct':round((b['c']/ep-1)*100,4),'same_day_exit_violation':False})
    return out

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rep=load_json(V326,{})
    candidates=[]
    seen=set()
    for route,path in (rep.get('artifacts') or {}).items():
        if not route.startswith('line_') or not str(path).endswith('.csv'):
            continue
        df=pd.read_csv(path, low_memory=False)
        if df.empty: continue
        mask=(df.get('v326_actionable10', False)==True) & (df.get('v326_any_history_overlap', True)==False)
        for r in df[mask].to_dict('records'):
            k=(str(r.get('symbol')), dn(r.get('entry_date')))
            if k in seen:
                # Preserve route overlap in a field rather than duplicating rows.
                for c in candidates:
                    if (c['symbol'], c['entry_date'])==k:
                        c['routes'].append(route)
                continue
            seen.add(k)
            candidates.append({**r, 'symbol':k[0], 'entry_date':k[1], 'routes':[route]})
    rows=[]
    for r in candidates:
        rr=dict(r)
        rr.update(replay(rr))
        rows.append(rr)
    open_rows=[r for r in rows if r.get('status')=='OPEN_UNEXPIRED']
    closed_rows=[r for r in rows if r.get('status')=='CLOSED_BY_EXECUTABLE_REPLAY']
    pd.DataFrame(rows).to_csv(OUT/'v327_replayed_current_candidates.csv', index=False)
    report={
        'version':'V327_V326_CURRENT_CANDIDATE_EXECUTABLE_REPLAY_NO_WRITE',
        'generated_at':datetime.now().isoformat(timespec='seconds'),
        'no_write':True,'production_write':False,'frontend_write':False,'watchlist_write':False,
        'source':str(V326),
        'candidate_rows':len(rows),
        'open_unexpired_rows':len(open_rows),
        'closed_by_replay_rows':len(closed_rows),
        'closed_rows_slim':[{k:r.get(k) for k in ['symbol','entry_date','routes','entry_price','sl','tp','exit_reason','exit_date','exit_price','hold_bars','pnl_pct','same_day_exit_violation']} for r in closed_rows],
        'open_rows_slim':[{k:r.get(k) for k in ['symbol','entry_date','routes','entry_price','sl','tp','t1_path_bars','latest_date','latest_close']} for r in open_rows],
        'decision':'V327_NO_OPEN_EXECUTABLE_CURRENT_V246_ROWS__NO_ENDPOINT_ROUTE__NO_WRITE' if not open_rows else 'V327_OPEN_CURRENT_ROWS_REQUIRE_ENDPOINT_MAPPING_SMOKE__NO_WRITE',
        'artifacts':{'out_dir':str(OUT),'rows_csv':str(OUT/'v327_replayed_current_candidates.csv'),'latest':str(LATEST)},
    }
    (OUT/'v327_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__=='__main__': main()
