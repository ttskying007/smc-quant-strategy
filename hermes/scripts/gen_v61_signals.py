#!/usr/bin/env python3
"""
V6.1 全量信号生成
=================
用V4 scan结果中的WR>=80%股票 + V6.1引擎生成信号
"""
import sys, os, json, time
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
from pathlib import Path
from datetime import datetime
from smc_engine_v61 import (load_cached_bars, detect_entries_v61, simulate_entry,
                            evaluate_v6, classify_market_state)

OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v6'
os.makedirs(OPT_DIR, exist_ok=True)

# Load V4 scan results
V4_RESULTS = Path.home() / '.hermes' / 'smc_opt_v4' / 'scan_v4_results.json'

print("="*70)
print("  V6.1 全量信号生成")
print("="*70)

# 1. Load scan results
with open(V4_RESULTS) as f:
    all_stocks = json.load(f)
print(f"  V4 scan results: {len(all_stocks)} stocks")

# Filter WR>=80%
quality = [s for s in all_stocks if s.get('wr_s', 0) >= 80]
print(f"  WR>=80%: {len(quality)} stocks")

# 2. Try to load GA best params
best_params = None
param_sources = [
    OPT_DIR / 'best_params_v61.json',
    OPT_DIR / 'ga_v2_result.json',
]

for ps in param_sources:
    if ps.exists():
        with open(ps) as f:
            data = json.load(f)
            if 'params' in data:
                best_params = data['params']
            else:
                # Direct params + metadata
                best_params = {k: v for k, v in data.items() 
                              if not k.startswith('_') and k in 
                              ['fvg_th','score_th','sl_mult','tp_mult','min_sigs']}
        break

if best_params:
    print(f"  Using params: {json.dumps(best_params)}")
else:
    print(f"  No GA params found, using defaults")
    best_params = {'fvg_th': 0.25, 'score_th': 2.5, 'sl_mult': 2.0, 'tp_mult': 2.5, 'min_sigs': 2}

# 3. Process stocks
results = []
errors = {}
start = time.time()

# Process in chunks for progress reporting
total = len(quality)
print(f"\n  Processing {total} stocks...")

