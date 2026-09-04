#!/usr/bin/env python3
"""全量A股: TOP信号组合 vs Baseline 回测对比"""
import json, sys, time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import backtest_v19

KLINE_DIR = Path('/root/.hermes/kline_cache')
files = sorted(KLINE_DIR.glob('*_daily_300.json'))

# TOP组合 (从挖掘数据选出的高命中率+大样本组合)
# 格式: (名称, 必须出现的信号类型集合, 入场信号类型)
FILTERS = {
    'baseline':     {'required': set(), 'entry_types': ('FVG_Bull','OB_Bull')},
    'FVGbear+OB':   {'required': {'FVG_Bear'}, 'entry_types': ('OB_Bull',)},
    'BOSbear+MSSbear+OB': {'required': {'BOS_Bear','MSS_Bear'}, 'entry_types': ('OB_Bull',)},
    'MSSbear+OB':   {'required': {'MSS_Bear'}, 'entry_types': ('OB_Bull',)},
    'OB+SweepBSL':  {'required': {'Sweep_BSL'}, 'entry_types': ('OB_Bull',)},
    'FVGbear+OBbull+FVGbull': {'required': {'FVG_Bear','FVG_Bull'}, 'entry_types': ('OB_Bull',)},
    'BOSbear+OB':   {'required': {'BOS_Bear'}, 'entry_types': ('OB_Bull',)},
    'bearish+OB':   {'required': {'BOS_Bear','MSS_Bear','FVG_Bear','Sweep_BSL'}, 'match_any': True, 'entry_types': ('OB_Bull',)},
}

results = {name: {
    'trades': [], 'stocks': 0, 'total_pnl': 0.0, 'wins': 0,
    'exit_methods': defaultdict(int), 'hold_bars': [],
} for name in FILTERS}

WINDOW = 5  # 上下文窗口

t0 = time.time()
for fi, fp in enumerate(files):
    sym = fp.stem.replace('_daily_300', '')
    try:
        ohlcv = json.loads(fp.read_bytes())
        if len(ohlcv) < 50: continue
    except: continue
    
    sigs, _, _, swings_dict = detect_all_signals_v20(ohlcv)
    n = len(ohlcv)
    
    # Build signal index
    sig_by_bar = defaultdict(set)
    for s in sigs:
        sig_by_bar[s.idx].add(s.type)
    
    # Baseline: unfiltered
    trades_bl = backtest_v19(sym, ohlcv, sigs, swings_dict)
    if isinstance(trades_bl, tuple): trades_bl = trades_bl[0]
    
    if trades_bl:
        results['baseline']['stocks'] += 1
        for t in trades_bl:
            results['baseline']['trades'].append(t.pnl_pct)
            results['baseline']['exit_methods'][t.exit_method] += 1
            results['baseline']['hold_bars'].append(t.hold_bars)
            if t.pnl_pct > 0: results['baseline']['wins'] += 1
            results['baseline']['total_pnl'] += t.pnl_pct
    
    # Filtered entries
    for fname, fconf in FILTERS.items():
        if fname == 'baseline': continue
        
        # Filter signals: only keep entry signals that have required context
        filtered_sigs = []
        for s in sigs:
            if s.type not in fconf['entry_types']:
                filtered_sigs.append(s)
                continue
            
            # Check context window
            nearby = set()
            for bi in range(max(0, s.idx-WINDOW), s.idx+1):
                nearby.update(sig_by_bar.get(bi, set()))
            
            required = fconf['required']
            match_any = fconf.get('match_any', False)
            
            if match_any:
                if nearby & required:
                    filtered_sigs.append(s)  # keep this entry signal
            else:
                if required.issubset(nearby):
                    filtered_sigs.append(s)
                # else: drop this entry signal
        
        if not any(s.type in fconf['entry_types'] for s in filtered_sigs):
            continue
        
        trades_fl = backtest_v19(sym, ohlcv, filtered_sigs, swings_dict)
        if isinstance(trades_fl, tuple): trades_fl = trades_fl[0]
        
        if trades_fl:
            results[fname]['stocks'] += 1
            for t in trades_fl:
                results[fname]['trades'].append(t.pnl_pct)
                results[fname]['exit_methods'][t.exit_method] += 1
                results[fname]['hold_bars'].append(t.hold_bars)
                if t.pnl_pct > 0: results[fname]['wins'] += 1
                results[fname]['total_pnl'] += t.pnl_pct
    
    if (fi+1) % 1000 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/4800] {elapsed:.0f}s bl={len(results['baseline']['trades'])}")

