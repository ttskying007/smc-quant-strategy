#!/usr/bin/env python3
"""
SMC V4 — Signal Details Generator v3
Final version with all type safety
"""
import importlib
import json, sys, os, time
sys.path.insert(0, os.path.expanduser('~/.hermes/scripts'))
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY']:
    os.environ.pop(k, None)

import smc_engine_v4
importlib.reload(smc_engine_v4)
from smc_engine_v4 import detect_entries_v4, backtest_v4, get_volatility_profile
from pathlib import Path
from datetime import datetime

KLINE_CACHE = Path.home() / '.hermes' / 'kline_cache'
OPT_DIR = Path.home() / '.hermes' / 'smc_opt_v4'

def load_bars(symbol):
    cache_key = f"{symbol}_daily_300".replace('.','_').replace('-','_')
    cp = KLINE_CACHE / f"{cache_key}.json"
    if cp.exists() and os.path.getsize(cp) > 100:
        try:
            with open(cp) as f:
                return json.load(f)
        except:
            pass
    return None

def fmt_time(val):
    if isinstance(val, (int, float)):
        val = str(int(val))
    if isinstance(val, str):
        if len(val) >= 10:
            return val[:10]
        if len(val) == 8:
            return f"{val[:4]}-{val[4:6]}-{val[6:8]}"
    return str(val) if val else ''

params = {'fvg_threshold': 0.26, 'score_threshold': 1.7, 'sl_mult': 2.5, 'tp_mult': 2.1}

with open(OPT_DIR / 'scan_v4_results.json') as f:
    all_stocks = json.load(f)

quality = [s for s in all_stocks if s.get('wr_s', 0) >= 80]
print(f"Total: {len(all_stocks)} WR>=80%: {len(quality)}")

results = []
errs = 0
t0 = time.time()

for i, s in enumerate(quality):
    code = s['code']
    name = s['name']
    
    try:
        bars = load_bars(code)
        if not bars or len(bars) < 120:
            errs += 1
            continue
        
        # Ensure 't' is string
        for b in bars:
            if 't' in b and not isinstance(b['t'], str):
                b['t'] = str(b['t'])
        
        vol = get_volatility_profile(bars)
        entries = detect_entries_v4(bars, params)
        strict_e = entries.get('strict', [])
        total_e = entries.get('total', [])
        
        if not strict_e and not total_e:
            errs += 1
            continue
        
        signals_list = []
        for mn, me in [('strict', strict_e), ('total', total_e)]:
            for e in me:
                idx = e.get('idx', 0)
                dl = 'LONG' if e.get('dir') == 'L' else 'SHORT'
                sigs = e.get('sigs', [])
                sc = e.get('sc', 0)
                
                entry_time = fmt_time(bars[idx]['t']) if 0 <= idx < len(bars) else ''
                ep = e.get('ep', 0)
                sl = e.get('sl', 0)
                tp = e.get('tp', 0)
                
                if ep and sl and tp:
                    if dl == 'LONG':
                        risk = abs(ep-sl)/ep*100
                        reward = abs(tp-ep)/ep*100
                    else:
                        risk = abs(sl-ep)/ep*100
                        reward = abs(ep-tp)/ep*100
                    rr = round(reward/risk,2) if risk>0 else 0
                else:
                    risk=reward=rr=0
                
                stypes = []
                for s_ in sigs:
                    if 'FVG' in s_: stypes.append('FVG')
                    elif 'SW' in s_: stypes.append('Sweep')
                    elif 'OB' in s_: stypes.append('OB')
                    elif 'CH' in s_: stypes.append('CHOCH')
                    elif 'BPR' in s_: stypes.append('BPR')
                    elif 'MS' in s_: stypes.append('MS')
                    elif 'MG' in s_: stypes.append('MergeFVG')
                    elif 'CF' in s_: stypes.append('ConfirmBar')
                stypes = list(dict.fromkeys(stypes))
                
                signals_list.append({
                    'mode': mn, 'direction': dl,
                    'entry_time': entry_time,
                    'entry_price': round(ep,4), 'stop_loss': round(sl,4), 'take_profit': round(tp,4),
                    'risk_pct': round(risk,2), 'reward_pct': round(reward,2), 'rr_ratio': rr,
                    'score': sc, 'signal_types': stypes, 'raw_signals': sigs,
                })
        
        if signals_list:
            strict_t = backtest_v4(bars, 'strict', params)
            total_t = backtest_v4(bars, 'total', params)
            # 防御: backtest_v4可能返回非list
            if not isinstance(strict_t, list): strict_t = []
            if not isinstance(total_t, list): total_t = []
            perf = {}
            for mn, trades in [('strict', strict_t), ('total', total_t)]:
                if trades and len(trades)>0:
                    n_wins = sum(1 for t in trades if t['pnl']>0)
                    losses = [t for t in trades if t['pnl']<=0]
                    n_losses = len(losses)
                    wr = n_wins/len(trades)*100
                    pf = 999
                    if n_losses > 0 and abs(sum(t['pnl'] for t in losses)) > 0.0001:
                        wp_sum = sum(t['pnl'] for t in trades if t['pnl']>0)
                        lp_sum = sum(t['pnl'] for t in losses)
                        pf = abs(wp_sum/lp_sum) if lp_sum != 0 else 999
                    perf[mn] = {'n': len(trades), 'wins': n_wins, 'wr': round(wr,1), 'pf': round(pf,2)}
            
            results.append({
                'code': code, 'name': name,
                'vol_level': vol.get('vol_level','?'), 'atr_pct': vol.get('atr_pct',0),
                'current_price': round(bars[-1]['c'],4),
                'signals': signals_list, 'performance': perf,
            })
    except Exception as e:
        errs += 1
        if errs <= 3:
            import traceback
            print(f"  ERROR [{code}]: {str(e)[:60]}")
            traceback.print_exc()
    
    if (i+1) % 200 == 0 or i == len(quality)-1:
        el = time.time()-t0
        print(f"  [{i+1}/{len(quality)}] found={len(results)} err={errs} {el:.0f}s")

