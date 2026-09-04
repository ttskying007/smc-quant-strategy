#!/usr/bin/env python3
"""
SMC V5 全量回测 — 市场状态驱动 + 策略管理
===========================================
每只股票扫描全部历史K线, 每根bar:
  1. 更新FVG回补率 → 判断市场状态
  2. 策略管理: L1(OB)永开, L2(LIQ→FVG)仅MR
  3. V19 find_tps/find_sls + RR≥1
  4. 逐bar入场, 向前遍历TP/SL
"""
import json, sys, time
from pathlib import Path
from collections import defaultdict, Counter

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20
from v11.v19_backtest_engine import find_tps, find_sls

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

# ═══ 配置 ═══
LIQ_LONG = ['Sweep_SSL', 'EQL']
STRUCT_LONG = ['CHOCH_Bull','BOS_Bull','MSS_Bull']
LOOKBACK_FVG = 20     # FVG回补率窗口
MIN_GAP = 1; MAX_GAP = 10
MAX_STOCKS = 0         # 0=全量
MIN_BARS = 80

def weekly_smc_trend(weekly):
    if len(weekly) < 20: return 'neutral', {}
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb=tc.get('CHOCH_Bull',0); cbr=tc.get('CHOCH_Bear',0)
    bb=tc.get('BOS_Bull',0); bbr=tc.get('BOS_Bear',0)
    last_ch = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last_ch and 'Bull' in last_ch[-1].type else ('bear' if last_ch and 'Bear' in last_ch[-1].type else None)
    if last_dir=='bull' and cb+bb>=cbr+bbr: return 'bullish', tc
    if last_dir=='bear' and cbr+bbr>cb+bb: return 'bearish', tc
    if cb+bb>(cbr+bbr)*1.5: return 'bullish', tc
    if cbr+bbr>(cb+bb)*1.5: return 'bearish', tc
    return 'neutral', tc

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o':c[0]['o'],'h':max(b['h'] for b in c),'l':min(b['l'] for b in c),'c':c[-1]['c']})
    return w

def get_market_state(fvg_fill_count, fvg_total):
    """基于FVG回补率判断市场状态"""
    if fvg_total < 5: return 'transition'
    rate = fvg_fill_count / fvg_total
    if rate > 0.60: return 'mean_reversion'
    if rate < 0.40: return 'expansion'
    return 'transition'

# ═══ MAIN ═══
t0 = time.time()
daily_files = sorted(KLINE.glob('*_daily_300.json'))
if MAX_STOCKS > 0:
    daily_files = daily_files[:MAX_STOCKS]

results = {
    'L1': {'trades':0,'wins':0,'pnls':[],'tp_hits':0,'sl_hits':0},
    'L2': {'trades':0,'wins':0,'pnls':[],'tp_hits':0,'sl_hits':0},
    'by_state': defaultdict(lambda: defaultdict(lambda: {'t':0,'w':0,'pnls':[]})),
    'state_dist': Counter(),
}

stock_count = 0
trade_count = 0

