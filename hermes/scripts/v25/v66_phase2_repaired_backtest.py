#!/usr/bin/env python3
"""Full-market historical replay for repaired V66 Phase2 POI retrace rules.
Uses the same v25 smc_detector + SL/TP/state/filter rules as daily_scan.py.
Outputs fixed strategy metrics and a baseline without the newly-added hard gates.
"""
import json, sys, math
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts/v25')
from smc_detector import detect_smc_signals
from daily_scan import atr, detect_state, _trend_ctx, _pass_daily_gate, compute_sltp

ROOT = Path('/root/.hermes')
KLINE_DIR = ROOT / 'kline_cache'
OUT = ROOT / 'smc_opt_v25' / 'v66_phase2_repaired_backtest.json'
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60


def d(b):
    return str(b.get('t') or b.get('date') or '')[:8]

def f(v):
    try: return float(v or 0)
    except Exception: return 0.0

def simulate(klines, entry_idx, pick):
    ep = f(pick.get('entry_price') or pick.get('price'))
    sl = f(pick.get('v25_sl_price') or pick.get('sl'))
    tp1 = 0.0
    tiers = pick.get('v25_tp_tiers') or []
    if tiers and isinstance(tiers[0], dict):
        tp1 = f(tiers[0].get('price'))
    tp1 = tp1 or f(pick.get('tp1'))
    if not (ep and sl and tp1) or ep <= sl:
        return None
    end = min(len(klines), entry_idx + MAX_HOLD + 1)
    for j in range(entry_idx + 1, end):  # T+1: no same-day exit
        lo, hi = f(klines[j].get('l')), f(klines[j].get('h'))
        if lo <= sl:
            return {**pick, 'exit_date': d(klines[j]), 'exit_price': round(sl, 4), 'exit_reason': 'SL_HIT', 'hold_bars': j-entry_idx, 'pnl_pct': round((sl/ep-1)*100, 4), 'won': False}
        if hi >= tp1:
            return {**pick, 'exit_date': d(klines[j]), 'exit_price': round(tp1, 4), 'exit_reason': 'TP1_HIT', 'hold_bars': j-entry_idx, 'pnl_pct': round((tp1/ep-1)*100, 4), 'won': True}
    if entry_idx + MAX_HOLD < len(klines):
        px = f(klines[entry_idx + MAX_HOLD].get('c'))
        return {**pick, 'exit_date': d(klines[entry_idx + MAX_HOLD]), 'exit_price': round(px, 4), 'exit_reason': 'TIME_STOP', 'hold_bars': MAX_HOLD, 'pnl_pct': round((px/ep-1)*100, 4), 'won': px > ep}
    return None