# SAVE
with open(OPT_DIR / 'signal_details_full.json', 'w') as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Compact table
lines = [f'{"="*70}',
         f'SMC V4 — 有信号股票({len(results)}只)',
         f'生成: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}',
         f'{"="*70}',
         f'  {"代码":>10} {"名称":<10} {"方向":>6} {"时间":>12} {"入场":>8} {"止损":>8} {"止盈":>8} {"R:R":>5} {"评分":>5} {"触发":<30}',
         f'  {"-"*68}']
for r in results:
    code = r['code']
    name = r['name'][:8]
    for s in r.get('signals', [])[:3]:
        d = s['direction'][:4]
        t = s['entry_time'][:10]
        ep = f"{s['entry_price']:>7.2f}" if s['entry_price'] else '  N/A'
        sl = f"{s['stop_loss']:>7.2f}" if s['stop_loss'] else '  N/A'
        tp = f"{s['take_profit']:>7.2f}" if s['take_profit'] else '  N/A'
        rr = f"{s['rr_ratio']:>4.1f}"
        sc = f"{s['score']:>4.1f}"
        trig = '+'.join(s['signal_types'][:4])
        lines.append(f"  {code:>10} {name:<10} {d:>6} {t:>12} {ep:>8} {sl:>8} {tp:>8} {rr:>5} {sc:>5} {trig:<30}")
lines.append(f'\nTotal: {len(results)} stocks, {sum(len(r.get("signals",[])) for r in results)} signals')
with open(OPT_DIR / 'signal_details_compact.txt', 'w') as f:
    f.write('\n'.join(lines))

# Detailed report
dl = []
for r in results[:200]:
    dl.append(f'{"="*70}')
    dl.append(f'  {r["code"]} | {r["name"]} | price={r["current_price"]:.2f} | ATR={r["atr_pct"]:.2f}% | {r["vol_level"]}')
    perf = r.get('performance',{})
    for m in ['strict','total']:
        if m in perf:
            p = perf[m]
            dl.append(f'  {m}: {p["n"]}t WR={p["wr"]}% PF={p["pf"]}')
    for i,s in enumerate(r.get('signals',[]),1):
        dl.append(f'  #{i} [{s["mode"]}] {s["direction"]} @ {s["entry_time"]}')
        dl.append(f'    EP={s["entry_price"]:.2f} SL={s["stop_loss"]:.2f} TP={s["take_profit"]:.2f} RR={s["rr_ratio"]} score={s["score"]}')
        dl.append(f'    Trigger: {"+".join(s["signal_types"][:5])}')
        dl.append(f'    Raw: {" ".join(s.get("raw_signals",[]))}')
with open(OPT_DIR / 'signal_details_report.txt', 'w') as f:
    f.write('\n'.join(dl))

print(f"\n{'='*70}")
print(f"  Done! {len(results)} stocks with signal details")
print(f"  {OPT_DIR}/signal_details_full.json")
print(f"  {OPT_DIR}/signal_details_compact.txt")
print(f"  {OPT_DIR}/signal_details_report.txt")
print(f"{'='*70}")

# Show first 10
for r in results[:10]:
    print(f"\n  {r['code']} | {r['name']} | price={r['current_price']:.2f}")
    for s in r.get('signals', [])[:2]:
        print(f"    {s['direction']:>6} @ {s['entry_time']}: "
              f"ep={s['entry_price']:.2f} sl={s['stop_loss']:.2f} tp={s['take_profit']:.2f} "
              f"RR={s['rr_ratio']} |{'+'.join(s['signal_types'][:4])}| sc={s['score']}")