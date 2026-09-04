#!/usr/bin/env python3
"""V25 Full Market Scan — Trailing Stop Strategy (A/B Quality Filter)"""
import json, sys, time
from pathlib import Path
sys.path.insert(0, '/root/.hermes/scripts')
from v11.rolling_backtest_v25 import *

CACHE_DIR = Path('/root/.hermes/kline_cache')
OUTPUT_DIR = Path('/root/.hermes/smc_opt_v25')
OUTPUT_DIR.mkdir(exist_ok=True)
QUALITY_PATH = Path('/root/.hermes/smc_signals/stock_quality_ratings.json')
FINAL_OUTPUT = Path('/root/.hermes/smc_signals/latest_signals.json')

# Load quality ratings — only process A/B tier
quality_map = {}
if QUALITY_PATH.exists():
    qdata = json.loads(QUALITY_PATH.read_text())
    for s in qdata.get('stocks', []):
        quality_map[s['symbol']] = s
    a_b_symbols = {sym for sym, info in quality_map.items() if info.get('tier') in ('A', 'B')}
    print(f"Quality ratings: {len(quality_map)} total, {len(a_b_symbols)} A/B tier")
else:
    a_b_symbols = None

all_cached = sorted([f.stem.replace('_daily_300','').replace('_','.') for f in CACHE_DIR.glob('*_daily_300.json')])
if a_b_symbols:
    symbols = sorted([s for s in all_cached if s in a_b_symbols])
else:
    symbols = all_cached
print(f"V25 Full Market — {len(symbols)} A/B stocks (of {len(all_cached)} cached)")

all_stocks=[]; all_trades=[]; t_start=time.time()

for idx,sym in enumerate(symbols):
    ohlcv=load_ohlcv(sym)
    if not ohlcv: continue
    phase=detect_market_phase(ohlcv)
    base=calc_stock_params(ohlcv,sym,phase=phase,tf='daily')
    sigs=detect_all_signals_v11(ohlcv,params=base,tf='daily')['all']
    if not sigs or len(sigs)<5: continue
    trades,sp=simulate_trades(ohlcv,sigs,{**base},phase)
    if sp<MIN_SWING_COVERAGE or len(trades)<2: continue
    
    wins=sum(1 for t in trades if t['won'])
    wr=wins/len(trades)*100
    wp=sum(t['pnl_pct'] for t in trades if t['won'])
    lp=abs(sum(t['pnl_pct'] for t in trades if not t['won']))
    pf=wp/lp if lp>0 else 999
    all_stocks.append({'symbol':sym,'n_trades':len(trades),'win_rate':round(wr,1),
                      'avg_rr':round(sum(t['rr'] for t in trades)/len(trades),2),
                      'profit_factor':round(pf,1),'swing_sl_pct':round(sp,1),
                      'avg_pnl':round(sum(t['pnl_pct'] for t in trades)/len(trades),2),
                      'phase':phase,
                      'quality_tier': quality_map.get(sym, {}).get('tier', '?'),
                      'quality_score': quality_map.get(sym, {}).get('score', 0)})
    all_trades.extend(trades)

    if (idx+1)%500==0:
        print(f"  [{idx+1}/{len(symbols)}] {len(all_stocks)} tradable | {(time.time()-t_start):.0f}s")
        # Save checkpoint
        json.dump({'stocks':all_stocks,'trades':all_trades[:10000],'processed':idx+1},
                  open(OUTPUT_DIR/'checkpoint.json','w'),default=str)

total_time=time.time()-t_start
n=len(all_trades); wins=sum(1 for t in all_trades if t['won'])
wr=wins/n*100 if n else 0
wp=sum(t['pnl_pct'] for t in all_trades if t['won'])
lp=abs(sum(t['pnl_pct'] for t in all_trades if not t['won']))
pf=wp/lp if lp>0 else 999
rr=sum(t['rr'] for t in all_trades)/n if n else 0
pnl=sum(t['pnl_pct'] for t in all_trades)/n if n else 0

print(f"\n{'='*70}")
print(f"V25 FULL MARKET — {len(all_stocks)}/{len(symbols)} | {total_time:.0f}s")
print(f"{'='*70}")
print(f"  Trades: {n} | WR: {wr:.1f}% | RR: {rr:.2f}x | PF: {pf:.0f} | P&L: {pnl:+.2f}%")
print(f"  WR>=80%: {sum(1 for s in all_stocks if s['win_rate']>=80)}")
print(f"  Swing SL: {sum(1 for t in all_trades if t.get('sl_type')=='swing')}/{n}" if n else "  Swing SL: 0/0")

# Top 10 by quality score
top10 = sorted(all_stocks, key=lambda x: x['quality_score'], reverse=True)[:10]
print(f"\n{'='*70}")
print(f"TOP 10 SIGNALS (by quality score)")
print(f"{'='*70}")
print(f"  {'#':>3} {'Symbol':<14} {'Tier':>4} {'Score':>6} {'Win%':>6} {'RR':>6} {'PF':>6} {'P&L%':>7} {'Phase':<14}")
print(f"  {'-'*70}")
for i, s in enumerate(top10, 1):
    print(f"  {i:>3} {s['symbol']:<14} {s['quality_tier']:>4} {s['quality_score']:>6.1f} {s['win_rate']:>5.1f}% {s['avg_rr']:>5.2f}x {s['profit_factor']:>5.1f} {s['avg_pnl']:>+6.2f}% {s['phase']:<14}")

# Save to latest_signals.json
output = {
    'timestamp': time.time(),
    'config': {'version': 'V25', 'trailing': True, 'quality_filter': 'A/B only',
               'swing_coverage_min': MIN_SWING_COVERAGE,
               'phase_params': PHASE_PARAMS, 'cycle_mult': CYCLE_SL_MULT},
    'summary': {'total_symbols_scanned': len(symbols), 'tradable': len(all_stocks),
                'total_trades': n, 'win_rate': round(wr, 1), 'avg_rr': round(rr, 2),
                'profit_factor': round(pf, 2), 'avg_pnl': round(pnl, 2),
                'a_stocks': sum(1 for s in all_stocks if s['quality_tier'] == 'A'),
                'b_stocks': sum(1 for s in all_stocks if s['quality_tier'] == 'B')},
    'stocks': all_stocks,
    'top10': top10,
    'all_trades': all_trades[:50000]
}
json.dump(output, open(FINAL_OUTPUT, 'w'), ensure_ascii=False, indent=2, default=str)
print(f"\nSaved: {FINAL_OUTPUT} ({len(all_stocks)} stocks, {n} trades)")

outpath=OUTPUT_DIR/'v25_full_merged.json'
json.dump({'timestamp':time.time(),'config':{'version':'V25','trailing':True},
           'summary':{'total_symbols':len(symbols),'tradable':len(all_stocks),
                      'total_trades':n,'win_rate':round(wr,1),'avg_rr':round(rr,2),
                      'profit_factor':round(pf,2),'avg_pnl':round(pnl,2)},
           'stocks':all_stocks,'all_trades':all_trades},
          open(outpath,'w'),ensure_ascii=False,indent=2,default=str)
print(f"Saved: {outpath}")
