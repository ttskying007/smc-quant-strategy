#!/usr/bin/env python3
"""Phase2 WR optimizer experiments.

Purpose: separate true time-ordered Phase2 variants from inflated/legacy reports.
Runs full-market V22 signal replay with strict temporal order:
  zone -> structure confirm -> executable entry -> T+1 exit.
"""
import json, sys, itertools
from pathlib import Path
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, '/root/.hermes/scripts')
sys.path.insert(0, '/root/.hermes/scripts/v11')
from signals_v22 import detect_all_signals_v22

KLINE_DIR = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v25/phase2_wr_optimizer.json')
N = int(sys.argv[1]) if len(sys.argv) > 1 else 0
MAX_HOLD = 60

def f(x):
    try: return float(x or 0)
    except Exception: return 0.0

def d(b): return str(b.get('t') or b.get('date') or '')[:8]

def atr(klines, idx, n=14):
    trs=[]
    for i in range(max(1, idx-n+1), idx+1):
        h,l,pc=f(klines[i].get('h')),f(klines[i].get('l')),f(klines[i-1].get('c'))
        trs.append(max(h-l, abs(h-pc), abs(l-pc)))
    return sum(trs)/len(trs) if trs else 0.0

def ma(klines, idx, p=20):
    vals=[f(klines[i].get('c')) for i in range(max(0, idx-p+1), idx+1)]
    return sum(vals)/len(vals) if vals else 0.0

def state(klines, idx):
    ep=f(klines[idx].get('c'))
    ap=atr(klines,idx)/ep*100 if ep else 0
    m20=ma(klines,idx); m20p=ma(klines,max(14,idx-10))
    slope=(m20-m20p)/m20p*100 if m20p else 0
    if ap>5: return 'HIGH_VOL'
    if ap<1.5: return 'LOW_VOL'
    if slope>1: return 'TREND_UP'
    if slope<-1: return 'TREND_DOWN'
    return 'RANGE'

def simulate(klines, entry_idx, ep, sl, tp, max_hold=MAX_HOLD):
    if not (ep and sl and tp) or ep <= sl or tp <= ep: return None
    end=min(len(klines), entry_idx+max_hold+1)
    for j in range(entry_idx+1,end):  # T+1 only
        lo,hi=f(klines[j].get('l')),f(klines[j].get('h'))
        if lo<=sl:
            return {'exit_date':d(klines[j]), 'exit_reason':'SL_HIT', 'exit_price':round(sl,4), 'hold_bars':j-entry_idx, 'pnl_pct':round((sl/ep-1)*100,4)}
        if hi>=tp:
            return {'exit_date':d(klines[j]), 'exit_reason':'TP_HIT', 'exit_price':round(tp,4), 'hold_bars':j-entry_idx, 'pnl_pct':round((tp/ep-1)*100,4)}
    if entry_idx+max_hold < len(klines):
        px=f(klines[entry_idx+max_hold].get('c'))
        return {'exit_date':d(klines[entry_idx+max_hold]), 'exit_reason':'TIME_STOP', 'exit_price':round(px,4), 'hold_bars':max_hold, 'pnl_pct':round((px/ep-1)*100,4)}
    return None

def sig_bar(s): return int(getattr(s,'idx', getattr(s,'bar', 0)) or 0)
def sig_type(s): return getattr(s,'type','')
def sig_lower(s): return f(getattr(s,'lower',0) or getattr(s,'price',0))
def sig_upper(s): return f(getattr(s,'upper',0) or getattr(s,'price',0))
def sig_meta(s): return getattr(s,'metadata',{}) or getattr(s,'meta',{}) or {}

def is_safe_lux_ob(s):
    # V22 also has SMC2026 OB with known future-swing risk; LuxAlgo OB carries break_bar.
    return sig_type(s)=='OB_Bull' and 'break_bar' in sig_meta(s)