for fi, df in enumerate(daily_files):
    sym = df.stem.replace('_daily_300', '')
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < MIN_BARS: continue
    except: continue
    
    # Weekly trend filter
    weekly_path = KLINE / f'{sym}_weekly_200.json'
    weekly = None
    if weekly_path.exists():
        try: weekly = json.loads(weekly_path.read_bytes())
        except: pass
    if weekly is None or len(weekly) < 20:
        weekly = daily_to_weekly(daily)
    w_trend, _ = weekly_smc_trend(weekly)
    if w_trend != 'bullish': continue
    
    stock_count += 1
    
    # Daily signals
    sigs, st, _, swings_dict = detect_all_signals_v20(daily)
    sbb = defaultdict(list)
    for s in sigs: sbb[s.idx].append(s)
    
    n = len(daily)
    
    # Pre-compute all FVG signals for fill rate tracking
    all_fvg = sorted([s for s in sigs if s.type == 'FVG_Bull'], key=lambda x: x.idx)
    
    # ═══ Walk through every bar ═══
    for bar in range(40, n - 3):
        # ── Market State: rolling FVG fill rate (FVG before this bar) ──
        fvgs_before = [f for f in all_fvg if f.idx < bar]
        recent_fvgs = fvgs_before[-LOOKBACK_FVG:] if len(fvgs_before) >= LOOKBACK_FVG else fvgs_before
        
        filled = 0
        for fvg in recent_fvgs:
            fvg_upper = fvg.upper if hasattr(fvg,'upper') and fvg.upper else fvg.price * 1.01
            for i in range(fvg.idx + 1, min(fvg.idx + 30, bar + 1)):
                if i < n and daily[i]['l'] <= fvg_upper:
                    filled += 1; break
        
        market_state = get_market_state(filled, len(recent_fvgs))
        results['state_dist'][market_state] += 1
        l2_enabled = (market_state == 'mean_reversion')
        
        if bar not in sbb: continue
        types_at_bar = [s.type for s in sbb[bar]]
        
        entry_bar = bar + 1
        if entry_bar >= n - 2: continue
        ep = daily[entry_bar]['o']
        if ep == 0: continue
        
        # ── L1: OB_Bull (always on) ──
        for s in sbb[bar]:
            if s.type != 'OB_Bull': continue
            
            tp, _, _ = find_tps(ep, sigs, swings_dict, daily)
            sl, _, _ = find_sls(ep, sigs, swings_dict, daily)
            if tp is None: tp = ep * 1.05
            if tp > ep * 1.05: tp = ep * 1.05
            if sl is None: sl = ep * 0.97
            
            tpd = abs(tp - ep) / ep * 100
            sld = abs(sl - ep) / ep * 100
            if sld == 0 or tpd / sld < 1.0: continue
            
            # Walk forward
            exit_idx = -1; exit_p = 0; exit_m = 'eod'
            for i in range(entry_bar + 1, n):
                b = daily[i]
                if b['h'] >= tp: exit_idx = i; exit_p = tp; exit_m = 'tp_hit'; break
                if b['l'] <= sl: exit_idx = i; exit_p = sl; exit_m = 'sl_hit'; break
            if exit_idx < 0: exit_idx = n - 1; exit_p = daily[exit_idx]['c']
            if exit_idx <= entry_bar: continue
            
            pnl = (exit_p - ep) / ep * 100
            results['L1']['trades'] += 1
            if pnl > 0: results['L1']['wins'] += 1
            results['L1']['pnls'].append(pnl)
            if exit_m == 'tp_hit': results['L1']['tp_hits'] += 1
            elif exit_m == 'sl_hit': results['L1']['sl_hits'] += 1
            results['by_state'][market_state]['L1']['t'] += 1
            if pnl > 0: results['by_state'][market_state]['L1']['w'] += 1
            results['by_state'][market_state]['L1']['pnls'].append(pnl)
            trade_count += 1
            break  # one OB per bar
        
        # ── L2: LIQ→FVG (only in Mean Reversion) ──
        if not l2_enabled: continue
        
        liq_sigs = [s for s in sbb[bar] if s.type in LIQ_LONG]
        if not liq_sigs: continue
        
        for liq in liq_sigs:
            for j in range(bar + MIN_GAP, min(bar + MAX_GAP + 1, n)):
                if j not in sbb: continue
                fvg_sigs = [s for s in sbb[j] if s.type == 'FVG_Bull']
                if not fvg_sigs: continue
                
                entry_bar2 = j + 1
                if entry_bar2 >= n - 2: continue
                ep2 = daily[entry_bar2]['o']
                if ep2 == 0: continue
                
                tp2, _, _ = find_tps(ep2, sigs, swings_dict, daily)
                sl2, _, _ = find_sls(ep2, sigs, swings_dict, daily)
                if tp2 is None: tp2 = ep2 * 1.05
                if tp2 > ep2 * 1.05: tp2 = ep2 * 1.05
                if sl2 is None: sl2 = ep2 * 0.97
                
                tpd2 = abs(tp2 - ep2) / ep2 * 100
                sld2 = abs(sl2 - ep2) / ep2 * 100
                if sld2 == 0 or tpd2 / sld2 < 1.0: break
                
                exit_idx2 = -1; exit_p2 = 0; exit_m2 = 'eod'
                for i in range(entry_bar2 + 1, n):
                    b = daily[i]
                    if b['h'] >= tp2: exit_idx2 = i; exit_p2 = tp2; exit_m2 = 'tp_hit'; break
                    if b['l'] <= sl2: exit_idx2 = i; exit_p2 = sl2; exit_m2 = 'sl_hit'; break
                if exit_idx2 < 0: exit_idx2 = n - 1; exit_p2 = daily[exit_idx2]['c']
                if exit_idx2 <= entry_bar2: continue
                
                pnl2 = (exit_p2 - ep2) / ep2 * 100
                results['L2']['trades'] += 1
                if pnl2 > 0: results['L2']['wins'] += 1
                results['L2']['pnls'].append(pnl2)
                if exit_m2 == 'tp_hit': results['L2']['tp_hits'] += 1
                elif exit_m2 == 'sl_hit': results['L2']['sl_hits'] += 1
                results['by_state'][market_state]['L2']['t'] += 1
                if pnl2 > 0: results['by_state'][market_state]['L2']['w'] += 1
                results['by_state'][market_state]['L2']['pnls'].append(pnl2)
                trade_count += 1
                break
    
    if (fi + 1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s stocks={stock_count} trades={trade_count}")

elapsed = time.time() - t0

# ═══ REPORT ═══
def summarize(d, label=''):
    if d['trades'] == 0: return f'{label}: 0笔'
    wr = d['wins'] / d['trades'] * 100
    avg = sum(d['pnls']) / len(d['pnls'])
    cum = sum(d['pnls'])
    tp = d.get('tp_hits', 0)
    sl = d.get('sl_hits', 0)
    avg_tp = sum(x for x in d['pnls'] if x > 0) / max(1, sum(1 for x in d['pnls'] if x > 0))
    avg_sl = sum(abs(x) for x in d['pnls'] if x <= 0) / max(1, sum(1 for x in d['pnls'] if x <= 0))
    rr = avg_tp / avg_sl if avg_sl > 0 else 999
    return f'{label}: {d["trades"]}笔 WR={wr:.1f}% avgPnL={avg:+.2f}% cum={cum:+.1f}% TP={tp} SL={sl} RR={rr:.1f}'

print(f"\n{'='*80}")
print(f"  SMC V5 全量回测 — {elapsed:.0f}s — {stock_count}只股票 — {trade_count}笔交易")
print(f"{'='*80}")

print(f"\n  市场状态分布: {dict(results['state_dist'].most_common())}")

print(f"\n  策略表现:")
print(f"  {summarize(results['L1'], 'L1 OB_Bull')}")
print(f"  {summarize(results['L2'], 'L2 LIQ→FVG')}")

# Combined
all_pnls = results['L1']['pnls'] + results['L2']['pnls']
total_t = results['L1']['trades'] + results['L2']['trades']
total_w = results['L1']['wins'] + results['L2']['wins']
total_cum = sum(all_pnls)
total_wr = total_w / total_t * 100 if total_t else 0
print(f"\n  {summarize({'trades':total_t,'wins':total_w,'pnls':all_pnls,'tp_hits':results['L1']['tp_hits']+results['L2']['tp_hits'],'sl_hits':results['L1']['sl_hits']+results['L2']['sl_hits']}, '组合')}")

# By market state
print(f"\n  按市场状态 × 策略:")
for state in ['expansion', 'transition', 'mean_reversion']:
    for tier in ['L1', 'L2']:
        d = results['by_state'][state][tier]
        if d['t'] == 0: continue
        wr = d['w'] / d['t'] * 100
        avg = sum(d['pnls']) / len(d['pnls'])
        cum = sum(d['pnls'])
        print(f"    {state}/{tier}: {d['t']}笔 WR={wr:.1f}% avgPnL={avg:+.2f}% cum={cum:+.1f}%")

# Save
output = {
    'meta': {'version': 'V5 full backtest', 'stocks': stock_count, 'trades': trade_count, 'elapsed': round(elapsed)},
    'L1': {k: v for k, v in results['L1'].items() if k != 'pnls'},
    'L2': {k: v for k, v in results['L2'].items() if k != 'pnls'},
    'L1_wr': results['L1']['wins'] / max(1, results['L1']['trades']) * 100,
    'L2_wr': results['L2']['wins'] / max(1, results['L2']['trades']) * 100,
    'L1_avg_pnl': sum(results['L1']['pnls']) / max(1, len(results['L1']['pnls'])),
    'L2_avg_pnl': sum(results['L2']['pnls']) / max(1, len(results['L2']['pnls'])),
    'state_dist': dict(results['state_dist']),
}
json.dump(output, open(OUT / 'backtest_v5_full.json', 'w'), ensure_ascii=False)
print(f"\n  保存: {OUT / 'backtest_v5_full.json'}")
