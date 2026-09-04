#!/usr/bin/env python3
"""V73 structural environment gate search.

Goal: test the user's core hypothesis that single-stock POI is insufficient;
Demand Zones only work when the broader SMC environment permits demand to hold.

This does NOT use generic MA/RSI.  It builds non-leaking structural breadth from
confirmed HH/HL/LH/LL states across the A-share universe, then filters V71's
cleaner smart-money-position trades by environment and per-stock trend context.
"""
from __future__ import annotations
import json, importlib.util
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

BASE = Path('/root/.hermes/scripts/v25/phase2_strict_ld_backtest.py')
spec = importlib.util.spec_from_file_location('ld', BASE)
ld = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ld)

KLINE_DIR = Path('/root/.hermes/kline_cache')
V71_TRADES = Path('/root/.hermes/smc_opt_v71_smart_money_position/v71_trades.json')
OUT_DIR = Path('/root/.hermes/smc_opt_v73_structural_env')
OUT_DIR.mkdir(parents=True, exist_ok=True)


def f(x, default=0.0):
    try:
        return float(x or 0)
    except Exception:
        return default


def d(b):
    return str(b.get('t') or b.get('date') or '')[:8]


def load_ks(kf: Path):
    try:
        ks = json.loads(kf.read_text())
    except Exception:
        return []
    for b in ks:
        for k in ('o','h','l','c','v'):
            if k in b:
                b[k] = f(b[k])
    return ks


def symbol_from_file(kf: Path) -> str:
    sym = kf.stem.replace('_daily_750','')
    return sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')


def confirmed_swing_series(ks):
    """Non-leaking daily structural state using only swings already confirmed by idx."""
    highs=[]; lows=[]; hp=lp=0
    high_events=[]; low_events=[]
    for i in range(3, len(ks)-3):
        if ld.is_swing_high(ks,i,3,3):
            high_events.append({'idx':i,'confirm':i+3,'price':f(ks[i].get('h'))})
        if ld.is_swing_low(ks,i,3,3):
            low_events.append({'idx':i,'confirm':i+3,'price':f(ks[i].get('l'))})
    out={}
    last_state='UNKNOWN'; last_event='NONE'
    last_high_break=-999; last_low_break=-999
    for i,b in enumerate(ks):
        while hp < len(high_events) and high_events[hp]['confirm'] <= i:
            highs.append(high_events[hp]); hp += 1
        while lp < len(low_events) and low_events[lp]['confirm'] <= i:
            lows.append(low_events[lp]); lp += 1
        state='UNKNOWN'; pattern='NA'
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1]['price'] > highs[-2]['price']
            hl = lows[-1]['price'] > lows[-2]['price']
            lh = highs[-1]['price'] < highs[-2]['price']
            ll = lows[-1]['price'] < lows[-2]['price']
            if hh and hl:
                state='UP_CONTINUATION'; pattern='HH_HL'
            elif lh and ll:
                state='DOWN_CONTINUATION'; pattern='LH_LL'
            elif hh and ll:
                state='EXPANSION_RANGE'; pattern='HH_LL'
            elif lh and hl:
                state='COMPRESSION_RANGE'; pattern='LH_HL'
            else:
                state='RANGE'; pattern='MIXED'
            close=f(b.get('c'))
            # CHOCH/BOS event inferred from confirmed structure levels; no future bars.
            if highs and close > highs[-1]['price'] * 1.001 and i - last_high_break >= 3:
                last_event = 'BULL_BOS' if last_state in ('UP_CONTINUATION','COMPRESSION_RANGE') else 'BULL_CHOCH'
                last_high_break = i
                state = 'BULL_TRANSITION' if last_event == 'BULL_CHOCH' else state
            elif lows and close < lows[-1]['price'] / 1.001 and i - last_low_break >= 3:
                last_event = 'BEAR_BOS' if last_state == 'DOWN_CONTINUATION' else 'BEAR_CHOCH'
                last_low_break = i
                state = 'BEAR_TRANSITION' if last_event == 'BEAR_CHOCH' else state
        out[d(b)] = {'state':state,'pattern':pattern,'event':last_event,'bar':i}
        last_state = state if state != 'UNKNOWN' else last_state
    return out