elapsed = time.time() - t0

# Print report
def stats(r):
    trades = r['trades']
    if not trades: return None
    wins = r['wins']
    total = len(trades)
    wr = wins/total*100
    avg_pnl = sum(trades)/total
    win_pnls = [p for p in trades if p > 0]
    loss_pnls = [abs(p) for p in trades if p <= 0]
    avg_win = sum(win_pnls)/len(win_pnls) if win_pnls else 0
    avg_loss = sum(loss_pnls)/len(loss_pnls) if loss_pnls else 0
    pf = sum(win_pnls)/sum(loss_pnls) if loss_pnls else 999
    return {'trades': total, 'stocks': r['stocks'], 'wr': wr, 'avg_pnl': avg_pnl,
            'total_pnl': sum(trades), 'avg_win': avg_win, 'avg_loss': avg_loss,
            'pf': pf, 'exit_methods': dict(r['exit_methods']),
            'avg_hold': sum(r['hold_bars'])/len(r['hold_bars'])}

print(f"\n{'='*75}")
print(f"  全量A股: TOP信号组合过滤回测 ({elapsed:.0f}s)")
print(f"{'='*75}")

bl = stats(results['baseline'])
print(f"\n  {'Filter':25s} {'Stock':>6s} {'Trades':>6s} {'WR':>6s} {'PnL':>7s} {'Win':>7s} {'Loss':>7s} {'PF':>6s} {'Hold':>5s} {'Total':>8s}")
print(f"  {'─'*25} {'─'*6} {'─'*6} {'─'*6} {'─'*7} {'─'*7} {'─'*7} {'─'*6} {'─'*5} {'─'*8}")

for fname in FILTERS:
    s = stats(results[fname])
    if not s: continue
    print(f"  {fname:25s} {s['stocks']:>6d} {s['trades']:>6d} {s['wr']:>5.1f}% {s['avg_pnl']:>+6.2f}% {s['avg_win']:>+6.2f}% {s['avg_loss']:>+6.2f}% {s['pf']:>5.1f} {s['avg_hold']:>4.1f}b {s['total_pnl']:>+7.0f}%")

print()
# PnL distribution for baseline vs best filter
for fname in ['baseline', 'bearish+OB', 'FVGbear+OB', 'BOSbear+MSSbear+OB']:
    s = stats(results[fname])
    if not s: continue
    trades = results[fname]['trades']
    buckets = {'<-2%':0, '-2~-1%':0, '-1~0%':0, '0~1%':0, '1~2%':0, '2~3%':0, '3~5%':0, '>5%':0}
    for p in trades:
        if p < -2: buckets['<-2%'] += 1
        elif p < -1: buckets['-2~-1%'] += 1
        elif p < 0: buckets['-1~0%'] += 1
        elif p < 1: buckets['0~1%'] += 1
        elif p < 2: buckets['1~2%'] += 1
        elif p < 3: buckets['2~3%'] += 1
        elif p <= 5: buckets['3~5%'] += 1
        else: buckets['>5%'] += 1
    bt = len(trades)
    print(f"  {fname} PnL dist: <-2={buckets['<-2%']/bt*100:4.1f}% -2~-1={buckets['-2~-1%']/bt*100:4.1f}% -1~0={buckets['-1~0%']/bt*100:4.1f}% 0~1={buckets['0~1%']/bt*100:4.1f}% 1~2={buckets['1~2%']/bt*100:4.1f}% 2~3={buckets['2~3%']/bt*100:4.1f}% 3~5={buckets['3~5%']/bt*100:4.1f}% >5={buckets['>5%']/bt*100:4.1f}%")
