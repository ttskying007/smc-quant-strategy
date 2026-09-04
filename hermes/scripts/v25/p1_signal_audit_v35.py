#!/usr/bin/env python3
import json, glob, time
from pathlib import Path
import smc_core_pine_like as pine
import smc_core_luxalgo_v34 as lux
CACHE=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v35'); OUT.mkdir(exist_ok=True)

def sym(fp): return Path(fp).stem.split('_daily_')[0].replace('_','.')
def main():
    agg={k:0 for k in ['stocks','lux_bos','lux_choch','lux_mss','lux_ob','lux_sweep','pine_fvg','pine_bpr','pine_eql_eqh','pine_lv','pine_ote','pine_sweep','pine_ob','pine_structure']}
    examples=[]; t=time.time()
    for i,fp in enumerate(sorted(CACHE.glob('*_daily_750.json')),1):
        ks=json.loads(fp.read_bytes())
        if len(ks)<120: continue
        r_l=lux.detect_all_signals_lux_v34(ks); sl=r_l['signals']
        r_p=pine.detect_all_signals_pine_like(ks); sp=r_p['signals']
        agg['stocks']+=1
        agg['lux_bos']+=sum(1 for e in sl.get('structure',[]) if e.get('type')=='BOS')
        agg['lux_choch']+=sum(1 for e in sl.get('structure',[]) if e.get('type')=='CHOCH')
        agg['lux_mss']+=sum(1 for e in sl.get('structure',[]) if e.get('is_mss'))
        agg['lux_ob']+=len(sl.get('obs',[])); agg['lux_sweep']+=len(sl.get('sweeps',[]))
        agg['pine_fvg']+=len(sp.get('fvgs',[])); agg['pine_bpr']+=len(sp.get('bprs',[])); agg['pine_eql_eqh']+=len(sp.get('eqh_eql',[]))
        agg['pine_lv']+=len(sp.get('liquidity_voids',[])); agg['pine_ote']+=len(sp.get('otes',[])); agg['pine_sweep']+=len(sp.get('sweeps',[])); agg['pine_ob']+=len(sp.get('obs',[])); agg['pine_structure']+=len(sp.get('structure',[]))
        if len(examples)<5:
            examples.append({'symbol':sym(fp),'lux_summary':r_l['summary'],'pine_summary':r_p['summary']})
        if i%500==0: print('processed',i,'elapsed',round(time.time()-t,1),flush=True)
    status={
      'BOS/CHOCH/MSS': {'source':'luxalgo_v34','trading':'enabled','status':'PARTIAL_PINE_ALIGNED','reason':'LuxAlgo leg/displayStructure implemented; exact user Pine event diff still pending'},
      'OB': {'source':'luxalgo_v34 storeOrderBlock','trading':'enabled','status':'ENABLED_CLEAN','reason':'same-event OB only'},
      'SWEEP': {'source':'luxalgo_v34 swing pivot sweep','trading':'enabled','status':'PARTIAL','reason':'EQL/EQH pool sweeps not merged'},
      'FVG': {'source':'pine_like','trading':'quarantined','status':'FAILED_P4_IF_ENABLED','reason':'V35 FVG add-on WR57.1 SL35.7; TREND_UP FVG polluted entries'},
      'BPR': {'source':'pine_like','trading':'quarantined','status':'NOT_VALIDATED','reason':'no standalone profitable sample in V35; needs exact BPR semantics'},
      'BRK': {'source':'missing in V35','trading':'disabled','status':'MISSING'},
      'EQL/EQH': {'source':'pine_like','trading':'display_only','status':'NOT_MERGED_TO_SWEEP'},
      'LV': {'source':'pine_like simple range/body','trading':'disabled','status':'NOT_PINE_EXACT'},
      'OTE': {'source':'pine_like structure zone','trading':'disabled','status':'NOT_VALIDATED'},
      'PB': {'source':'confirmation only','trading':'confirmation_only','status':'OK_AS_CONFIRMATION_NOT_SIGNAL'},
      'RB': {'source':'missing in V35','trading':'disabled','status':'MISSING'}
    }
    report={'aggregate_counts':agg,'avg_per_stock':{k:round(v/max(agg['stocks'],1),2) for k,v in agg.items() if k!='stocks'},'status':status,'examples':examples}
    (OUT/'p1_signal_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
