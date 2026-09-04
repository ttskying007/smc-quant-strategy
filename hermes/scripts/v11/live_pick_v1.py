#!/usr/bin/env python3
"""
今日选股 + 实时监控 V1.0
2026-05-14 11:00
===================
1. 刷新日线数据到最新 (Hubble API)
2. 全量扫描OB_Bull + 所有信号
3. 输出选股清单: 代码/名称/信号/价格/SL/TP/历史WR
4. 30分钟监控 + T+1 + 盈亏记录
"""
import json, time, subprocess
from pathlib import Path
from collections import defaultdict
import sys

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v20 import detect_all_signals_v20, _calc_atr

KLINE = Path('/root/.hermes/kline_cache')
OUT = Path('/root/.hermes/smc_opt_v21')
DNA_FILE = OUT / 'stock_dna_v11.json'
MONITOR = OUT / 'live_monitor'
MONITOR.mkdir(exist_ok=True)

HUBBLE = 'http://43.167.234.49:3101/api/v2/cnstock/stocks'
KEY = '123456'

# ═══ Step 1: Refresh daily data ═══
def refresh_one(symbol):
    """Download latest daily bars from Hubble"""
    name = symbol.replace('.', '_')
    out = KLINE / f'{name}_daily_300.json'
    try:
        cmd = ['curl', '-sS', '--max-time', '10',
               '-H', f'X-API-Key: {KEY}',
               f'{HUBBLE}?symbol={symbol}&interval=daily&limit=300']
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0 and r.stdout.strip():
            d = json.loads(r.stdout)
            bars = d.get('data', [])
            if len(bars) >= 50:
                result = [{'t': b['time'], 'o': b['open'], 'h': b['high'],
                           'l': b['low'], 'c': b['close'], 'v': b.get('volume', 0)}
                          for b in bars]
                result.sort(key=lambda x: x['t'])
                out.write_text(json.dumps(result))
                return len(result)
    except: pass
    return 0