def make_trade(symbol, klines, z, c, entry_idx, mode, rr=1.5, sl_mult=0.96):
    zl,zh=z['low'],z['high']
    b=klines[entry_idx]
    ep=f(b.get('o')) if mode.endswith('_next_open') else f(b.get('c'))
    if ep<=0 or zl<=0 or zh<=zl: return None
    risk_state=state(klines, entry_idx)
    a=atr(klines, entry_idx)
    # OB retrace: structural SL under POI; FVG immediate: ATR/zone hybrid SL.
    if z['type']=='OB_Bull':
        sl=min(zl*sl_mult, zl-a*0.25)
    else:
        sl=min(zl*0.985, ep-a*0.8)
    risk_pct=(ep/sl-1)*100 if sl else 999
    tp=ep+(ep-sl)*rr
    res=simulate(klines, entry_idx, ep, sl, tp)
    if not res: return None
    return {
        'symbol':symbol,'zone_type':z['type'],'conf_type':c['type'],'mode':mode,
        'entry_date':d(klines[entry_idx]),'zone_date':d(klines[z['bar']]),'confirm_date':d(klines[c['bar']]),
        'entry_idx':entry_idx,'zone_bar':z['bar'],'confirm_bar':c['bar'],
        'entry_price':round(ep,4),'zone_low':round(zl,4),'zone_high':round(zh,4),'sl':round(sl,4),'tp':round(tp,4),
        'risk_pct':round(risk_pct,3),'market_state':risk_state,
        'retrace_pct':round(max(0,min(100,(zh-f(b.get('l')))/max(zh-zl,1e-9)*100)),2),
        **res
    }

def trades_for_file(kf):
    sym=kf.stem.replace('_daily_750','')
    symbol=sym.replace('_SH','.SH').replace('_SZ','.SZ').replace('_BJ','.BJ')
    try: klines=json.loads(kf.read_text())
    except Exception: return []
    if len(klines)<150: return []
    for b in klines:
        for k in ('o','h','l','c','v'):
            if k in b: b[k]=f(b[k])
    try: sigs, summary, swings, sig_dict = detect_all_signals_v22(klines)
    except Exception: return []
    confirms=[{'type':sig_type(s),'bar':sig_bar(s)} for s in sigs if sig_type(s) in ('BOS_Bull','CHOCH_Bull')]
    zones=[]
    for s in sigs:
        st=sig_type(s); bar=sig_bar(s)
        if bar<30 or bar>=len(klines)-MAX_HOLD-10: continue
        if st=='FVG_Bull':
            lo,hi=sig_lower(s),sig_upper(s)
            if hi>lo>0: zones.append({'type':st,'bar':bar,'low':lo,'high':hi})
        elif is_safe_lux_ob(s):
            lo,hi=sig_lower(s),sig_upper(s)
            if hi>lo>0: zones.append({'type':st,'bar':bar,'low':lo,'high':hi})
    out=[]; used=set()
    for z in zones:
        cands=[c for c in confirms if z['bar'] < c['bar'] <= z['bar']+30]
        if not cands: continue
        c=cands[0]
        # 1) FVG immediate after confirm: no retrace waiting.
        if z['type']=='FVG_Bull':
            ei=c['bar']+1
            if ei < len(klines)-MAX_HOLD and f(klines[ei].get('o')) <= z['high']*1.03:
                t=make_trade(symbol,klines,z,c,ei,'FVG_immediate_next_open',rr=1.5)
                if t: out.append(t)
        # 2) OB true Phase2 retrace after confirm: wait for touch + reclaim confirmation.
        if z['type']=='OB_Bull':
            for wait in range(c['bar']+1, min(c['bar']+8, len(klines)-MAX_HOLD)):
                b=klines[wait]; lo,hi,op,cl=f(b.get('l')),f(b.get('h')),f(b.get('o')),f(b.get('c'))
                touches = lo <= z['high'] and hi >= z['low']
                reclaim = cl >= z['low'] and cl >= op and cl <= z['high']*1.03
                not_broken = lo >= z['low']*0.985
                if touches and reclaim and not_broken:
                    t=make_trade(symbol,klines,z,c,wait,'OB_retrace_reclaim_close',rr=1.5,sl_mult=0.96)
                    if t: out.append(t)
                    break
    return out

