#!/usr/bin/env python3
"""腾讯API刷新日线 + 全量扫描选股"""
import json, time, subprocess
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
sys.path.insert(0,'/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE=Path('/root/.hermes/kline_cache')
OUT=Path('/root/.hermes/smc_opt_v21')
DNA_FILE=OUT/'stock_dna_v11.json'
dna={}
if DNA_FILE.exists():
    with open(DNA_FILE) as f: dna=json.load(f).get('dna',{})

def refresh_one(sym):
    """Download daily from Tencent"""
    name=sym.replace('.','_')
    code,mkt=sym.split('.')
    prefix='sz' if mkt=='SZ' else 'sh'
    out=KLINE/f'{name}_daily_300.json'
    try:
        r=subprocess.run(['curl','-sSL','--max-time','8',
            f'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,300,qfq'],
            capture_output=True,text=True,timeout=12)
        if r.returncode==0:
            d=json.loads(r.stdout)
            data=d.get('data',{}).get(f'{prefix}{code}',{})
            bars=data.get('qfqday',data.get('day',[]))
            if bars and len(bars)>=50:
                result=[]
                for b in bars:
                    result.append({'t':b[0].replace('-',''),'o':float(b[1]),'c':float(b[2]),'h':float(b[3]),'l':float(b[4]),'v':float(b[5])*100 if len(b)>5 else 0})
                out.write_text(json.dumps(result))
                return len(result)
    except:pass
    return 0

print("刷新日线 (20并发, 腾讯API)...")
daily_files=sorted(KLINE.glob('*_daily_300.json'))
syms=[]
for f in daily_files:
    n=f.stem.replace('_daily_300','')
    p=n.rsplit('_',1)
    if len(p)==2:syms.append(f'{p[0]}.{p[1]}')

t0=time.time();refreshed=0
with ThreadPoolExecutor(max_workers=20) as ex:
    futures={ex.submit(refresh_one,s):s for s in syms}
    for f in as_completed(futures):
        refreshed+=1
        if refreshed%500==0:print(f"  [{refreshed}/{len(syms)}] {time.time()-t0:.0f}s")

print(f"刷新完成: {refreshed}只 {time.time()-t0:.0f}s")

# ═══ Scan ═══
print("\n全量扫描信号...")
picks=[]
for fp in daily_files:
    name=fp.stem.replace('_daily_300','')
    parts=name.rsplit('_',1)
    if len(parts)!=2:continue
    sym=f'{parts[0]}.{parts[1]}'
    try:
        daily=json.loads(fp.read_bytes());n=len(daily)
        if n<50:continue
    except:continue
    last=daily[-1];ld=str(last.get('t',last.get('date','')))[:10]
    try:
        if int(ld.replace('-',''))<20260512:continue
    except:continue
    try:sigs,st,_,_=detect_all_signals_v20(daily)
    except:continue
    recent=[s for s in sigs if s.idx>=n-3]
    if not recent:continue
    sd=dna.get(sym,{})
    for s in recent:
        sl=s.lower*0.995 if s.lower>0 else last['c']*0.97
        picks.append({
            'symbol':sym,'signal':s.type,
            'signal_date':str(daily[s.idx].get('t',daily[s.idx].get('date','')))[:10],
            'signal_price':round(s.price,2),
            'zone_low':round(s.lower,2) if s.lower>0 else 0,
            'zone_high':round(s.upper,2) if s.upper>0 else 0,
            'last_close':round(last['c'],2),'last_date':ld,
            'suggested_buy':round(last['c'],2),
            'sl_price':round(sl,2),'tp_price':round(last['c']*1.03,2),
            'hist_wr':sd.get('v11_wr',0),'hist_pnl':sd.get('v11_avg_pnl',0),
            'best_pat':sd.get('best_pattern','?'),'hist_trades':sd.get('v11_trades',0),
            'trend':sd.get('trend','?'),'ob_wr':sd.get('ob_wr',0),'fvg_wr':sd.get('fvg_wr',0),
        })

picks.sort(key=lambda x:(x['signal']!='OB_Bull',-x['hist_wr']))
ob=[p for p in picks if p['signal']=='OB_Bull']
fvg=[p for p in picks if p['signal']=='FVG_Bull']
other=[p for p in picks if p['signal'] not in('OB_Bull','FVG_Bull')]

print(f"\n{'='*100}")
print(f"  SMC 今日选股 2026-05-14 11:00")
print(f"  扫描: {len(syms)}只 | 有信号: {len(set(p['symbol'] for p in picks))}只")
print(f"  OB_Bull:{len(ob)} | FVG:{len(fvg)} | Other:{len(other)}")
print(f"{'='*100}")

print(f"\n  🟢 OB_Bull 选股 (全部{len(ob)}只) - 历史WR=94.2%")
print(f"  {'代码':<12s} {'信号日':<12s} {'信号价':>8s} {'现价':>8s} {'建议买入':>9s} {'SL':>8s} {'TP':>8s} {'histWR':>7s} {'OBwr':>6s} {'交易':>5s}")
print(f"  {'-'*105}")
for p in ob:
    print(f"  {p['symbol']:<12s} {p['signal_date']:<12s} {p['signal_price']:>8.2f} {p['last_close']:>8.2f} {p['suggested_buy']:>9.2f} {p['sl_price']:>8.2f} {p['tp_price']:>8.2f} {p['hist_wr']:>6.1%} {p['ob_wr']:>5.1%} {p['hist_trades']:>5d}")

print(f"\n  🟡 FVG_Bull + Other ({len(fvg)+len(other)}只, 全部保留)")
for p in fvg[:40]:
    print(f"  {p['symbol']:<12s} {p['signal']:<14s} {p['signal_price']:>8.2f} {p['last_close']:>8.2f} {p['sl_price']:>8.2f} {p['tp_price']:>8.2f} {p['hist_wr']:>6.1%}")
for p in other[:40]:
    print(f"  {p['symbol']:<12s} {p['signal']:<14s} {p['signal_price']:>8.2f} {p['last_close']:>8.2f} {p['sl_price']:>8.2f} {p['tp_price']:>8.2f} {p['hist_wr']:>6.1%}")

# Save
json.dump({'time':'2026-05-14 11:00','ob':ob,'fvg':fvg,'other':other,'all':picks},
          open(OUT/'today_picks_0514.json','w'),ensure_ascii=False)
print(f"\n  Saved: {OUT/'today_picks_0514.json'} (OB:{len(ob)} FVG:{len(fvg)} Other:{len(other)})")
