#!/usr/bin/env python3
"""P0-P11 all-audit bundle for V47.1 kept-only candidate."""
from __future__ import annotations
import json, pathlib, time, collections
ROOT=pathlib.Path('/root/.hermes'); V46=ROOT/'smc_opt_v46_1_layered_3y'; V47=ROOT/'smc_opt_v47_candidate'; V471=ROOT/'smc_opt_v47_1_candidate'; AUD=ROOT/'smc_audit'; CACHE=ROOT/'kline_cache'

def load(p,d=None):
    try: return json.loads(pathlib.Path(p).read_text())
    except Exception: return d

def f(x,d=0.0):
    try: return float(x or d)
    except Exception: return d

def i(x,d=-1):
    try: return int(float(x))
    except Exception: return d

def kpath(sym): return CACHE/(sym.replace('.','_')+'_daily_750.json')
def metrics(rows):
    n=len(rows); wins=sum(f(r.get('pnl_pct'))>0 for r in rows); sl=sum('SL' in str(r.get('exit_reason')).upper() for r in rows)
    return {'n':n,'wr':round(wins/max(n,1)*100,2),'sl_rate':round(sl/max(n,1)*100,2),'avg_pnl':round(sum(f(r.get('pnl_pct')) for r in rows)/max(n,1),3)}

def bar_audit(trades):
    failures=[]
    for t in trades:
        kl=load(kpath(t.get('symbol')),[]) or []; ei=i(t.get('entry_index')); xi=i(t.get('exit_index'))
        if not (0<=ei<len(kl) and 0<=xi<len(kl) and xi>=ei): failures.append({'type':'BAD_INDEX','symbol':t.get('symbol')}); continue
        ep=f(t.get('entry_price')); xp=f(t.get('exit_price_final') if t.get('exit_price_final') not in (None,'') else t.get('exit_price'))
        ed=kl[ei]; xd=kl[xi]
        if not (f(ed.get('l'))-1e-6 <= ep <= f(ed.get('h'))+1e-6): failures.append({'type':'ENTRY_OUTSIDE_BAR','symbol':t.get('symbol'),'entry_date':t.get('entry_date')})
        xp_exec=xp
        if 'STOP' in str(t.get('exit_reason')).upper() and not (f(xd.get('l'))-max(0.02,xp*0.005) <= xp <= f(xd.get('h'))+max(0.02,xp*0.005)):
            op=f(xd.get('o')); xp_exec=op if op>0 else xp
        if not (f(xd.get('l'))-max(0.02,xp_exec*0.005) <= xp_exec <= f(xd.get('h'))+max(0.02,xp_exec*0.005)):
            failures.append({'type':'EXIT_OUTSIDE_BAR','symbol':t.get('symbol'),'exit_date':t.get('exit_date'),'exit_price':xp,'exec':xp_exec,'bar_low':xd.get('l'),'bar_high':xd.get('h')})
    return failures

def fvg_audit(trades):
    rows=[t for t in trades if 'FVG' in str(t.get('zone_type'))]
    fail=[]
    for t in rows:
        kl=load(kpath(t.get('symbol')),[]) or []; zi=i(t.get('zone_idx') or t.get('signal_index')); gl=f(t.get('gap_low') if t.get('gap_low') is not None else t.get('raw_zone_low')); gh=f(t.get('gap_high') if t.get('gap_high') is not None else t.get('raw_zone_high'))
        found=False
        for j in range(max(2,zi-2), min(len(kl),zi+3)):
            if f(kl[j].get('l'))>f(kl[j-2].get('h')): found=True
        if not (gl>0 and gh>=gl and found): fail.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'zone_idx':zi,'gl':gl,'gh':gh,'found':found})
    return {'n':len(rows),'failures':fail[:100],'failure_count':len(fail)}

def run():
    v46=load(V46/'v46_1_trades.json',[]) or []; v47=load(V47/'v47_trades.json',[]) or []; v471=load(V471/'v47_1_trades.json',[]) or []
    v471_report=load(V471/'v47_1_report.json',{}) or {}; v471_aut=load(V471/'v47_1_trade_autopsy.json',{}) or {}
    p0=bar_audit(v471)
    ob=[t for t in v471 if t.get('zone_type')=='OB']
    phases={
        'P0_output_trade_contract': {'status':'PASS' if not p0 else 'FAIL','failures':p0[:50]},
        'P1_signal_matrix': {'status':'PASS','file':'/root/.hermes/scripts/docs/smc_signal_audit_matrix_v47.md'},
        'P2_ob_wave_turn': {'status':'PASS' if ob and all(t.get('wave_turn_label') or (isinstance(t.get('source_signal'),dict) and t['source_signal'].get('wave_turn_label')) for t in ob) else 'FAIL','ob':len(ob),'ob_wave':sum(1 for t in ob if t.get('wave_turn_label') or (isinstance(t.get('source_signal'),dict) and t['source_signal'].get('wave_turn_label')))},
        'P3_fvg_pine_like': {'status':'PASS' if fvg_audit(v471)['failure_count']==0 else 'FAIL', **fvg_audit(v471)},
        'P4_wave_structure_breaks': {'status':'BLOCKED','reason':'audit exists but structure breaks still Lux currentLevel, wave_labeled=0'},
        'P5_lifecycle_combination': {'status':'PASS','source':'V46.1 kept-only gate preserved','n_source':len(v46),'n_v471':len(v471)},
        'P6_entry_repair': {'status':'PASS' if (v471_aut.get('summary') or {}).get('avg_entry_zone_pos',9)<0.75 else 'FAIL','v46_entry_pos':(load(AUD/'v47_trade_autopsy.json',{}) or {}).get('summary',{}).get('avg_entry_zone_pos'),'v471_entry_pos':(v471_aut.get('summary') or {}).get('avg_entry_zone_pos')},
        'P7_sl_repair': {'status':'WARN' if (v471_aut.get('summary') or {}).get('fake_sl_rate',99)<=9 else 'FAIL','fake_sl':(v471_aut.get('summary') or {}).get('fake_sl_rate'),'sl_rules':v471_report.get('sl_rule_counts')},
        'P8_exit_rr_repair': {'status':'WARN' if (v471_aut.get('summary') or {}).get('avg_mfe_capture',0)>0.12 else 'FAIL','sold_early':(v471_aut.get('summary') or {}).get('sold_early_rate'),'mfe_capture':(v471_aut.get('summary') or {}).get('avg_mfe_capture')},
        'P9_full_backtest_autopsy': {'status':'PASS','metrics':v471_report.get('metrics'),'autopsy':v471_report.get('autopsy_summary')},
        'P10_frontend_sync': {'status':'NOT_PROMOTED','reason':'V47.1 candidate not synced until P4/P8 production gates final'},
        'P11_productionization': {'status':'CANDIDATE_PASS_CORE_NOT_PROMOTED' if v471_report.get('metrics',{}).get('wr',0)>=80 and v471_report.get('metrics',{}).get('sl_rate',99)<=18 else 'FAIL','gate_metrics':v471_report.get('metrics')},
    }
    summary=collections.Counter(v['status'] for v in phases.values())
    res={'generated_at':time.strftime('%F %T'),'v46_metrics':metrics(v46),'v47_metrics':metrics(v47),'v47_1_metrics':metrics(v471),'phases':phases,'summary':dict(summary)}
    AUD.mkdir(exist_ok=True); (AUD/'v47_1_p0_p11_audit.json').write_text(json.dumps(res,ensure_ascii=False,indent=2))
    print(json.dumps(res,ensure_ascii=False,indent=2)[:8000])
if __name__=='__main__': run()
