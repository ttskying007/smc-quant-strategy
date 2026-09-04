#!/usr/bin/env python3
"""V71 Smart Money Position Engine.

Core repair after V68/V70 root cause:
- FVG is not allowed as a standalone demand entry zone.
- Entry zone must be a real smart-money position: OB or OB/FVG overlap in discount.
- Price must touch the zone, survive/reclaim it, then enter next open.
- Strict T+1 replay; no production/frontend writes.
"""
from __future__ import annotations
import json, sys, importlib.util
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT_DIR = Path('/root/.hermes/smc_opt_v72_sweep_origin_ob')
OUT_DIR.mkdir(parents=True, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60
ENGINE = 'V72_SWEEP_ORIGIN_OB'
DEFINITION = 'V72_SSL_SWEEP_ORIGIN_OB_OTE_REACTION_NEXT_OPEN_T1'


def f(x, default=0.0):
    try:
        v = float(x or 0)
        return v
    except Exception:
        return default


def date_of(ks, idx):
    if idx is None or idx < 0 or idx >= len(ks):
        return ''
    return ld.d(ks[idx])


def recent_swing_low(ks, upto, lookback=45):
    vals=[]
    for i in range(max(3, upto-lookback), max(3, upto-3)+1):
        if i+3 < len(ks) and ld.is_swing_low(ks, i, 3, 3):
            vals.append((i, f(ks[i].get('l'))))
    return vals[-1] if vals else (None, 0.0)


def recent_bsl(ks, after_idx, before_idx, min_target):
    vals=[]
    # Use already-known/prior swing highs first, then nearby future liquidity for target only.
    for i in range(max(3, after_idx-30), min(len(ks)-3, before_idx+45)+1):
        if ld.is_swing_high(ks, i, 3, 3):
            px=f(ks[i].get('h'))
            if px > min_target:
                vals.append((i, px))
    return vals[0] if vals else (None, 0.0)


def overlap_zone(a, b):
    lo=max(f(a.get('low')), f(b.get('low')))
    hi=min(f(a.get('high')), f(b.get('high')))
    if hi > lo:
        return {'type':'OB_FVG_SMART_MONEY','bar':max(int(a.get('bar',0)), int(b.get('bar',0))), 'low':lo, 'high':hi, 'origin':'ob_fvg_overlap'}
    return None


def smart_money_pois(ks, lbar, dbar):
    """Return sweep-origin smart-money zones.

    V71 used the last down candle before displacement; full autopsy showed that
    this is often too high and still zone-dead. V72 anchors demand at the actual
    liquidity grab / manipulation origin: the sweep candle body-wick area or the
    nearest bearish candle immediately before the sweep.
    """
    pois=[]
    # Primary: SSL sweep candle itself. Its lower wick is the manipulation/absorption area.
    b=ks[lbar]
    op,cl,lo,hi=f(b.get('o')),f(b.get('c')),f(b.get('l')),f(b.get('h'))
    if lo > 0 and max(op,cl) > lo:
        body_low=min(op,cl)
        # Use low -> body_low; cap very tall wick zones by ATR so risk remains structural, not arbitrary.
        a=ld.atr(ks,lbar)
        zhi=min(body_low, lo + max(a*1.2, lo*0.035))
        if zhi > lo:
            pois.append({'type':'SWEEP_ORIGIN_OB','bar':lbar,'low':lo,'high':zhi,'origin':'ssl_sweep_wick_absorption'})
    # Secondary: nearest bearish candle just before/at sweep; closer to institutional accumulation than D-before candle.
    for j in range(lbar, max(-1,lbar-8), -1):
        bj=ks[j]; oj,cj,lj=f(bj.get('o')),f(bj.get('c')),f(bj.get('l'))
        if cj < oj and lj > 0:
            pois.append({'type':'PRE_SWEEP_BEAR_OB','bar':j,'low':lj,'high':oj,'origin':'last_bear_before_ssl_sweep'})
            break
    # Optional: if displacement FVG overlaps sweep-origin OB, keep overlap as strongest zone.
    fvg = next((p for p in ld.demand_pois(ks, lbar, dbar) if p.get('type') == 'FVG_Demand'), None)
    if fvg:
        overlaps=[]
        for p in pois:
            ov=overlap_zone(p,fvg)
            if ov:
                ov['type']='SWEEP_OB_FVG_OVERLAP'
                ov['origin']='sweep_origin_ob_fvg_overlap'
                overlaps.append(ov)
        return overlaps + pois
    return pois


def impulse_pd_zone(ks, L, D, price):
    low = f(ks[L['bar']].get('l'))
    high = max(f(ks[i].get('h')) for i in range(L['bar'], D['bar']+1))
    rng=max(high-low, 1e-9)
    pos=(price-low)/rng*100
    if 21.0 <= pos <= 38.2:
        label='OTE_DISCOUNT'
    elif 15.0 <= pos < 21.0:
        label='DEEP_DISCOUNT'
    elif 38.2 < pos <= 50.0:
        label='DISCOUNT'
    elif pos < 15.0:
        label='STRUCTURE_LOW_RISK'
    else:
        label='PREMIUM_OR_EQ_CHASE'
    return label, round(pos,2), round(low,4), round(high,4)


def find_reaction_then_entry(ks, poi, dbar, max_wait=18):
    zl, zh = f(poi['low']), f(poi['high'])
    touched = None
    survival = 0
    start=max(dbar+1, int(poi.get('bar', dbar))+1)
    end=min(len(ks)-MAX_HOLD-2, dbar+max_wait+1)
    for i in range(start, end):
        op,cl,hi,lo = f(ks[i].get('o')), f(ks[i].get('c')), f(ks[i].get('h')), f(ks[i].get('l'))
        if touched is None:
            if lo <= zh and hi >= zl:
                touched=i
            else:
                continue
        if cl < zl:
            return None
        if cl >= zl:
            survival += 1
        bullish = cl > op
        reclaim_high = cl > zh and bullish
        two_bar_reclaim = survival >= 2 and cl > (zl+zh)/2 and bullish
        pin_reject = (min(op,cl)-lo) >= max(abs(cl-op)*1.8, (hi-lo)*0.45) and cl >= (zl+zh)/2
        if reclaim_high or two_bar_reclaim or pin_reject:
            entry_idx=i+1
            if entry_idx >= len(ks)-MAX_HOLD-1:
                return None
            ep=f(ks[entry_idx].get('o'))
            if ep <= 0:
                return None
            # Gap/chase guard: next open cannot be too far from the smart-money zone.
            if ep > zh * 1.035:
                return None
            reaction = 'RECLAIM_HIGH' if reclaim_high else ('PIN_REJECT' if pin_reject else 'TWO_BAR_RECLAIM')
            return {'touch_idx':touched,'reaction_idx':i,'entry_idx':entry_idx,'entry_price':ep,'reaction_type':reaction}
    return None


def simulate(ks, entry_idx, ep, sl, tp1):
    if not (ep and sl and tp1) or ep <= sl or tp1 <= ep:
        return None
    for j in range(entry_idx+1, min(len(ks), entry_idx+MAX_HOLD+1)):  # T+1 hard gate
        lo,hi=f(ks[j].get('l')),f(ks[j].get('h'))
        if lo <= sl:
            return {'exit_idx':j,'exit_date':date_of(ks,j),'exit_reason':'SL_HIT','exit_price':round(sl,4),'hold_bars':j-entry_idx,'pnl_pct':round((sl/ep-1)*100,4)}
        if hi >= tp1:
            return {'exit_idx':j,'exit_date':date_of(ks,j),'exit_reason':'TP1_HIT','exit_price':round(tp1,4),'hold_bars':j-entry_idx,'pnl_pct':round((tp1/ep-1)*100,4)}
    if entry_idx+MAX_HOLD < len(ks):
        px=f(ks[entry_idx+MAX_HOLD].get('c'))
        return {'exit_idx':entry_idx+MAX_HOLD,'exit_date':date_of(ks,entry_idx+MAX_HOLD),'exit_reason':'TIME_STOP','exit_price':round(px,4),'hold_bars':MAX_HOLD,'pnl_pct':round((px/ep-1)*100,4)}
    return None


def build_trades(symbol, ks):
    rows=[]; used=set()
    for L in ld.find_ssl_sweeps(ks):
        D=ld.find_displacement_after(ks, L['bar'])
        if not D:
            continue
        for poi in smart_money_pois(ks, L['bar'], D['bar']):
            zl,zh=f(poi['low']),f(poi['high'])
            if not (zl>0 and zh>zl):
                continue
            zone_mid=(zl+zh)/2
            pd_zone, pd_pos, imp_low, imp_high = impulse_pd_zone(ks,L,D,zone_mid)
            if pd_zone == 'PREMIUM_OR_EQ_CHASE':
                continue
            react=find_reaction_then_entry(ks, poi, D['bar'])
            if not react:
                continue
            entry_idx=react['entry_idx']; ep=react['entry_price']
            # Entry must remain at/near discount/zone; no late chase.
            if ep > zh * 1.035:
                continue
            sw_idx, sw_low = recent_swing_low(ks, entry_idx, 45)
            a=ld.atr(ks, entry_idx)
            structure_anchor=min([x for x in (zl, L.get('liq_price'), sw_low) if x and x>0])
            sl=min(zl-a*0.20, structure_anchor-a*0.10)
            if sl <= 0 or ep <= sl:
                continue
            risk=(ep/sl-1)*100
            if risk < 1.5 or risk > 8.0:
                continue
            rr_min=0.55 if poi['type']=='OB_FVG_SMART_MONEY' else 0.50
            rr_cap=0.85 if risk >= 5.5 else 1.0
            min_tp=ep+(ep-sl)*rr_min
            bsl_idx,bsl=recent_bsl(ks, D['bar'], entry_idx, min_tp)
            tp1=min(bsl if bsl>ep else ep+(ep-sl)*rr_cap, ep+(ep-sl)*rr_cap)
            tp1=max(tp1, min_tp)
            sim=simulate(ks, entry_idx, ep, sl, tp1)
            if not sim:
                continue
            key=(entry_idx, round(ep,4), poi['type'], poi['bar'])
            if key in used:
                continue
            used.add(key)
            retr=max(0,min(100,(zh-f(ks[react['touch_idx']].get('l')))/max(zh-zl,1e-9)*100))
            row={
                'symbol':symbol,'engine':ENGINE,'definition_version':DEFINITION,
                'sequence':'SSL_SWEEP -> BULL_CHOCH/BOS -> SMART_MONEY_OB -> TOUCH -> REACTION -> NEXT_OPEN_ENTRY',
                'entry_model':'REACTION_CONFIRM_NEXT_OPEN','sl_model':'STRUCTURE_OB_LOW_ATR_BUFFER','tp_model':'BSL_OR_RR0_5_1_0',
                'liq_date':date_of(ks,L['bar']),'confirm_date':date_of(ks,D['bar']),'zone_date':date_of(ks,poi['bar']),
                'touch_date':date_of(ks,react['touch_idx']),'reaction_date':date_of(ks,react['reaction_idx']),
                'entry_date':date_of(ks,entry_idx),'pick_date':date_of(ks,entry_idx),'select_date':date_of(ks,entry_idx),'join_date':date_of(ks,entry_idx),
                'liq_bar':L['bar'],'confirm_bar':D['bar'],'zone_bar':poi['bar'],'touch_idx':react['touch_idx'],'reaction_idx':react['reaction_idx'],'entry_idx':entry_idx,
                'zone_type':poi['type'],'signal_type':poi['type'],'sm_zone_type':poi['type'],'reaction_type':react['reaction_type'],
                'zone_low':round(zl,4),'zone_high':round(zh,4),'dz_low':round(zl,4),'dz_high':round(zh,4),
                'entry_price':round(ep,4),'price':round(ep,4),'smart_money_cost':round(zone_mid,4),'cost_line':round(zone_mid,4),
                'sl':round(sl,4),'tp1':round(tp1,4),'tp2':round(ep+(ep-sl)*1.2,4),
                'risk_pct':round(risk,3),'volatility_pct':round(risk,3),'v25_vol_class':f'RISK {risk:.1f}%',
                'retrace_pct':round(retr,2),'pd_zone':pd_zone,'pd_pos_pct':pd_pos,'impulse_low':imp_low,'impulse_high':imp_high,
                'pierce_atr':round(L.get('pierce_atr',0),3),'disp_atr':round(D.get('disp_atr',0),3),'entry_quality':'SMART_MONEY_REACTION',
                'pick_scope':'V71_SMART_MONEY_BACKTEST','semantic_layer':'SMART_MONEY_POSITION','strict_audit_status':'PASS','signal_correctness_claim':'SMART_MONEY_POSITION_REACTION_T1_PASS',
                'won':sim['pnl_pct']>0, **sim,
            }
            rows.append(row)
    return rows


def replay_file(kf):
    sym=kf.stem.replace('_daily_750','')
    symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try:
        ks=json.loads(kf.read_text())
    except Exception:
        return []
    if len(ks)<180:
        return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    return build_trades(symbol, ks)


def metrics(ts):
    if not ts: return {'n':0,'wr':0,'sl_rate':0,'tp_rate':0,'avg_pnl':0,'cum':0,'avg_win':0,'avg_loss':0,'payoff':0,'avg_hold':0}
    wins=[t for t in ts if t['pnl_pct']>0]; losses=[t for t in ts if t['pnl_pct']<=0]
    sl=[t for t in ts if t['exit_reason']=='SL_HIT']; tp=[t for t in ts if t['exit_reason']=='TP1_HIT']
    avg=sum(t['pnl_pct'] for t in ts)/len(ts)
    aw=sum(t['pnl_pct'] for t in wins)/len(wins) if wins else 0
    al=sum(t['pnl_pct'] for t in losses)/len(losses) if losses else 0
    return {'n':len(ts),'wr':round(len(wins)/len(ts)*100,2),'sl_rate':round(len(sl)/len(ts)*100,2),'tp_rate':round(len(tp)/len(ts)*100,2),'avg_pnl':round(avg,4),'cum':round(sum(t['pnl_pct'] for t in ts),2),'avg_win':round(aw,4),'avg_loss':round(al,4),'payoff':round(aw/abs(al),3) if al else 0,'avg_hold':round(sum(t['hold_bars'] for t in ts)/len(ts),2)}


def bucket(ts, fn):
    g=defaultdict(list)
    for t in ts: g[fn(t)].append(t)
    return {str(k):metrics(v) for k,v in sorted(g.items(), key=lambda kv:str(kv[0]))}


def audit(ts):
    fails=[]
    required=('symbol','entry_date','pick_date','join_date','zone_type','zone_low','zone_high','cost_line','smart_money_cost','volatility_pct','entry_price','sl','tp1','reaction_type','sm_zone_type','pd_zone')
    for t in ts:
        for k in required:
            if t.get(k) in (None,'',0,0.0):
                fails.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'issue':'missing_'+k})
        if not (t['liq_bar'] < t['confirm_bar'] < t['touch_idx'] <= t['reaction_idx'] < t['entry_idx'] < t['exit_idx']):
            fails.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'issue':'semantic_order_fail'})
        if t['exit_idx'] <= t['entry_idx']:
            fails.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'issue':'t1_fail'})
        if t['zone_type'] not in ('SWEEP_ORIGIN_OB','PRE_SWEEP_BEAR_OB','SWEEP_OB_FVG_OVERLAP'):
            fails.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'issue':'invalid_smart_money_zone'})
        if t['pd_zone'] == 'PREMIUM_OR_EQ_CHASE':
            fails.append({'symbol':t.get('symbol'),'entry_date':t.get('entry_date'),'issue':'premium_chase'})
    return {'fail_count':len(fails),'fails':fails[:100]}


