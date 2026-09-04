#!/usr/bin/env python3
"""V70 candidate engine: repair zone-dead by adding post-zone reaction confirmation.

New hypothesis from V70 root-cause audit:
- 97% of SL trades were true zone death / close below zone low, not only SL noise.
- Original V68 enters at zone midpoint too early, before confirming demand actually reacts.
- New candidates wait for zone touch -> reclaim/continuation confirmation -> next-day executable entry.

No production/frontend writes.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional

ROOT=Path('/root/.hermes')
KLINE_DIR=ROOT/'kline_cache'
OUT_DIR=ROOT/'smc_opt_v70_reaction_confirm'
OUT_DIR.mkdir(parents=True, exist_ok=True)
MAX_HOLD=60

def f(x:Any, default:float=0.0)->float:
    try:
        if x is None or x=='': return default
        v=float(x); return v if math.isfinite(v) else default
    except Exception: return default

def d(b): return str(b.get('t') or b.get('date') or '')[:8]

def atr(ks,idx,n=14):
    trs=[]
    for i in range(max(1,idx-n+1),idx+1):
        h,l,pc=f(ks[i].get('h')),f(ks[i].get('l')),f(ks[i-1].get('c'))
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0

def ma(vals,n): return sum(vals[-n:])/n if len(vals)>=n else None

def is_sw_low(ks,i,L=3,R=3):
    if i-L<0 or i+R>=len(ks): return False
    lo=f(ks[i].get('l'))
    return all(f(ks[j].get('l'))>lo for j in range(i-L,i)) and all(f(ks[j].get('l'))>=lo for j in range(i+1,i+R+1))

def is_sw_high(ks,i,L=3,R=3):
    if i-L<0 or i+R>=len(ks): return False
    hi=f(ks[i].get('h'))
    return all(f(ks[j].get('h'))<hi for j in range(i-L,i)) and all(f(ks[j].get('h'))<=hi for j in range(i+1,i+R+1))

def swings_until(ks,upto):
    lows=[]; highs=[]
    for i in range(3,max(3,upto-3)+1):
        if is_sw_low(ks,i): lows.append({'bar':i,'price':f(ks[i].get('l'))})
        if is_sw_high(ks,i): highs.append({'bar':i,'price':f(ks[i].get('h'))})
    return lows,highs

def trend(ks,idx):
    closes=[f(b.get('c')) for b in ks[:idx+1]]; c=closes[-1]
    m20=ma(closes,20); m60=ma(closes,60)
    ret20=(c/closes[-21]-1)*100 if len(closes)>21 and closes[-21] else 0
    ret60=(c/closes[-61]-1)*100 if len(closes)>61 and closes[-61] else 0
    hi60=max(f(b.get('h')) for b in ks[max(0,idx-60):idx+1]); lo60=min(f(b.get('l')) for b in ks[max(0,idx-60):idx+1])
    pos60=(c-lo60)/max(hi60-lo60,1e-9)*100
    if m20 and m60 and c>m20>m60 and ret20>0: state='TREND_UP'
    elif m20 and m60 and c<m20<m60 and ret20<0: state='TREND_DOWN'
    elif ret60 < -8: state='DOWN_60'
    elif ret20 > 5 and pos60 > 75: state='EXTENDED_UP'
    else: state='RANGE_TRANSITION'
    return {'trend_state':state,'ret20':ret20,'ret60':ret60,'pos60':pos60,'above_ma20':bool(m20 and c>m20),'above_ma60':bool(m60 and c>m60)}

def find_ssl(ks):
    out=[]; lows=[]
    for i in range(8,len(ks)-MAX_HOLD-5):
        cand=i-3
        if cand>=3 and is_sw_low(ks,cand): lows.append({'bar':cand,'price':f(ks[cand].get('l'))})
        recent=[x for x in lows if 3<=i-x['bar']<=60]
        if not recent: continue
        lo,cl,op=f(ks[i].get('l')),f(ks[i].get('c')),f(ks[i].get('o')); a=atr(ks,i)
        target=min(recent,key=lambda x:(abs(lo-x['price'])/max(x['price'],1e-9),i-x['bar']))
        pierce=target['price']-lo
        if pierce>=max(a*0.05,target['price']*0.0015) and cl>target['price'] and cl>op:
            out.append({'bar':i,'liq_price':target['price'],'sweep_low':lo,'pierce_atr':pierce/max(a,1e-9)})
    return out

def displacement(ks,lbar,max_wait=12):
    _, highs=swings_until(ks,lbar)
    highs=[h for h in highs if 3<=lbar-h['bar']<=80]
    if not highs: return None
    sh=highs[-1]
    for j in range(lbar+1,min(len(ks)-MAX_HOLD-4,lbar+max_wait+1)):
        op,cl=f(ks[j].get('o')),f(ks[j].get('c')); body=cl-op; a=atr(ks,j)
        if cl>sh['price'] and body>0 and body>=a*0.35:
            return {'bar':j,'swing_high':sh['price'],'disp_atr':body/max(a,1e-9)}
    return None

def fvg_pois(ks,lbar,dbar):
    out=[]
    for i in range(max(lbar+2,dbar-2),min(dbar+3,len(ks))):
        h0=f(ks[i-2].get('h')); l2=f(ks[i].get('l'))
        if h0>0 and l2>h0 and (l2-h0)>=atr(ks,i)*0.20:
            out.append({'bar':i-1,'low':h0,'high':l2,'type':'FVG_Demand'})
    return out

def recent_swing_low(ks,idx,fallback):
    lows,_=swings_until(ks,idx)
    c=[x for x in lows if 3<=idx-x['bar']<=40]
    return min(c[-5:],key=lambda x:x['price'])['price'] if c else fallback

def confirm_after_touch(ks,poi,dbar,mode):
    zl,zh=poi['low'],poi['high']; touch=None
    for i in range(max(dbar+1,poi['bar']+1),min(len(ks)-MAX_HOLD-3,dbar+20)):
        op,cl,hi,lo=f(ks[i].get('o')),f(ks[i].get('c')),f(ks[i].get('h')),f(ks[i].get('l'))
        if touch is None:
            if lo<=zh and hi>=zl:
                if cl<zl: return None
                touch=i
            continue
        # after touch, require demand reaction; this is the core repair
        if cl < zl: return None
        if mode=='reclaim_zone_high' and cl>zh and cl>op:
            return {'confirm_idx':i,'touch_idx':touch,'entry_idx':i+1,'entry_price':f(ks[i+1].get('o')),'entry_rule':'next_open_after_zone_high_reclaim'}
        if mode=='two_bar_reclaim' and i>=touch+1:
            prev=ks[i-1]
            if f(prev.get('c'))>zl and cl>zh and cl>op:
                return {'confirm_idx':i,'touch_idx':touch,'entry_idx':i+1,'entry_price':f(ks[i+1].get('o')),'entry_rule':'next_open_after_two_bar_reclaim'}
        if mode=='break_disp_high' and cl>max(zh, f(ks[dbar].get('h'))) and cl>op:
            return {'confirm_idx':i,'touch_idx':touch,'entry_idx':i+1,'entry_price':f(ks[i+1].get('o')),'entry_rule':'next_open_after_break_displacement_high'}
    return None

def simulate(ks,eidx,ep,sl,tp,max_hold=MAX_HOLD):
    if not (sl<ep<tp): return None
    for j in range(eidx+1,min(len(ks),eidx+max_hold+1)):
        lo,hi=f(ks[j].get('l')),f(ks[j].get('h'))
        if lo<=sl:
            return {'exit_idx':j,'exit_date':d(ks[j]),'exit_reason':'SL_HIT','exit_price':round(sl,4),'hold_bars':j-eidx,'pnl_pct':round((sl/ep-1)*100,4)}
        if hi>=tp:
            return {'exit_idx':j,'exit_date':d(ks[j]),'exit_reason':'TP1_HIT','exit_price':round(tp,4),'hold_bars':j-eidx,'pnl_pct':round((tp/ep-1)*100,4)}
    if eidx+max_hold<len(ks):
        px=f(ks[eidx+max_hold].get('c'))
        return {'exit_idx':eidx+max_hold,'exit_date':d(ks[eidx+max_hold]),'exit_reason':'TIME_STOP','exit_price':round(px,4),'hold_bars':max_hold,'pnl_pct':round((px/ep-1)*100,4)}
    return None

def rows_for(symbol,ks):
    rows=[]; used=set()
    for L in find_ssl(ks):
        D=displacement(ks,L['bar'])
        if not D: continue
        if D['disp_atr']<1.0: continue
        for poi in fvg_pois(ks,L['bar'],D['bar']):
            zl,zh=poi['low'],poi['high']
            for mode in ('reclaim_zone_high','two_bar_reclaim','break_disp_high'):
                ent=confirm_after_touch(ks,poi,D['bar'],mode)
                if not ent: continue
                eidx=ent['entry_idx']; ep=ent['entry_price']
                if eidx>=len(ks)-MAX_HOLD-1 or ep<=0: continue
                tr=trend(ks,eidx)
                if tr['trend_state'] in ('TREND_DOWN','DOWN_60','EXTENDED_UP'): continue
                if not tr['above_ma20']: continue
                # confirm entry should not be too far above zone; avoid chasing after delayed reclaim
                chase_pct=(ep/zh-1)*100
                if chase_pct>4.0: continue
                retr=max(0,min(100,(zh-f(ks[ent['touch_idx']].get('l')))/max(zh-zl,1e-9)*100))
                if not (30<=retr<100): continue
                base_sl=recent_swing_low(ks,eidx,min(L['sweep_low'],zl))
                a=atr(ks,eidx)
                for sl_mode,sl in (('zone_low',min(zl*0.985,zl-a*0.25)),('structure',min(base_sl*0.995,base_sl-a*0.15))):
                    if not (0<sl<ep): continue
                    risk=(ep/sl-1)*100
                    if not (1<=risk<=10): continue
                    for rr in (0.05,0.08,0.10,0.15,0.20,0.30,0.50,0.80,1.00):
                        tp=ep+(ep-sl)*rr
                        sim=simulate(ks,eidx,ep,sl,tp)
                        if not sim: continue
                        key=(eidx,poi['bar'],mode,sl_mode,rr)
                        if key in used: continue
                        used.add(key)
                        rows.append({'symbol':symbol,'engine':'V70_REACTION_CONFIRM','definition_version':'LD_FVG_touch_reclaim_next_open','mode':mode,'sl_mode':sl_mode,'rr':rr,'sequence':'SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_TOUCH -> REACTION_CONFIRM -> NEXT_OPEN_ENTRY','liq_bar':L['bar'],'confirm_bar':D['bar'],'zone_bar':poi['bar'],'touch_idx':ent['touch_idx'],'reaction_confirm_idx':ent['confirm_idx'],'entry_idx':eidx,'liq_date':d(ks[L['bar']]),'confirm_date':d(ks[D['bar']]),'zone_date':d(ks[poi['bar']]),'touch_date':d(ks[ent['touch_idx']]),'entry_date':d(ks[eidx]),'pick_date':d(ks[eidx]),'join_date':d(ks[eidx]),'zone_type':'FVG_Demand','signal_type':'FVG_Demand','zone_low':round(zl,4),'zone_high':round(zh,4),'entry_price':round(ep,4),'price':round(ep,4),'smart_money_cost':round(ep,4),'cost_line':round(ep,4),'sl':round(sl,4),'tp1':round(tp,4),'risk_pct':round(risk,3),'volatility_pct':round(risk,3),'retrace_pct':round(retr,2),'chase_pct':round(chase_pct,3),'pierce_atr':round(L['pierce_atr'],3),'disp_atr':round(D['disp_atr'],3),**tr,**sim})
    return rows

def replay(kf):
    sym=kf.stem.replace('_daily_750',''); symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: ks=json.loads(kf.read_text())
    except Exception: return []
    if len(ks)<180: return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    return rows_for(symbol,ks)

def metrics(rs):
    if not rs: return {'n':0}
    wins=[r for r in rs if r['pnl_pct']>0]; losses=[r for r in rs if r['pnl_pct']<=0]
    return {'n':len(rs),'wr':round(len(wins)/len(rs)*100,2),'avg_pnl':round(sum(r['pnl_pct'] for r in rs)/len(rs),4),'sl_rate':round(sum(r['exit_reason']=='SL_HIT' for r in rs)/len(rs)*100,2),'tp_rate':round(sum(r['exit_reason']=='TP1_HIT' for r in rs)/len(rs)*100,2),'avg_win':round(sum(r['pnl_pct'] for r in wins)/len(wins),4) if wins else 0,'avg_loss':round(sum(r['pnl_pct'] for r in losses)/len(losses),4) if losses else 0,'avg_hold':round(sum(r['hold_bars'] for r in rs)/len(rs),2)}

def bucket(rs,fn):
    g=defaultdict(list)
    for r in rs: g[fn(r)].append(r)
    return {str(k):metrics(v) for k,v in sorted(g.items(), key=lambda kv:str(kv[0]))}

def audit(rs):
    fails=[]
    for r in rs:
        issues=[]
        if not (r['liq_bar'] < r['confirm_bar'] and r['zone_bar'] <= r['confirm_bar'] + 1 and r['confirm_bar'] < r['touch_idx'] <= r['reaction_confirm_idx'] < r['entry_idx']): issues.append('semantic_order')
        if r['exit_idx']<=r['entry_idx']: issues.append('t_plus_1')
        for k in ('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1'):
            if r.get(k) in (None,'',0,0.0): issues.append('missing_'+k)
        if issues: fails.append({'symbol':r['symbol'],'entry_date':r['entry_date'],'issues':issues})
    return {'n':len(rs),'fail_count':len(fails),'semantic_order_fail':sum('semantic_order' in x['issues'] for x in fails),'t_plus_1_fail':sum('t_plus_1' in x['issues'] for x in fails),'field_contract_fail':sum(any(i.startswith('missing_') for i in x['issues']) for x in fails),'sample_fails':fails[:20]}

def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    all_rows=[]
    print('V70 reaction confirm full replay',len(files),datetime.now().strftime('%H:%M:%S'),flush=True)
    for i,kf in enumerate(files,1):
        all_rows.extend(replay(kf))
        if i%500==0: print(i,'trades',len(all_rows),flush=True)
    combos=[]
    groups=defaultdict(list)
    for r in all_rows: groups[(r['mode'],r['sl_mode'],r['rr'])].append(r)
    for k,v in groups.items(): combos.append({'mode':k[0],'sl_mode':k[1],'rr':k[2],**metrics(v)})
    combos.sort(key=lambda x:(x['wr'],min(x['n'],500),x['avg_pnl']), reverse=True)
    report={'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(files),'metrics':metrics(all_rows),'audit':audit(all_rows),'combo_table':combos,'buckets':{'mode':bucket(all_rows,lambda r:r['mode']),'sl_mode':bucket(all_rows,lambda r:r['sl_mode']),'rr':bucket(all_rows,lambda r:r['rr']),'trend':bucket(all_rows,lambda r:r['trend_state']),'chase_bin':bucket(all_rows,lambda r:'<=1' if r['chase_pct']<=1 else ('1-2' if r['chase_pct']<=2 else ('2-4' if r['chase_pct']<=4 else '>4'))),'exit':bucket(all_rows,lambda r:r['exit_reason'])},'decision':'NO_PRODUCTION_SYNC'}
    if combos and combos[0]['n']>=100 and combos[0]['wr']>=90 and report['audit']['fail_count']==0:
        report['decision']='CANDIDATE_PASSES_90_NEEDS_FRONTEND_SYNC'
    (OUT_DIR/'v70_trades.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2))
    (OUT_DIR/'v70_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({'metrics':report['metrics'],'audit':report['audit'],'top10':combos[:10],'decision':report['decision'],'out':str(OUT_DIR)},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