def make_pick(symbol, klines, z, c, entry_idx, baseline=False):
    latest_idx = entry_idx
    curr = klines[entry_idx]
    curr_lo, curr_hi = f(curr.get('l')), f(curr.get('h'))
    curr_close, curr_open = f(curr.get('c') or curr.get('o')), f(curr.get('o') or curr.get('c'))
    dz_low = f(z.get('low') or curr_open * 0.97)
    dz_high = f(z.get('high') or curr_open)
    if dz_low <= 0 or dz_high <= dz_low: return None
    if not ((curr_lo <= dz_high) and (curr_hi >= dz_low)): return None
    entry_price = curr_close or curr_open
    if entry_price <= 0: return None
    entry_above_zone_pct = (entry_price / dz_high - 1) * 100 if dz_high > 0 else 0
    if entry_above_zone_pct > 0.8: return None
    if baseline:
        if entry_price < dz_low * 0.97: return None
    else:
        if entry_price < dz_low: return None
    retrace_depth_pct = max(0.0, min(100.0, round((dz_high - curr_lo) / max(dz_high - dz_low, 0.001) * 100, 1)))
    sweeps = make_pick.sweeps
    has_sweep_before = any(sw for sw in sweeps if c.bar - 15 <= sw.bar < c.bar)
    sweep_tag = 'SWEEP_TO_STRUCTURE' if has_sweep_before else 'STRUCTURE_ONLY'
    state_info = detect_state(klines, c.bar)
    market_state = state_info.get('state', 'UNKNOWN')
    if not baseline:
        if market_state in ('RANGE', 'HIGH_VOL', 'UNDEFINED', 'TREND_DOWN'): return None
        if retrace_depth_pct > 70: return None
        if sweep_tag != 'SWEEP_TO_STRUCTURE': return None
    b = klines[c.bar]
    op, cl, hi, lo = f(b.get('o')), f(b.get('c')), f(b.get('h')), f(b.get('l'))
    body_ratio = abs(cl - op) / max(hi - lo, 0.0001)
    tr = _trend_ctx(klines, c.bar)
    score = round(min(95, max(60, 55 + c.confidence * 20 + c.strength * 2 - max(0, tr.get('range_atr', 0) - 4) * 3)), 3)
    ok, reasons, family = _pass_daily_gate(z['type'], c.type, score, tr, body_ratio)
    pick = {
        'symbol': symbol, 'engine': 'V66_REPAIRED_BACKTEST' if not baseline else 'V66_BASELINE_BACKTEST',
        'definition_version': 'V66_PHASE2_POI_RETRACE_REPAIRED' if not baseline else 'V66_PHASE2_POI_RETRACE_BASELINE',
        'entry_date': d(klines[entry_idx]), 'entry_idx': entry_idx,
        'pick_date': d(klines[entry_idx]), 'select_date': d(klines[entry_idx]), 'join_date': d(klines[entry_idx]),
        'zone_date': d(klines[z['bar']]), 'confirm_date': d(klines[c.bar]),
        'price': round(entry_price, 4), 'entry_price': round(entry_price, 4),
        'zone_type': z['type'], 'zone_bar': z['bar'], 'zone_age': entry_idx - z['bar'],
        'conf_type': c.type, 'ctx_seq': f"{z['type']} -> {c.type} -> RETRACE",
        'dz_low': round(dz_low, 4), 'dz_high': round(dz_high, 4), 'zone_low': round(dz_low, 4), 'zone_high': round(dz_high, 4),
        'retrace_pct': retrace_depth_pct, 'retrace_depth_pct': retrace_depth_pct,
        'entry_quality': 'RETRACE', 'quality_tier': 'A_NORMAL', 'score': score, 'breakout_quality_score': score,
        'v59_setup_family': family, 'pick_scope': 'ACTIVE_CANDIDATE' if ok else 'REJECTED_FULL_MARKET_GATE', 'is_active_pick': bool(ok),
        'reject_reason': ';'.join(reasons), 'sweep_tag': sweep_tag, 'market_state': market_state,
    }
    pick.update(compute_sltp(pick, klines))
    pick['sl'] = pick.get('v25_sl_price')
    if pick.get('v25_tp_tiers') and isinstance(pick['v25_tp_tiers'][0], dict): pick['tp1'] = pick['v25_tp_tiers'][0].get('price', 0)
    pick['risk_pct'] = pick.get('v25_sl_pct', 0)
    pick['cost_line'] = pick.get('v25_cost_line') or round((pick['zone_low'] + pick['zone_high']) / 2, 4)
    pick['smart_money_cost'] = pick['cost_line']; pick['volatility_pct'] = pick.get('v25_atr_pct') or pick.get('risk_pct') or 0
    if not baseline and f(pick.get('v25_sl_price')) >= entry_price: return None
    if not baseline and f(pick.get('v25_sl_pct')) > 5: return None
    return pick if pick.get('is_active_pick') else None