for i, s in enumerate(quality):
    code = s['code']
    name = s['name']
    
    try:
        bars = load_cached_bars(code, 300)
        if not bars or len(bars) < 100:
            continue
        
        state = classify_market_state(bars)
        entries = detect_entries_v61(bars, best_params)
        
        total_sigs = entries.get('total', [])
        if not total_sigs:
            continue
        
        # Generate trade outcomes
        trades = []
        for e in total_sigs:
            t = simulate_entry(e, bars)
            if t:
                trades.append(t)
        
        if not trades:
            continue
        
        # Calculate performance
        wins = [t for t in trades if t['pnl']>0]
        losses = [t for t in trades if t['pnl']<=0]
        wr = len(wins)/len(trades)*100
        win_sum = sum(t['pnl'] for t in wins) if wins else 0
        loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
        pf = (win_sum/loss_sum) if loss_sum>0 else (999 if win_sum>0 else 0)
        
        # Signal detail
        signals_list = []
        modes = {'bronze': 0, 'silver': 0, 'gold': 0}
        for mode_name in ['bronze', 'silver', 'gold']:
            modes[mode_name] = len(entries.get(mode_name, []))
        
        for e in total_sigs[:5]:  # 最多5个信号
            idx = e.get('idx', 0)
            dir_label = 'LONG' if e.get('dir') == 'L' else 'SHORT'
            sigs = e.get('sigs', [])
            sc = e.get('sc', 0)
            level = e.get('level', '?')
            
            entry_time = ''
            if 0 <= idx < len(bars):
                t_val = bars[idx].get('t', '')
                entry_time = str(t_val)[:10] if t_val else ''
            
            ep = e.get('ep', 0)
            sl = e.get('sl', 0)
            tp = e.get('tp', 0)
            
            risk_pct = reward_pct = rr = 0
            if ep and sl and tp:
                if dir_label == 'LONG':
                    risk_pct = abs(ep-sl)/ep*100
                    reward_pct = abs(tp-ep)/ep*100
                else:
                    risk_pct = abs(sl-ep)/ep*100
                    reward_pct = abs(ep-tp)/ep*100
                rr = round(reward_pct/risk_pct, 2) if risk_pct > 0 else 0
            
            signal_types = []
            for s_ in sigs:
                if 'FVG' in s_ and 'F' not in s_: signal_types.append('FVG')
                elif 'SW' in s_: signal_types.append('Sweep')
                elif 'OB' in s_: signal_types.append('OB')
                elif 'CH' in s_: signal_types.append('CHOCH')
                elif 'BPR' in s_: signal_types.append('BPR')
                elif 'MS' in s_: signal_types.append('MS')
                elif 'CF' in s_: signal_types.append('Confirm')
            signal_types = list(dict.fromkeys(signal_types))
            
            signals_list.append({
                'level': level,
                'direction': dir_label,
                'entry_time': entry_time,
                'entry_price': round(ep, 4) if ep else 0,
                'stop_loss': round(sl, 4) if sl else 0,
                'take_profit': round(tp, 4) if tp else 0,
                'risk_pct': round(risk_pct, 2),
                'reward_pct': round(reward_pct, 2),
                'rr_ratio': rr,
                'score': sc,
                'signal_types': signal_types,
                'raw_signals': sigs,
            })
        
        results.append({
            'code': code,
            'name': name,
            'state': {
                'vol': state[0],
                'trend': state[1],
                'volume': state[2],
            },
            'current_price': round(bars[-1]['c'], 4),
            'atr_pct': round(
                sum(abs(bars[i]['h']-bars[i]['l']) for i in range(-20,0))/20 / 
                (sum((bars[i]['h']+bars[i]['l'])/2 for i in range(-20,0))/20) * 100, 2
            ),
            'total_signals': len(total_sigs),
            'signals_by_mode': modes,
            'performance': {
                'n_trades': len(trades),
                'wins': len(wins),
                'wr': round(wr, 1),
                'pf': round(pf, 2),
            },
            'sample_signals': signals_list,
        })
        
    except Exception as e:
        errors[code] = str(e)[:60]
    
    if (i+1) % 200 == 0:
        elapsed = time.time() - start
        rate = (i+1)/elapsed if elapsed>0 else 0
        print(f"  [{i+1}/{total}] found: {len(results)} err: {len(errors)} {rate:.1f}stk/s")

elapsed = time.time() - start
print(f"\n  Done! {len(results)} stocks with signals, {len(errors)} errors")
print(f"  Time: {elapsed:.0f}s")

if errors:
    print(f"  Sample errors:")
    for k in list(errors.keys())[:5]:
        print(f"    {k}: {errors[k]}")

# 4. Save full results
output = {
    'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    'params': best_params,
    'total_stocks': len(results),
    'errors': len(errors),
    'processing_time_s': round(elapsed, 0),
    'stocks': results,
}

json_path = OPT_DIR / 'v61_signals_full.json'
with open(json_path, 'w') as f:
    json.dump(output, f, indent=2, ensure_ascii=False)
print(f"\n  Saved: {json_path}")

# 5. Stats
wrs = []
pfs = []
for r in results:
    p = r.get('performance', {})
    if p.get('n_trades', 0) > 0:
        wrs.append(p['wr'])
        pfs.append(p['pf'])

