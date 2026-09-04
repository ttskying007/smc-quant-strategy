#!/usr/bin/env python3
"""Audit whether BOS/CHOCH/MSS are tied to wave-turn structure layer."""
from __future__ import annotations
import json, pathlib, time, collections, urllib.request
ROOT=pathlib.Path('/root/.hermes'); AUD=ROOT/'smc_audit'; CACHE=ROOT/'kline_cache'

def load(p,d=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return d

def f(x,d=0.0):
    try: return float(x or d)
    except Exception: return d

def audit_frontend(symbol='600519.SH'):
    try: d=json.loads(urllib.request.urlopen(f'http://127.0.0.1:8890/api/kline_full?symbol={symbol}&tf=daily&ver=V46_1',timeout=20).read())
    except Exception as e: return {'error':repr(e)}
    sig=d.get('signals_list') or []
    rows=[s for s in sig if s.get('family') in ('bos','choch','mss')]
    wave=sum(1 for s in rows if s.get('wave_turn_label') or s.get('wave_ref_idx') or 'wave' in str(s.get('pivot_rule','')).lower())
    return {'symbol':symbol,'structure_breaks':len(rows),'wave_labeled':wave,'families':dict(collections.Counter(s.get('family') for s in rows)),'samples':rows[:20]}

def audit_trades(path):
    trades=load(path,[]) or []
    rows=[]
    for t in trades:
        st=t.get('struct_event') or {}
        rows.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'source_event':t.get('source_event'),'struct_type':st.get('type'),'swing_label':st.get('swing_label'),'pivot_rule':st.get('pivot_rule'),'wave_turn_label':t.get('wave_turn_label'),'struct_has_wave':bool(st.get('wave_turn_label') or st.get('wave_ref_idx') or 'wave' in str(st.get('pivot_rule','')).lower())})
    return {'n':len(rows),'struct_has_wave':sum(r['struct_has_wave'] for r in rows),'trade_has_ob_wave':sum(1 for r in rows if r.get('wave_turn_label')),'by_struct':dict(collections.Counter(r['struct_type'] for r in rows)),'samples_without_wave_struct':[r for r in rows if not r['struct_has_wave']][:50]}

def main():
    res={'generated_at':time.strftime('%F %T'),'frontend_600519':audit_frontend('600519.SH'),'v46_trades':audit_trades(ROOT/'smc_opt_v46_1_layered_3y/v46_1_trades.json')}
    vp=ROOT/'smc_opt_v47_candidate/v47_trades.json'
    if vp.exists(): res['v47_trades']=audit_trades(vp)
    AUD.mkdir(exist_ok=True); (AUD/'v47_wave_structure_audit.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
    print(json.dumps(res,ensure_ascii=False,indent=2)[:5000])
if __name__=='__main__': main()
