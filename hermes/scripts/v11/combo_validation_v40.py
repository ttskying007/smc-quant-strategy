#!/usr/bin/env python3
"""
全量组合验证测试 V4.0
=====================
对每只股票, 测试所有信号上下文组合 × 3窗口 × 2周期
目标: 发现哪些信号组合在哪个周期/窗口/股票上最优
输出: 个股最佳组合 + 全局聚合 + 跨周期对比
"""
import json, time
from pathlib import Path
from collections import defaultdict
from itertools import combinations
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
OUT.mkdir(exist_ok=True)

TARGET = 2.0; LOOKAHEAD = 5; MIN_SAMPLES = 3
CTX_WINDOW = 20  # 上下文窗口: 入场信号前N根bar

# Entry signals (what triggers the trade)
ENTRY_SIGNALS = ['FVG_Bull', 'OB_Bull']

# Context signals (what's checked in the window before entry)
ALL_CONTEXT = [
    'FVG_Bull', 'OB_Bull',
    'Sweep_SSL', 'Sweep_BSL', 'EQL', 'EQH',
    'CHOCH_Bull', 'CHOCH_Bear', 'BOS_Bull', 'BOS_Bear',
    'MSS_Bull', 'MSS_Bear',
    'FVG_Bear', 'OB_Bear', 'BPR',
]

# Pre-generate all combos to test (single + pair + triple)
COMBOS = []
for s in ALL_CONTEXT:
    COMBOS.append(frozenset([s]))
for a, b in combinations(ALL_CONTEXT, 2):
    COMBOS.append(frozenset([a, b]))
# Top triples only (most impactful ones)
triple_candidates = ['Sweep_SSL','CHOCH_Bull','BOS_Bull','BOS_Bear','MSS_Bull','OB_Bear','FVG_Bear','BPR','EQL']
for a, b, c in combinations(triple_candidates, 3):
    COMBOS.append(frozenset([a, b, c]))

print(f"Testing {len(COMBOS)} combos per stock × 3 windows × 2 cycles")

def daily_to_weekly(daily):
    w = []
    for i in range(0, len(daily), 5):
        c = daily[i:i+5]
        if len(c) >= 3:
            w.append({'o': c[0]['o'], 'h': max(b['h'] for b in c),
                      'l': min(b['l'] for b in c), 'c': c[-1]['c']})
    return w

def weekly_smc(weekly):
    if len(weekly) < 20: return 'neutral'
    sigs, st, _, _ = detect_all_signals_v20(weekly)
    tc = st['type_counts']
    cb = tc.get('CHOCH_Bull', 0); cbr = tc.get('CHOCH_Bear', 0)
    bb = tc.get('BOS_Bull', 0); bbr = tc.get('BOS_Bear', 0)
    last = [s for s in sigs if 'CHOCH' in s.type]
    last_dir = 'bull' if last and 'Bull' in last[-1].type else ('bear' if last and 'Bear' in last[-1].type else None)
    if last_dir == 'bull' and cb + bb >= cbr + bbr: return 'bullish'
    if last_dir == 'bear' and cbr + bbr > cb + bb: return 'bearish'
    if cb + bb > (cbr + bbr) * 1.5: return 'bullish'
    if cbr + bbr > (cb + bb) * 1.5: return 'bearish'
    return 'neutral'

def analyze_stock(ohlcv, sym):
    """Analyze one stock: test all combos across 3 windows"""
    sigs, st, _, _ = detect_all_signals_v20(ohlcv)
    if not sigs: return None
    
    n = len(ohlcv)
    sig_by_bar = defaultdict(set)
    for s in sigs:
        sig_by_bar[s.idx].add(s.type)
    
    # 3 windows
    windows = {'full': 0, 'mid': max(0, n - 150), 'recent': max(0, n - 50)}
    result = {}
    
    for wn, start_bar in windows.items():
        combo_stats = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': []})
        
        for s in sigs:
            if s.type not in ENTRY_SIGNALS: continue
            bar = s.idx
            if bar < start_bar or bar + LOOKAHEAD >= n: continue
            
            # Collect context signals in window before entry
            ctx = set()
            for bi in range(max(start_bar, bar - CTX_WINDOW), bar + 1):
                ctx.update(sig_by_bar.get(bi, set()))
            ctx.discard(s.type)  # remove entry signal itself
            
            if not ctx: continue
            
            # Calculate return
            ep = ohlcv[bar]['c']
            max_h = max(ohlcv[i]['h'] for i in range(bar + 1, min(bar + LOOKAHEAD + 1, n)))
            ret = (max_h - ep) / ep * 100
            
            # Test all combos
            ctx_frozen = frozenset(ctx)
            for combo in COMBOS:
                if combo.issubset(ctx_frozen):
                    combo_stats[combo]['total'] += 1
                    combo_stats[combo]['returns'].append(ret)
                    if ret >= TARGET:
                        combo_stats[combo]['hits'] += 1
        
        # Filter: only combos with enough samples
        filtered = {}
        for combo, stats in combo_stats.items():
            if stats['total'] >= MIN_SAMPLES:
                hr = stats['hits'] / stats['total']
                filtered[str(sorted(combo))] = {
                    'hits': stats['hits'], 'total': stats['total'],
                    'rate': round(hr, 3),
                    'avg_ret': round(sum(stats['returns']) / len(stats['returns']), 2)
                }
        if filtered:
            result[wn] = filtered
    
    return result if result else None