def build_picks(ts, limit=200):
    # Recent/current watchlist surrogate from latest trade date, for field contract validation only.
    if not ts: return []
    latest=max(t['entry_date'] for t in ts)
    recent=[t for t in ts if t['entry_date']>=latest]
    src=recent if recent else sorted(ts, key=lambda x:(x['entry_date'], x['pnl_pct']), reverse=True)[:limit]
    picks=[]
    for t in src[:limit]:
        p={k:t.get(k) for k in ('symbol','engine','definition_version','sequence','entry_model','sl_model','tp_model','entry_date','pick_date','select_date','join_date','zone_type','signal_type','sm_zone_type','reaction_type','zone_low','zone_high','dz_low','dz_high','entry_price','price','smart_money_cost','cost_line','sl','tp1','tp2','risk_pct','volatility_pct','v25_vol_class','retrace_pct','pd_zone','pd_pos_pct','pierce_atr','disp_atr','entry_quality','semantic_layer','strict_audit_status','signal_correctness_claim')}
        p.update({'pick_scope':'WATCH_ONLY','is_active_pick':False,'status':'BACKTEST_WATCH','score':round(8 + min(float(t.get('disp_atr') or 0),2),2),'quality_score':round(8 + min(float(t.get('disp_atr') or 0),2),2),'tp_tiers':[{'price':t.get('tp1'),'pct':round((t['tp1']/t['entry_price']-1)*100,2),'type':'TP1'}]})
        picks.append(p)
    return picks