if wrs:
    print(f"\n{'='*70}")
    print(f"  V6.1 综合统计 ({len(results)} stocks)")
    print(f"{'='*70}")
    print(f"  Avg WR: {sum(wrs)/len(wrs):.1f}%")
    print(f"  Median WR: {sorted(wrs)[len(wrs)//2]:.1f}%")
    print(f"  WR>=90%: {sum(1 for w in wrs if w>=90)}/{len(wrs)} ({sum(1 for w in wrs if w>=90)/len(wrs)*100:.1f}%)")
    print(f"  WR>=80%: {sum(1 for w in wrs if w>=80)}/{len(wrs)} ({sum(1 for w in wrs if w>=80)/len(wrs)*100:.1f}%)")
    print(f"  WR>=70%: {sum(1 for w in wrs if w>=70)}/{len(wrs)} ({sum(1 for w in wrs if w>=70)/len(wrs)*100:.1f}%)")
    print(f"  WR>=60%: {sum(1 for w in wrs if w>=60)}/{len(wrs)} ({sum(1 for w in wrs if w>=60)/len(wrs)*100:.1f}%)")
    print(f"  Avg PF: {sum(pfs)/len(pfs):.2f}")
    print(f"  PF>=3: {sum(1 for p in pfs if p>=3)}/{len(pfs)}")
    print(f"  PF>=5: {sum(1 for p in pfs if p>=5)}/{len(pfs)}")
    
    total_trades = sum(r.get('performance',{}).get('n_trades',0) for r in results)
    total_signals = sum(r.get('total_signals',0) for r in results)
    print(f"  Total trades: {total_trades}")
    print(f"  Total signals: {total_signals}")
    print(f"  Avg trades/stock: {total_trades/len(results):.1f}")
    print(f"  Avg signals/stock: {total_signals/len(results):.1f}")

from collections import defaultdict

# 6. Per-mode stats
modes_count = defaultdict(lambda: defaultdict(int))
for r in results:
    for mode, cnt in r.get('signals_by_mode', {}).items():
        if cnt > 0:
            modes_count[mode]['stocks'] += 1
            modes_count[mode]['count'] += cnt

print(f"\n  Signal modes:")
for mode in ['bronze', 'silver', 'gold']:
    if mode in modes_count:
        print(f"    {mode:>8}: {modes_count[mode]['stocks']} stocks, {modes_count[mode]['count']} signals")

# 7. Top 30 stocks for quick reference
print(f"\n{'='*70}")
print(f"  Top 50 stocks by WR")
print(f"{'='*70}")
top = sorted(results, key=lambda x: -x.get('performance',{}).get('wr', 0))[:50]
print(f"{'代码':>10} {'名称':>8} {'WR':>5} {'PF':>6} {'n':>3} {'vol':>8} {'趋势':>6} {'量':>6}")
for r in top:
    p = r.get('performance', {})
    s = r.get('state', {})
    print(f"{r['code']:>10} {r['name'][:8]:>8} {p.get('wr',0):>5.1f}% {p.get('pf',0):>6.2f} "
          f"{p.get('n_trades',0):>3d} {s.get('vol','?'):>8} {s.get('trend','?'):>6} {s.get('volume','?'):>6}")

# Generate easy-to-read report
print(f"\n  Done! Full report: {json_path}")
print(f"  Quick stats: {OPT_DIR / 'v61_stats.txt'}")

# Save stats
with open(OPT_DIR / 'v61_stats.txt', 'w') as f:
    f.write(f"V6.1 全量信号统计\n")
    f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"参数: {json.dumps(best_params)}\n")
    f.write(f"股票总数: {len(results)}\n")
    if wrs:
        f.write(f"平均WR: {sum(wrs)/len(wrs):.1f}%\n")
        f.write(f"中位数WR: {sorted(wrs)[len(wrs)//2]:.1f}%\n")
        f.write(f"WR>=90%: {sum(1 for w in wrs if w>=90)}/{len(wrs)}\n")
        f.write(f"WR>=80%: {sum(1 for w in wrs if w>=80)}/{len(wrs)}\n")
        f.write(f"总交易: {total_trades}\n")
        f.write(f"总信号: {total_signals}\n")