# ═══ MAIN ═══
daily_files = sorted(KLINE.glob('*_daily_300.json'))
t0 = time.time()

stock_results = {}     # per-stock results
global_combo = defaultdict(lambda: {'hits': 0, 'total': 0, 'returns': [], 'stocks': set()})

for fi, df in enumerate(daily_files):
    name = df.stem.replace('_daily_300', '')
    parts = name.rsplit('_', 1)
    sym = f'{parts[0]}.{parts[1]}' if len(parts) == 2 else name
    try:
        daily = json.loads(df.read_bytes())
        if len(daily) < 50: continue
    except: continue
    
    # Weekly trend
    weekly_path = KLINE / f'{name}_weekly_200.json'
    try:
        if weekly_path.exists():
            weekly = json.loads(weekly_path.read_bytes())
            if len(weekly) < 20: weekly = daily_to_weekly(daily)
        else:
            weekly = daily_to_weekly(daily)
    except:
        weekly = daily_to_weekly(daily)
    
    w_trend = weekly_smc(weekly)
    
    # Analyze daily
    daily_res = analyze_stock(daily, sym)
    
    # Analyze 60min if available
    m60_res = None
    m60_path = KLINE / f'{name}_60min_500.json'
    if m60_path.exists():
        try:
            m60 = json.loads(m60_path.read_bytes())
            if len(m60) >= 30:
                m60_res = analyze_stock(m60, sym)
        except: pass
    
    if daily_res or m60_res:
        stock_results[sym] = {
            'w_trend': w_trend,
            'daily': daily_res,
            '60min': m60_res
        }
        
        # Aggregate to global (daily full window only)
        if daily_res and 'full' in daily_res:
            for combo_str, stats in daily_res['full'].items():
                combo_key = frozenset(eval(combo_str))
                global_combo[combo_key]['hits'] += stats['hits']
                global_combo[combo_key]['total'] += stats['total']
                global_combo[combo_key]['returns'].append(stats['avg_ret'])
                global_combo[combo_key]['stocks'].add(sym)
    
    if (fi + 1) % 500 == 0:
        elapsed = time.time() - t0
        print(f"  [{fi+1}/{len(daily_files)}] {elapsed:.0f}s stocks={len(stock_results)} combos={len(global_combo)}")

elapsed = time.time() - t0

# ═══ REPORT ═══
print(f"\n{'='*70}")
print(f"  全量组合验证 V4.0 ({elapsed:.0f}s)")
print(f"  扫描: {len(daily_files)} → {len(stock_results)}只有效")
print(f"  测试: {len(COMBOS)} 组合 × 3 窗口 × 2 周期")
td = defaultdict(int)
for r in stock_results.values(): td[r['w_trend']] += 1
print(f"  趋势: bullish={td['bullish']} bearish={td['bearish']} neutral={td['neutral']}")
print(f"{'='*70}")

# ── 全局最佳组合 ──
print(f"\n  全局最佳上下文组合 (按WR排序, ≥50只股票, ≥200样本):")
ranked = sorted(global_combo.items(), key=lambda x: x[1]['hits'] / max(x[1]['total'], 1), reverse=True)
shown = 0
for combo, stats in ranked:
    if len(stats['stocks']) < 50 or stats['total'] < 200: continue
    hr = stats['hits'] / stats['total'] * 100
    avg_r = sum(stats['returns']) / len(stats['returns']) if stats['returns'] else 0
    combo_str = '+'.join(sorted(combo, key=lambda x: ('Bull' not in x, x)))
    print(f"    WR={hr:5.1f}%  Ret={avg_r:+5.2f}%  N={stats['total']:>5d}  stocks={len(stats['stocks']):>4d}  [{combo_str[:80]}]")
    shown += 1
    if shown >= 25: break

