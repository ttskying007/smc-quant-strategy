#!/usr/bin/env python3
"""Generate signal details - simple sequential version for debugging"""
import json, sys, os, time
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

from pathlib import Path
from datetime import datetime
KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'

from smc_engine_v4 import detect_entries_v4, backtest_v4, get_volatility_profile

def load_bars(symbol, limit=300):
    cache_key = f"{symbol}_daily_{limit}".replace('.','_').replace('-','_')
    cache_path = KLINE_CACHE / f"{cache_key}.json"
    if cache_path.exists() and os.path.getsize(cache_path) > 100:
        try:
            with open(cache_path) as f:
                return json.load(f)
        except:
            pass
    return None

with open(OPT_DIR / 'scan_v4_results.json') as f:
    all_stocks = json.load(f)

# Filter WR>=80%
quality = [s for s in all_stocks if s.get('wr_s', 0) >= 80]
print(f"Total: {len(all_stocks)} WR>=80%: {len(quality)}")

results = []
errors = {}
start = time.time()

for i, s in enumerate(quality):
    code = s['code']
    name = s['name']
    
    try:
        bars = load_bars(code, 300)
        if not bars or len(bars) < 120:
            continue
        
        vol = get_volatility_profile(bars)
        params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}
        entries = detect_entries_v4(bars, params)
        
        strict_e = entries.get('strict', [])
        total_e = entries.get('total', [])
        
        if not strict_e and not total_e:
            continue
        
        signals_list = []
        for mode_name, mode_entries in [('strict', strict_e), ('total', total_e)]:
            for e in mode_entries:
                idx = e.get('idx', 0)
                dir_label = 'LONG' if e.get('dir') == 'L' else 'SHORT'
                sigs = e.get('sigs', [])
                sc = e.get('sc', 0)
                
                entry_time = ""
                if 0 <= idx < len(bars):
                    t_val = bars[idx].get('t', '')
                    entry_time = str(t_val)[:10] if t_val else ''
                    if len(entry_time) == 8:
                        entry_time = f"{entry_time[:4]}-{entry_time[4:6]}-{entry_time[6:8]}"
                
                ep = e.get('ep', 0)
                sl = e.get('sl', 0)
                tp = e.get('tp', 0)
                
                if ep and sl and tp:
                    if dir_label == 'LONG':
                        risk = abs(ep-sl)/ep*100
                        reward = abs(tp-ep)/ep*100
                    else:
                        risk = abs(sl-ep)/ep*100
                        reward = abs(ep-tp)/ep*100
                    rr = round(reward/risk,2) if risk>0 else 0
                else:
                    risk=reward=rr=0
                
                signal_types = []
                for s_ in sigs:
                    if 'FVG' in s_: signal_types.append('FVG')
                    elif 'SW' in s_: signal_types.append('Sweep')
                    elif 'OB' in s_: signal_types.append('OB')
                    elif 'CH' in s_: signal_types.append('CHOCH')
                    elif 'BPR' in s_: signal_types.append('BPR')
                    elif 'MS' in s_: signal_types.append('MS')
                    elif 'MG' in s_: signal_types.append('MergeFVG')
                    elif 'CF' in s_: signal_types.append('ConfirmBar')
                signal_types = list(dict.fromkeys(signal_types))
                
                signals_list.append({
                    'mode': mode_name, 'direction': dir_label,
                    'entry_time': entry_time,
                    'entry_price': round(ep,4), 'stop_loss': round(sl,4), 'take_profit': round(tp,4),
                    'risk_pct': round(risk,2), 'reward_pct': round(reward,2), 'rr_ratio': rr,
                    'score': sc, 'signal_types': signal_types, 'raw_signals': sigs,
                })
        
        if signals_list:
            strict_trades = backtest_v4(bars, 'strict', params)
            total_trades = backtest_v4(bars, 'total', params)
            
            perf = {}
            for mn, trades in [('strict', strict_trades), ('total', total_trades)]:
                if trades and len(trades)>0:
                    wins = [t for t in trades if t['pnl']>0]
                    losses = [t for t in trades if t['pnl']<=0]
                    wr = len(wins)/len(trades)*100 if trades else 0
                    loss_sum = abs(sum(t['pnl'] for t in losses)) if losses else 0
                    win_sum = sum(t['pnl'] for t in wins) if wins else 0
                    pf = (win_sum / loss_sum) if loss_sum > 0 else 999 if win_sum > 0 else 0
                    perf[mn] = {'n': len(trades), 'wins': len(wins), 'wr': round(wr,1), 'pf': round(pf,2)}
            
            results.append({
                'code': code, 'name': name,
                'vol_level': vol.get('vol_level','?'), 'atr_pct': vol.get('atr_pct',0),
                'current_price': round(bars[-1]['c'],4),
                'signals': signals_list, 'performance': perf,
            })
    except Exception as e:
        errors[code] = str(e)[:40]
    
    if (i+1) % 200 == 0:
        elapsed = time.time()-start
        rate = (i+1)/elapsed if elapsed>0 else 0
        print(f"  [{i+1}/{len(quality)}] found: {len(results)} err: {len(errors)} {rate:.1f}stk/s")