def refresh_all(max_workers=10):
    """Refresh all stocks, skip already-fresh ones"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    # Check freshness first
    sample = KLINE / '600519_SH_daily_300.json'
    if sample.exists():
        d = json.loads(sample.read_bytes())
        last_date = str(d[-1].get('t', d[-1].get('date', '')))[:8]
        if last_date >= '20260513':
            print(f"  Data already fresh (last={last_date}), skipping refresh")
            return
    
    daily = sorted(KLINE.glob('*_daily_300.json'))
    syms = []
    for f in daily:
        n = f.stem.replace('_daily_300', '')
        parts = n.rsplit('_', 1)
        if len(parts) == 2:
            syms.append(f'{parts[0]}.{parts[1]}')
    
    print(f"  Refreshing {len(syms)} stocks (10 workers)...")
    done = 0
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(refresh_one, s): s for s in syms}
        for f in as_completed(futures):
            done += 1
            if done % 1000 == 0:
                print(f"    [{done}/{len(syms)}]")
    print(f"  Refresh complete: {done} stocks")

# ═══ Step 2: Load DNA ═══
def load_dna():
    if not DNA_FILE.exists(): return {}
    with open(DNA_FILE) as f:
        d = json.load(f)
    return d.get('dna', {})

# ═══ Step 3: Scan for today's signals ═══
def scan_today():
    """Scan all stocks for active signals on the last bar"""
    daily_files = sorted(KLINE.glob('*_daily_300.json'))
    dna = load_dna()
    
    picks = []
    stats = {'total': 0, 'ob_bull': 0, 'fvg_bull': 0, 'other': 0}
    
    for fp in daily_files:
        name = fp.stem.replace('_daily_300', '')
        parts = name.rsplit('_', 1)
        if len(parts) != 2: continue
        sym = f'{parts[0]}.{parts[1]}'
        try:
            daily = json.loads(fp.read_bytes())
            if len(daily) < 50: continue
        except: continue
        
        n = len(daily)
        last_bar = daily[-1]
        last_date = str(last_bar.get('t', last_bar.get('date', '')))[:10]
        last_close = last_bar['c']
        
        # Only process if data is recent (within 2 days)
        try:
            ld_int = int(last_date.replace('-', ''))
            if ld_int < 20260512: continue  # skip stale data
        except: continue
        
        try:
            sigs, st, swings, _ = detect_all_signals_v20(daily)
        except: continue
        
        # Find signals on the last few bars (0=last, 1=second last)
        recent_sigs = [s for s in sigs if s.idx >= n - 3]
        
        if not recent_sigs: continue
        stats['total'] += 1
        
        # Get DNA
        stock_dna = dna.get(sym, {})
        
        # ATR for SL calculation
        atr_val = _calc_atr(daily, 14)
        avg_p = sum(b['c'] for b in daily[-50:]) / min(50, n)
        atr_pct = atr_val / avg_p if avg_p > 0 else 0.02
        
        for s in recent_sigs:
            entry = {
                'symbol': sym,
                'signal': s.type,
                'signal_bar': s.idx,
                'signal_date': str(daily[s.idx].get('t', daily[s.idx].get('date', '')))[:10],
                'signal_price': round(s.price, 2),
                'zone_low': round(s.lower, 2) if s.lower > 0 else 0,
                'zone_high': round(s.upper, 2) if s.upper > 0 else 0,
                'last_close': round(last_close, 2),
                'last_date': last_date,
            }
            
            # Entry/SL/TP
            entry['suggested_buy'] = round(last_close, 2)  # T+1: buy at next open
            if s.lower > 0:
                entry['sl_price'] = round(s.lower * 0.995, 2)
            else:
                entry['sl_price'] = round(last_close * 0.97, 2)
            entry['tp_price'] = round(last_close * 1.03, 2)
            
            # Historical WR from DNA
            if stock_dna:
                entry['hist_wr'] = stock_dna.get('v11_wr', 0)
                entry['hist_pnl'] = stock_dna.get('v11_avg_pnl', 0)
                entry['best_pattern'] = stock_dna.get('best_pattern', '?')
                entry['hist_trades'] = stock_dna.get('v11_trades', 0)
                entry['trend'] = stock_dna.get('trend', '?')
                entry['ob_wr'] = stock_dna.get('ob_wr', 0)
                entry['fvg_wr'] = stock_dna.get('fvg_wr', 0)
            else:
                entry['hist_wr'] = 0
                entry['hist_pnl'] = 0
                entry['best_pattern'] = '?'
                entry['hist_trades'] = 0
                entry['trend'] = '?'
                entry['ob_wr'] = 0
                entry['fvg_wr'] = 0
            
            # Signal quality
            if s.type == 'OB_Bull': stats['ob_bull'] += 1
            elif s.type == 'FVG_Bull': stats['fvg_bull'] += 1
            else: stats['other'] += 1
            
            picks.append(entry)
    
    # Sort: OB_Bull first, then by historical WR
    picks.sort(key=lambda x: (
        x['signal'] != 'OB_Bull',
        -x['hist_wr'],
        -(x.get('ob_wr', 0))
    ))
    
    return picks, stats


# ═══ MAIN ═══
print("=" * 70)
print("  SMC 今日选股 + 实时监控 V1.0")
print("  时间: 2026-05-14 11:00")
print("=" * 70)

# Step 1: Refresh data
print("\n[Step 1] 刷新数据...")
refresh_all()

# Step 2: Scan
print("\n[Step 2] 全量扫描...")
picks, stats = scan_today()
print(f"  有信号股票: {stats['total']} | OB_Bull: {stats['ob_bull']} | FVG_Bull: {stats['fvg_bull']} | Other: {stats['other']}")
print(f"  总选股: {len(picks)}")

# Step 3: Output
print(f"\n[Step 3] 今日选股清单 (前50只)")
print(f"  {'代码':<12s} {'信号':<12s} {'信号价':>7s} {'买入':>7s} {'SL':>7s} {'TP':>7s} {'histWR':>7s} {'趋势':>6s}")
print(f"  {'-'*80}")
for i, p in enumerate(picks[:50]):
    print(f"  {p['symbol']:<12s} {p['signal']:<12s} {p['signal_price']:>7.2f} {p['suggested_buy']:>7.2f} "
          f"{p['sl_price']:>7.2f} {p['tp_price']:>7.2f} {p['hist_wr']:>6.1%} {p['trend']:>6s}")

# Step 4: Show all OB_Bull picks with full detail
ob_picks = [p for p in picks if p['signal'] == 'OB_Bull']
print(f"\n[Step 4] OB_Bull 选股详情 (共{len(ob_picks)}只, 全部显示)")
print(f"  {'代码':<12s} {'信号日':<12s} {'信号价':>7s} {'买入(开盘)':>9s} {'SL':>7s} {'TP':>7s} {'histWR':>7s} {'histPnL':>7s} {'OBwr':>6s} {'交易数':>5s}")
print(f"  {'-'*95}")
for i, p in enumerate(ob_picks):
    print(f"  {p['symbol']:<12s} {p['signal_date']:<12s} {p['signal_price']:>7.2f} {p['suggested_buy']:>9.2f} "
          f"{p['sl_price']:>7.2f} {p['tp_price']:>7.2f} {p['hist_wr']:>6.1%} {p['hist_pnl']:>+6.2f}% "
          f"{p['ob_wr']:>5.1%} {p['hist_trades']:>5d}")

# Step 5: Save for monitoring
monitor_file = MONITOR / f'picks_{time.strftime("%Y%m%d_%H%M")}.json'
json.dump({
    'meta': {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'total_picks': len(picks),
             'ob_bull': len(ob_picks), 'fvg_bull': stats['fvg_bull']},
    'picks': picks,
    'ob_picks': ob_picks,
}, open(monitor_file, 'w'), ensure_ascii=False)

# Step 6: Save active positions for monitoring
active = []
for p in ob_picks:
    active.append({
        'symbol': p['symbol'],
        'signal': p['signal'],
        'entry_date': p['last_date'],
        'entry_price': 0,  # will be filled on next open
        'suggested_buy': p['suggested_buy'],
        'sl_price': p['sl_price'],
        'tp_price': p['tp_price'],
        'status': 'pending',  # pending/open/closed
        'hist_wr': p['hist_wr'],
        'hist_pnl': p['hist_pnl'],
    })
json.dump(active, open(MONITOR / 'active_positions.json', 'w'), ensure_ascii=False)

print(f"\n[Step 5] 保存完成")
print(f"  选股清单: {monitor_file}")
print(f"  活跃持仓: {MONITOR/'active_positions.json'} ({len(active)}只)")
print(f"\n  OB_Bull信号股全部列出，共{len(ob_picks)}只")