def build_environment(files):
    by_date=defaultdict(Counter)
    stock_state={}
    print(f'Building structural breadth for {len(files)} stocks {datetime.now():%H:%M:%S}', flush=True)
    for n,kf in enumerate(files,1):
        sym=symbol_from_file(kf)
        ks=load_ks(kf)
        if len(ks)<180:
            continue
        states=confirmed_swing_series(ks)
        stock_state[sym]=states
        for dt,st in states.items():
            by_date[dt][st['state']] += 1
            by_date[dt]['TOTAL'] += 1
        if n % 500 == 0:
            print(f'  env {n}/{len(files)}', flush=True)
    env={}
    prev_bull=[]
    for dt in sorted(by_date):
        c=by_date[dt]; total=max(c['TOTAL'],1)
        bull=(c['UP_CONTINUATION']+c['BULL_TRANSITION'])/total
        bear=(c['DOWN_CONTINUATION']+c['BEAR_TRANSITION'])/total
        rng=(c['COMPRESSION_RANGE']+c['EXPANSION_RANGE']+c['RANGE'])/total
        prev_bull.append((dt,bull))
        base=None
        if len(prev_bull)>20:
            base=prev_bull[-21][1]
        slope20=(bull-base) if base is not None else 0.0
        env[dt]={
            'total':total,
            'bull_breadth':round(bull,4),
            'bear_breadth':round(bear,4),
            'range_breadth':round(rng,4),
            'bull_slope20':round(slope20,4),
            'state':'BULL_ENV' if bull>=0.42 and bear<=0.36 else ('RECOVERY_ENV' if bull>=0.34 and slope20>=0.035 and bear<=0.42 else ('BEAR_ENV' if bear>=0.42 and bull<=0.34 else 'MIXED_ENV')),
        }
    return env, stock_state


def metrics(ts):
    if not ts:
        return {'n':0,'wr':0,'sl_rate':0,'tp_rate':0,'avg_pnl':0,'cum':0,'avg_win':0,'avg_loss':0,'payoff':0,'avg_hold':0}
    wins=[t for t in ts if f(t.get('pnl_pct'))>0]
    losses=[t for t in ts if f(t.get('pnl_pct'))<=0]
    sl=[t for t in ts if t.get('exit_reason')=='SL_HIT']
    tp=[t for t in ts if t.get('exit_reason')=='TP1_HIT']
    avg=sum(f(t.get('pnl_pct')) for t in ts)/len(ts)
    aw=sum(f(t.get('pnl_pct')) for t in wins)/len(wins) if wins else 0
    al=sum(f(t.get('pnl_pct')) for t in losses)/len(losses) if losses else 0
    return {'n':len(ts),'wr':round(len(wins)/len(ts)*100,2),'sl_rate':round(len(sl)/len(ts)*100,2),'tp_rate':round(len(tp)/len(ts)*100,2),'avg_pnl':round(avg,4),'cum':round(sum(f(t.get('pnl_pct')) for t in ts),2),'avg_win':round(aw,4),'avg_loss':round(al,4),'payoff':round(aw/abs(al),3) if al else 0,'avg_hold':round(sum(f(t.get('hold_bars')) for t in ts)/len(ts),2)}


def bucket(ts, key):
    g=defaultdict(list)
    for t in ts:
        g[key(t)].append(t)
    return {str(k):metrics(v) for k,v in sorted(g.items(), key=lambda kv: str(kv[0]))}


def annotate_trades(trades, env, stock_state):
    out=[]
    for t in trades:
        nt=dict(t)
        ed=nt.get('entry_date') or nt.get('pick_date')
        sym=nt.get('symbol')
        e=env.get(ed, {})
        s=stock_state.get(sym, {}).get(ed, {})
        nt['market_env']=e.get('state','UNKNOWN_ENV')
        nt['market_bull_breadth']=e.get('bull_breadth',0)
        nt['market_bear_breadth']=e.get('bear_breadth',0)
        nt['market_range_breadth']=e.get('range_breadth',0)
        nt['market_bull_slope20']=e.get('bull_slope20',0)
        nt['stock_trend_state']=s.get('state','UNKNOWN')
        nt['stock_structure_pattern']=s.get('pattern','NA')
        nt['stock_last_event']=s.get('event','NONE')
        # Two SMC story types requested by the user.
        if nt.get('sequence','').startswith('SSL_SWEEP') and nt.get('stock_last_event') in ('BULL_CHOCH','BULL_BOS'):
            nt['setup_family']='REVERSAL_LIQ_CHOCH_TO_POI' if nt.get('stock_last_event')=='BULL_CHOCH' else 'CONTINUATION_BOS_PULLBACK_TO_POI'
        elif nt.get('stock_trend_state') in ('UP_CONTINUATION','BULL_TRANSITION'):
            nt['setup_family']='CONTINUATION_BOS_PULLBACK_TO_POI'
        else:
            nt['setup_family']='REVERSAL_LIQ_CHOCH_TO_POI'
        out.append(nt)
    return out