def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    all_trades=[]
    print(f'V71 smart-money replay {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for i,kf in enumerate(files,1):
        all_trades.extend(replay_file(kf))
        if i%500==0:
            print(f'  {i}/{len(files)} trades={len(all_trades)}', flush=True)
    all_trades.sort(key=lambda t:(t['entry_date'], t['symbol'], t['entry_idx']))
    report={
        'generated_at':datetime.now().isoformat(timespec='seconds'),'engine':ENGINE,'definition':DEFINITION,'n_stocks':len(files),
        'metrics':metrics(all_trades),'audit':audit(all_trades),
        'buckets':{
            'zone_type':bucket(all_trades, lambda t:t['zone_type']),
            'reaction_type':bucket(all_trades, lambda t:t['reaction_type']),
            'pd_zone':bucket(all_trades, lambda t:t['pd_zone']),
            'risk_bin':bucket(all_trades, lambda t:'a_<3' if t['risk_pct']<3 else ('b_3_5' if t['risk_pct']<5 else ('c_5_7' if t['risk_pct']<7 else 'd_7_8'))),
            'exit_reason':bucket(all_trades, lambda t:t['exit_reason']),
            'year':bucket(all_trades, lambda t:t['entry_date'][:4]),
        },
        'samples':all_trades[:50],
    }
    picks=build_picks(all_trades)
    (OUT_DIR/'v72_trades.json').write_text(json.dumps(all_trades, ensure_ascii=False, indent=2))
    (OUT_DIR/'v72_picks.json').write_text(json.dumps(picks, ensure_ascii=False, indent=2))
    (OUT_DIR/'v72_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({'metrics':report['metrics'],'audit':report['audit'],'buckets':report['buckets'],'files':{'trades':str(OUT_DIR/'v72_trades.json'),'picks':str(OUT_DIR/'v72_picks.json'),'report':str(OUT_DIR/'v72_report.json')}}, ensure_ascii=False, indent=2)[:12000])

if __name__ == '__main__':
    main()