def replay_file(kf, baseline=False):
    sym = kf.stem.replace('_daily_750','')
    symbol = sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: klines = json.loads(kf.read_text())
    except Exception: return []
    if len(klines) < 120: return []
    for b in klines:
        for k in ('o','h','l','c','v'):
            if k in b: b[k] = f(b[k])
    try: sigs = detect_smc_signals(klines)
    except Exception: return []
    confirms = [s for s in sigs if s.type in ('BOS_Bull','CHOCH_Bull')]
    make_pick.sweeps = [s for s in sigs if 'Sweep' in s.type]
    zones = []
    for s in sigs:
        if s.type == 'OB_Bull': zones.append({'type':'OB_Bull','bar':s.bar,'low':s.meta.get('ob_low'),'high':s.meta.get('ob_high')})
    # same simple FVG as daily_scan
    for i in range(2, len(klines)):
        hi0, lo2 = f(klines[i-2].get('h')), f(klines[i].get('l'))
        if hi0 > 0 and lo2 > hi0 * 1.002: zones.append({'type':'FVG_Bull','bar':i,'low':hi0,'high':lo2})
    trades=[]; used=set()
    for z in zones:
        zbar=z['bar']
        if zbar < 30 or zbar >= len(klines)-65: continue
        for c in confirms:
            if c.bar <= zbar or c.bar > zbar + 30: continue
            # enter on first retrace after confirmation, not before confirmation
            for eb in range(c.bar + 1, min(zbar + 31, len(klines)-MAX_HOLD-1)):
                key=(zbar,c.bar,eb,z['type'])
                if key in used: continue
                p=make_pick(symbol, klines, z, c, eb, baseline=baseline)
                if p:
                    t=simulate(klines, eb, p)
                    if t:
                        trades.append(t); used.add(key)
                    break
            break
    return trades

def metrics(trades):
    if not trades: return {'n':0}
    wins=[t for t in trades if t['pnl_pct']>0]; losses=[t for t in trades if t['pnl_pct']<=0]
    sl=[t for t in trades if t['exit_reason']=='SL_HIT']; tp=[t for t in trades if t['exit_reason']=='TP1_HIT']
    avg_win=sum(t['pnl_pct'] for t in wins)/max(1,len(wins)); avg_loss=sum(t['pnl_pct'] for t in losses)/max(1,len(losses))
    return {'n':len(trades),'wr':round(len(wins)/len(trades)*100,2),'sl_rate':round(len(sl)/len(trades)*100,2),'tp_rate':round(len(tp)/len(trades)*100,2),'avg_pnl':round(sum(t['pnl_pct'] for t in trades)/len(trades),4),'cum':round(sum(t['pnl_pct'] for t in trades),2),'avg_win':round(avg_win,4),'avg_loss':round(avg_loss,4),'rr':round(avg_win/abs(avg_loss),3) if avg_loss else 0,'avg_hold':round(sum(t['hold_bars'] for t in trades)/len(trades),2)}

def bucket(trades, field):
    out={}
    for k,g in defaultdict(list, {}).items(): pass
    groups=defaultdict(list)
    for t in trades: groups[t.get(field,'')].append(t)
    return {str(k): metrics(v) for k,v in sorted(groups.items(), key=lambda kv: str(kv[0]))}

def bucket_fn(trades, fn):
    groups=defaultdict(list)
    for t in trades: groups[fn(t)].append(t)
    return {str(k): metrics(v) for k,v in sorted(groups.items(), key=lambda kv: str(kv[0]))}

def retr_bin(t):
    r=f(t.get('retrace_depth_pct'))
    if r < 20: return 'a_<20'
    if r < 40: return 'b_20_40'
    if r < 60: return 'c_40_60'
    if r <= 70: return 'd_60_70'
    return 'e_>70'

def sl_bin(t):
    s=f(t.get('risk_pct') or t.get('v25_sl_pct'))
    if s < 2.5: return 'a_<2.5'
    if s < 3.5: return 'b_2.5_3.5'
    if s < 4.5: return 'c_3.5_4.5'
    return 'd_4.5_5'

def score_bin(t):
    s=f(t.get('score'))
    if s < 65: return 'a_<65'
    if s < 70: return 'b_65_70'
    if s < 75: return 'c_70_75'
    return 'd_>=75'

def top_combos(trades, min_n=30):
    combos=[]
    fields=['zone_type','market_state','conf_type','sweep_tag']
    for z in sorted(set(t.get('zone_type') for t in trades)):
      for st in sorted(set(t.get('market_state') for t in trades)):
       for cf in sorted(set(t.get('conf_type') for t in trades)):
        for rb in sorted(set(retr_bin(t) for t in trades)):
         g=[t for t in trades if t.get('zone_type')==z and t.get('market_state')==st and t.get('conf_type')==cf and retr_bin(t)==rb]
         if len(g)>=min_n:
          m=metrics(g); combos.append({'filter':f'{z}|{st}|{cf}|{rb}','metrics':m})
    combos.sort(key=lambda x:(x['metrics'].get('avg_pnl',-999), x['metrics'].get('wr',0), x['metrics'].get('n',0)), reverse=True)
    return combos[:40]