# ── 窗口敏感度 ──
print(f"\n  窗口敏感度 (top组合在各窗口的表现):")
for combo, stats in ranked[:8]:
    if stats['total'] < 200: continue
    combo_str = '+'.join(sorted(combo))
    rates = []
    for window in ['full', 'mid', 'recent']:
        w_hits = 0; w_total = 0
        for sym, r in stock_results.items():
            dr = r.get('daily', {})
            wd = dr.get(window, {}) if dr else {}
            ck = str(sorted(combo))
            if ck in wd:
                w_hits += wd[ck]['hits']
                w_total += wd[ck]['total']
        if w_total >= 10:
            rates.append(f"{window}={w_hits/w_total*100:.0f}%({w_total})")
    if rates:
        print(f"    [{combo_str[:60]}]  {' | '.join(rates)}")

# ── 周期对比 ──
print(f"\n  周期对比 (同组合日线vs60min full窗口):")
daily_top = {}
m60_top = {}
for combo, stats in ranked[:20]:
    combo_str = str(sorted(combo))
    # Daily aggregate
    d_hits = 0; d_total = 0
    m_hits = 0; m_total = 0
    for sym, r in stock_results.items():
        dr = r.get('daily', {})
        if dr and 'full' in dr and combo_str in dr['full']:
            d_hits += dr['full'][combo_str]['hits']
            d_total += dr['full'][combo_str]['total']
        mr = r.get('60min', {})
        if mr and 'full' in mr and combo_str in mr['full']:
            m_hits += mr['full'][combo_str]['hits']
            m_total += mr['full'][combo_str]['total']
    if d_total >= 50:
        combo_label = '+'.join(sorted(combo, key=lambda x: ('Bull' not in x, x)))[:40]
        d_wr = d_hits / d_total * 100 if d_total else 0
        m_wr = m_hits / m_total * 100 if m_total else 0
        print(f"    {combo_label:45s} 日:{d_wr:.0f}%(N={d_total})  60m:{m_wr:.0f}%(N={m_total})")

# ── 个股最佳 ──
print(f"\n  个股最佳组合 (每只股票full窗口top-1):")
per_stock_best = {}
for sym, r in stock_results.items():
    dr = r.get('daily', {})
    if not dr or 'full' not in dr: continue
    best_combo = max(dr['full'].items(), key=lambda x: x[1]['rate'])
    per_stock_best[sym] = {
        'combo': best_combo[0],
        'rate': best_combo[1]['rate'],
        'total': best_combo[1]['total'],
        'trend': r['w_trend']
    }

# Frequency of best combos
combo_freq = defaultdict(int)
rate_dist = defaultdict(int)
for sym, info in per_stock_best.items():
    combo_freq[info['combo']] += 1
    rate_dist[int(info['rate'] * 10) * 10] += 1

print(f"    有最佳组合: {len(per_stock_best)}只")
print(f"    命中率分布: {dict(sorted(rate_dist.items()))}")

print(f"    最常用最佳组合 (前15):")
for combo_str, freq in sorted(combo_freq.items(), key=lambda x: -x[1])[:15]:
    gs = global_combo.get(frozenset(eval(combo_str)), {})
    gh = gs.get('hits', 0) / max(gs.get('total', 1), 1) * 100 if gs.get('total', 0) > 0 else 0
    print(f"      {freq:>4d}只  GlobalWR={gh:4.1f}%  [{combo_str[:80]}]")

# ═══ SAVE ═══
# Compact: per-stock top-5 combos per window
compact = {}
for sym, r in stock_results.items():
    compact[sym] = {'w_trend': r['w_trend'], 'windows': {}}
    dr = r.get('daily', {})
    for wn in ['full', 'mid', 'recent']:
        if dr and wn in dr:
            top5 = sorted(dr[wn].items(), key=lambda x: x[1]['rate'], reverse=True)[:5]
            compact[sym]['windows'][wn] = {c: s for c, s in top5}

json.dump(compact, open(OUT / 'combo_validation_v40.json', 'w'), ensure_ascii=False)
print(f"\n  Saved: {OUT/'combo_validation_v40.json'} ({len(compact)} stocks)")