def metrics(ts):
    if not ts: return {'n':0}
    wins=[t for t in ts if t['pnl_pct']>0]; sl=[t for t in ts if t['exit_reason']=='SL_HIT']; tp=[t for t in ts if t['exit_reason']=='TP_HIT']
    avg=sum(t['pnl_pct'] for t in ts)/len(ts)
    return {'n':len(ts),'wr':round(len(wins)/len(ts)*100,2),'sl_rate':round(len(sl)/len(ts)*100,2),'tp_rate':round(len(tp)/len(ts)*100,2),'avg_pnl':round(avg,4),'cum':round(sum(t['pnl_pct'] for t in ts),2),'avg_hold':round(sum(t['hold_bars'] for t in ts)/len(ts),2)}

def profile_report(trades):
    prof={}
    filters={
        'ALL':lambda t: True,
        'FVG_immediate':lambda t:t['mode'].startswith('FVG'),
        'OB_retrace':lambda t:t['mode'].startswith('OB'),
        'OB_LOW_VOL':lambda t:t['mode'].startswith('OB') and t['market_state']=='LOW_VOL',
        'OB_NOT_HIGH_VOL':lambda t:t['mode'].startswith('OB') and t['market_state']!='HIGH_VOL',
        'OB_risk_2_8':lambda t:t['mode'].startswith('OB') and 2<=t['risk_pct']<=8,
        'OB_retr_lt60':lambda t:t['mode'].startswith('OB') and t['retrace_pct']<60,
        'OB_retr_lt60_risk_2_8':lambda t:t['mode'].startswith('OB') and t['retrace_pct']<60 and 2<=t['risk_pct']<=8,
        'FVG_TREND_UP_or_LOW_VOL':lambda t:t['mode'].startswith('FVG') and t['market_state'] in ('TREND_UP','LOW_VOL'),
        'FVG_risk_2_6':lambda t:t['mode'].startswith('FVG') and 2<=t['risk_pct']<=6,
    }
    for name,fn in filters.items(): prof[name]=metrics([t for t in trades if fn(t)])
    # combo buckets
    buckets=defaultdict(list)
    for t in trades:
        rb='r<30' if t['retrace_pct']<30 else ('r30_60' if t['retrace_pct']<60 else 'r60+')
        sk=f"{t['zone_type']}|{t['conf_type']}|{t['market_state']}|{rb}"
        buckets[sk].append(t)
    combos=[{'filter':k,'metrics':metrics(v)} for k,v in buckets.items() if len(v)>=30]
    combos.sort(key=lambda x:(x['metrics'].get('wr',0), x['metrics'].get('avg_pnl',-999), x['metrics'].get('n',0)), reverse=True)
    return prof, combos[:50]

def main():
    files=sorted(KLINE_DIR.glob('*_daily_750.json'))
    if N>0: files=files[:N]
    trades=[]
    print(f"Phase2 WR optimizer {len(files)} stocks {datetime.now():%H:%M:%S}", flush=True)
    for i,kf in enumerate(files,1):
        trades.extend(trades_for_file(kf))
        if i%500==0: print(f"  {i}/{len(files)} trades={len(trades)}", flush=True)
    prof, combos=profile_report(trades)
    report={'generated_at':datetime.now().isoformat(timespec='seconds'),'n_stocks':len(files),'all':metrics(trades),'profiles':prof,'top_combos':combos,'samples':trades[:20]}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({k:report[k] for k in ('generated_at','n_stocks','all','profiles','top_combos')},ensure_ascii=False,indent=2)[:8000])
    print('Saved:',OUT)

if __name__=='__main__': main()