print(f"\nDone! {len(results)} stocks with signals, {len(errors)} errors")
if errors:
    print(f"Sample errors:")
    for k in list(errors.keys())[:5]:
        print(f"  {k}: {errors[k]}")

# SAVE
with open(OPT_DIR / 'signal_details_full.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Compact report
lines = []
lines.append('='*70)
lines.append(f'SMC V4 — 有信号股票({len(results)}只)')
lines.append(f'生成: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
lines.append(f'{"="*70}')
header = f'  {"代码":>10} {"名称":<10} {"方向":>6} {"时间":>12} {"入场":>8} {"止损":>8} {"止盈":>8} {"R:R":>5} {"评分":>5} {"触发":<30}'
lines.append(header)
lines.append('  ' + '-'*68)

for r in results:
    code = r['code']
    name = r['name'][:8]
    for s in r.get('signals', [])[:3]:
        d = s['direction'][:4]
        t = s['entry_time'][:10]
        ep = f"{s['entry_price']:>7.2f}" if s['entry_price'] else '  N/A'
        sl = f"{s['stop_loss']:>7.2f}" if s['stop_loss'] else '  N/A'
        tp_v = s.get('take_profit', 0)
        tp = f"{tp_v:>7.2f}" if tp_v else '  N/A'
        rr = f"{s['rr_ratio']:>4.1f}" if s['rr_ratio'] else '  N/A'
        sc = f"{s['score']:>4.1f}"
        trig = '+'.join(s['signal_types'][:4])
        lines.append(f"  {code:>10} {name:<10} {d:>6} {t:>12} {ep:>8} {sl:>8} {tp:>8} {rr:>5} {sc:>5} {trig:<30}")

lines.append(f'\nTotal: {len(results)} stocks')
lines.append(f'Signals: {sum(len(r.get("signals",[])) for r in results)}')

with open(OPT_DIR / 'signal_details_compact.txt', 'w') as f:
    f.write('\n'.join(lines))

# Detailed report (for first 100)
detail_lines = []
for r in results[:200]:
    code = r['code']; name = r['name']
    vol = r.get('vol_level','?'); atr = r.get('atr_pct',0); price = r.get('current_price',0)
    detail_lines.append(f'{"="*70}')
    detail_lines.append(f'  {code} | {name} | price={price:.2f} | ATR={atr:.2f}% | {vol}')
    perf = r.get('performance',{})
    for m in ['strict','total']:
        if m in perf:
            p = perf[m]
            detail_lines.append(f'  {m}: {p["n"]}t WR={p["wr"]}% PF={p["pf"]}')
    for i,s in enumerate(r.get('signals',[]),1):
        detail_lines.append(f'  #{i} [{s["mode"]}] {s["direction"]} @ {s["entry_time"]}')
        detail_lines.append(f'    EP={s["entry_price"]:.2f} SL={s["stop_loss"]:.2f} TP={s["take_profit"]:.2f} RR={s["rr_ratio"]} score={s["score"]}')
        detail_lines.append(f'    Trigger: {"+".join(s["signal_types"][:5])}')
        detail_lines.append(f'    Raw: {" ".join(s.get("raw_signals",[]))}')

with open(OPT_DIR / 'signal_details_report.txt', 'w') as f:
    f.write('\n'.join(detail_lines))

print(f"\nFiles saved:")
print(f"  JSON: {OPT_DIR}/signal_details_full.json")
print(f"  Table: {OPT_DIR}/signal_details_compact.txt")
print(f"  Report: {OPT_DIR}/signal_details_report.txt")

# Show first 10
print(f"\n{'='*70}")
print(f"  First 10 stocks with signal details:")
print(f"{'='*70}")
for r in results[:10]:
    print(f"\n  {r['code']} | {r['name']} | price={r['current_price']:.2f}")
    for s in r.get('signals', [])[:2]:
        print(f"    {s['direction']:>6} @ {s['entry_time']}: "
              f"ep={s['entry_price']:.2f} sl={s['stop_loss']:.2f} tp={s['take_profit']:.2f} "
              f"RR={s['rr_ratio']} |{'+'.join(s['signal_types'][:4])}| score={s['score']}")