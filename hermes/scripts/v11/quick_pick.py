#!/usr/bin/env python3
"""快速选股扫描 (跳过刷新,用现有数据)"""
import json,sys
from pathlib import Path
sys.path.insert(0,'/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v21')
DNA_FILE=OUT/'stock_dna_v11.json'

dna={}
if DNA_FILE.exists():
    with open(DNA_FILE) as f:
        dna=json.load(f).get('dna',{})

picks=[]
stats={'total':0,'ob':0,'fvg':0,'other':0}

for fp in sorted(KLINE.glob('*_daily_300.json')):
    name=fp.stem.replace('_daily_300','')
    parts=name.rsplit('_',1)
    if len(parts)!=2:continue
    sym=f'{parts[0]}.{parts[1]}'
    try:
        daily=json.loads(fp.read_bytes())
        n=len(daily)
        if n<50:continue
    except:continue
    
    last=daily[-1]
    ld=str(last.get('t',last.get('date','')))[:10]
    # Skip if data older than May 10
    try:
        if int(ld.replace('-',''))<20260401:continue
    except:continue
    
    try:
        sigs,st,_,_=detect_all_signals_v20(daily)
    except:continue
    
    # T+1: yesterday's signal = today's entry
    # Check last 2 bars: yesterday (n-2) and today (n-1)
    recent=[s for s in sigs if s.idx>=n-2]
    if not recent:continue
    stats['total']+=1
    
    sd=dna.get(sym,{})
    for s in recent:
        sl=s.lower*0.995 if s.lower>0 else last['c']*0.97
        tp=last['c']*1.03
        entry={
            'symbol':sym,
            'signal':s.type,
            'signal_date':str(daily[s.idx].get('t',daily[s.idx].get('date','')))[:10],
            'signal_price':round(s.price,2),
            'zone_low':round(s.lower,2) if s.lower>0 else 0,
            'zone_high':round(s.upper,2) if s.upper>0 else 0,
            'last_close':round(last['c'],2),
            'last_date':ld,
            'suggested_buy':round(last['c'],2),
            'sl_price':round(sl,2),
            'tp_price':round(tp,2),
            'hist_wr':sd.get('v11_wr',0),
            'hist_pnl':sd.get('v11_avg_pnl',0),
            'best_pat':sd.get('best_pattern','?'),
            'hist_trades':sd.get('v11_trades',0),
            'trend':sd.get('trend','?'),
            'ob_wr':sd.get('ob_wr',0),
            'fvg_wr':sd.get('fvg_wr',0),
        }
        if s.type=='OB_Bull':stats['ob']+=1
        elif s.type=='FVG_Bull':stats['fvg']+=1
        else:stats['other']+=1
        picks.append(entry)

picks.sort(key=lambda x:(x['signal']!='OB_Bull',-x['hist_wr']))
ob=[p for p in picks if p['signal']=='OB_Bull']
fvg=[p for p in picks if p['signal']=='FVG_Bull']

print(f"扫描: {len(list(KLINE.glob('*_daily_300.json')))}只")
print(f"有信号: {stats['total']} | OB:{stats['ob']} | FVG:{stats['fvg']} | Other:{stats['other']}")
print(f"\n{'='*95}")
print(f"  OB_Bull 选股清单 (全部{len(ob)}只)")
print(f"  {'代码':<12s} {'信号日':<12s} {'信号价':>7s} {'现价':>7s} {'SL':>7s} {'TP':>7s} {'histWR':>7s} {'OBwr':>6s} {'交易':>5s} {'趋势':>5s}")
print(f"  {'-'*90}")
for p in ob:
    print(f"  {p['symbol']:<12s} {p['signal_date']:<12s} {p['signal_price']:>7.2f} {p['last_close']:>7.2f} {p['sl_price']:>7.2f} {p['tp_price']:>7.2f} {p['hist_wr']:>6.1%} {p['ob_wr']:>5.1%} {p['hist_trades']:>5d} {p['trend']:>5s}")

print(f"\n{'='*95}")
print(f"  FVG_Bull + Other 选股清单 ({len(fvg)+stats['other']}只, 低质量信号保留)")
print(f"  {'代码':<12s} {'信号':<14s} {'信号价':>7s} {'现价':>7s} {'SL':>7s} {'TP':>7s} {'histWR':>7s}")
print(f"  {'-'*80}")
for p in fvg[:50]:
    print(f"  {p['symbol']:<12s} {p['signal']:<14s} {p['signal_price']:>7.2f} {p['last_close']:>7.2f} {p['sl_price']:>7.2f} {p['tp_price']:>7.2f} {p['hist_wr']:>6.1%}")
# Other signals
other_sigs=[p for p in picks if p['signal'] not in ('OB_Bull','FVG_Bull')]
for p in other_sigs[:30]:
    print(f"  {p['symbol']:<12s} {p['signal']:<14s} {p['signal_price']:>7.2f} {p['last_close']:>7.2f} {p['sl_price']:>7.2f} {p['tp_price']:>7.2f} {p['hist_wr']:>6.1%}")

json.dump({'time':'2026-05-14 11:00','ob':ob,'fvg':fvg,'other':other_sigs,'all':picks},
          open(OUT/'today_picks.json','w'),ensure_ascii=False)
print(f"\nSaved: {OUT/'today_picks.json'} ({len(picks)} picks)")