def production_profiles(trades):
    profiles = {
        'P0_current_fixed': lambda t: True,
        'P1_FVG_only': lambda t: t.get('zone_type') == 'FVG_Bull',
        'P2_FVG_retr_lt40': lambda t: t.get('zone_type') == 'FVG_Bull' and f(t.get('retrace_depth_pct')) < 40,
        'P3_FVG_risk_lt35': lambda t: t.get('zone_type') == 'FVG_Bull' and f(t.get('risk_pct') or t.get('v25_sl_pct')) < 3.5,
        'P4_FVG_risk_lt35_retr_lt40': lambda t: t.get('zone_type') == 'FVG_Bull' and f(t.get('risk_pct') or t.get('v25_sl_pct')) < 3.5 and f(t.get('retrace_depth_pct')) < 40,
        'P5_LOW_VOL_all': lambda t: t.get('market_state') == 'LOW_VOL',
        'P6_FVG_LOW_VOL': lambda t: t.get('zone_type') == 'FVG_Bull' and t.get('market_state') == 'LOW_VOL',
        'P7_FVG_LOW_VOL_CHOCH_retr_lt60': lambda t: t.get('zone_type') == 'FVG_Bull' and t.get('market_state') == 'LOW_VOL' and t.get('conf_type') == 'CHOCH_Bull' and f(t.get('retrace_depth_pct')) < 60,
        'P8_FVG_TRENDUP_BOS_retr_lt60_risk_lt35': lambda t: t.get('zone_type') == 'FVG_Bull' and t.get('market_state') == 'TREND_UP' and t.get('conf_type') == 'BOS_Bull' and f(t.get('retrace_depth_pct')) < 60 and f(t.get('risk_pct') or t.get('v25_sl_pct')) < 3.5,
        'P9_FVG_LOWVOL_OR_TRENDUPBOS_retr_lt60_risk_lt35': lambda t: t.get('zone_type') == 'FVG_Bull' and f(t.get('retrace_depth_pct')) < 60 and f(t.get('risk_pct') or t.get('v25_sl_pct')) < 3.5 and (t.get('market_state') == 'LOW_VOL' or (t.get('market_state') == 'TREND_UP' and t.get('conf_type') == 'BOS_Bull')),
    }
    out = {}
    for name, fn in profiles.items():
        g = [t for t in trades if fn(t)]
        out[name] = metrics(g)
    return out

def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    fixed=[]; base=[]
    print(f"V66 repaired replay {len(files)} stocks {datetime.now():%H:%M:%S}", flush=True)
    for i,kf in enumerate(files,1):
        base.extend(replay_file(kf, baseline=True))
        fixed.extend(replay_file(kf, baseline=False))
        if i%500==0: print(f"  {i}/{len(files)} base={len(base)} fixed={len(fixed)}", flush=True)
    report={'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(files),'baseline':metrics(base),'fixed':metrics(fixed),'delta':{},'production_profiles':production_profiles(fixed),'fixed_buckets':{'zone_type':bucket(fixed,'zone_type'),'market_state':bucket(fixed,'market_state'),'sweep_tag':bucket(fixed,'sweep_tag'),'exit_reason':bucket(fixed,'exit_reason'),'conf_type':bucket(fixed,'conf_type'),'retrace_bin':bucket_fn(fixed,retr_bin),'sl_bin':bucket_fn(fixed,sl_bin),'score_bin':bucket_fn(fixed,score_bin)},'top_combos':top_combos(fixed),'baseline_counts':dict(Counter(t.get('zone_type') for t in base)),'fixed_counts':dict(Counter(t.get('zone_type') for t in fixed)),'samples':fixed[:20]}
    for k in ('n','wr','sl_rate','avg_pnl','cum'):
        if k in report['fixed'] and k in report['baseline']:
            report['delta'][k]=round(report['fixed'][k]-report['baseline'][k],4)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2)[:6000])
    print(f"Saved: {OUT}")

if __name__=='__main__': main()