def passes_gate(t, gate):
    mb=f(t.get('market_bull_breadth')); br=f(t.get('market_bear_breadth')); slp=f(t.get('market_bull_slope20'))
    st=t.get('stock_trend_state')
    ev=t.get('market_env')
    last=t.get('stock_last_event')
    rt=t.get('reaction_type')
    risk=f(t.get('risk_pct'))
    pd=t.get('pd_zone')
    if gate == 'env_state_only':
        return ev in ('BULL_ENV','RECOVERY_ENV')
    if gate == 'env_breadth_strict':
        return mb >= 0.42 and br <= 0.36
    if gate == 'env_recovery_or_bull':
        return (mb >= 0.42 and br <= 0.38) or (mb >= 0.34 and slp >= 0.035 and br <= 0.42)
    if gate == 'env_plus_stock_trend':
        return ((mb >= 0.42 and br <= 0.38) or (mb >= 0.34 and slp >= 0.035 and br <= 0.42)) and st in ('UP_CONTINUATION','BULL_TRANSITION','COMPRESSION_RANGE')
    if gate == 'env_plus_event':
        return ((mb >= 0.42 and br <= 0.38) or (mb >= 0.34 and slp >= 0.035 and br <= 0.42)) and last in ('BULL_CHOCH','BULL_BOS')
    if gate == 'full_context_quality':
        return ((mb >= 0.42 and br <= 0.38) or (mb >= 0.34 and slp >= 0.035 and br <= 0.42)) and st in ('UP_CONTINUATION','BULL_TRANSITION','COMPRESSION_RANGE') and rt == 'RECLAIM_HIGH' and 2.0 <= risk <= 6.0 and pd in ('DISCOUNT','OTE_DISCOUNT','STRUCTURE_LOW_RISK')
    return False


def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    env, stock_state = build_environment(files)
    trades=json.loads(V71_TRADES.read_text())
    annotated=annotate_trades(trades, env, stock_state)
    gates=['env_state_only','env_breadth_strict','env_recovery_or_bull','env_plus_stock_trend','env_plus_event','full_context_quality']
    gate_rows={g:metrics([t for t in annotated if passes_gate(t,g)]) for g in gates}
    by_gate={g:[t for t in annotated if passes_gate(t,g)] for g in gates}
    best=max(gates, key=lambda g:(gate_rows[g]['avg_pnl'], gate_rows[g]['wr'], gate_rows[g]['n']))
    selected=by_gate[best]
    report={
        'generated_at':datetime.now().isoformat(timespec='seconds'),
        'engine':'V73_STRUCTURAL_ENV_GATE_SEARCH',
        'hypothesis':'Demand Zone validity requires broad structural environment + per-stock trend context, not POI label changes.',
        'base_v71':metrics(annotated),
        'gate_metrics':gate_rows,
        'selected_gate':best,
        'selected_metrics':metrics(selected),
        'selected_buckets':{
            'year':bucket(selected, lambda t:t.get('entry_date','')[:4]),
            'market_env':bucket(selected, lambda t:t.get('market_env')),
            'stock_trend_state':bucket(selected, lambda t:t.get('stock_trend_state')),
            'stock_last_event':bucket(selected, lambda t:t.get('stock_last_event')),
            'setup_family':bucket(selected, lambda t:t.get('setup_family')),
            'reaction_type':bucket(selected, lambda t:t.get('reaction_type')),
            'pd_zone':bucket(selected, lambda t:t.get('pd_zone')),
            'risk_bin':bucket(selected, lambda t:'a_<2' if f(t.get('risk_pct'))<2 else ('b_2_4' if f(t.get('risk_pct'))<4 else ('c_4_6' if f(t.get('risk_pct'))<6 else 'd_6_8'))),
            'exit_reason':bucket(selected, lambda t:t.get('exit_reason')),
        },
        'env_sample':{k:env[k] for k in sorted(env)[-10:]},
        'samples':selected[:50],
    }
    (OUT_DIR/'v73_annotated_trades.json').write_text(json.dumps(annotated, ensure_ascii=False, indent=2))
    (OUT_DIR/'v73_selected_trades.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2))
    (OUT_DIR/'v73_env_by_date.json').write_text(json.dumps(env, ensure_ascii=False, indent=2))
    (OUT_DIR/'v73_gate_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({
        'base_v71':report['base_v71'],
        'gate_metrics':report['gate_metrics'],
        'selected_gate':best,
        'selected_metrics':report['selected_metrics'],
        'selected_buckets':report['selected_buckets'],
        'files':{
            'report':str(OUT_DIR/'v73_gate_report.json'),
            'selected':str(OUT_DIR/'v73_selected_trades.json'),
            'annotated':str(OUT_DIR/'v73_annotated_trades.json'),
            'env':str(OUT_DIR/'v73_env_by_date.json'),
        }
    }, ensure_ascii=False, indent=2)[:20000])

if __name__ == '__main__':
    main()
