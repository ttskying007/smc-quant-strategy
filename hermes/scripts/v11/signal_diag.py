#!/usr/bin/env python3
"""Deep diagnostic: trace signal detection quality root causes"""
import json, sys
from pathlib import Path

sys.path.insert(0, '/root/.hermes/scripts')
from v11.signals_v19 import (
    detect_all_signals_v19, detect_leg_swings,
    detect_choch_bos_v19, detect_sweep_v19, detect_mss_v19, detect_eql_v19,
    detect_fvg_v19, detect_ob_luxalgo, detect_ob_smc2026,
    _calc_atr
)

# Test stocks: mix of active/quiet, different price ranges
TEST_STOCKS = [
    ('600519_SH', '茅台'),
    ('000001_SZ', '平安银行'),
    ('300750_SZ', '宁德时代'),
    ('600036_SH', '招商银行'),
    ('000858_SZ', '五粮液'),
    ('688981_SH', '中芯国际'),
    ('002594_SZ', '比亚迪'),
]

print("="*80)
print("V19 SIGNAL DETECTION DEEP DIAGNOSTIC")
print("="*80)

for sym, name in TEST_STOCKS:
    fpath = Path(f'/root/.hermes/kline_cache/{sym}_daily_300.json')
    if not fpath.exists():
        print(f"\n{sym} ({name}): NO DATA")
        continue
    
    ohlcv = json.loads(fpath.read_bytes())
    bars = len(ohlcv)
    avg_price = sum(b['c'] for b in ohlcv[-100:])/min(100,bars) if bars>=20 else 100
    atr14 = _calc_atr(ohlcv, 14)
    
    # ── Step 1: Swings ──
    swings, swings_dict = detect_leg_swings(ohlcv, leg_size=20)
    
    # ── Step 2: Each signal type independently + count ──
    fvg = detect_fvg_v19(ohlcv)
    ob_standalone = detect_ob_smc2026(ohlcv, swings)
    choch_bos, _ = detect_choch_bos_v19(ohlcv, swings)
    ob_lux = detect_ob_luxalgo(ohlcv, swings, choch_bos)
    sweep = detect_sweep_v19(ohlcv, swings)
    mss = detect_mss_v19(ohlcv, swings)
    eql = detect_eql_v19(ohlcv, swings, avg_price=avg_price)
    
    # ── Step 3: Cross-check signal overlap ──
    # Check: how many CHOCH/BOS vs number of swings? (CHOCH/BOS only fires ONCE per swing)
    choch_count = sum(1 for s in choch_bos if 'CHOCH' in s.type)
    bos_count = sum(1 for s in choch_bos if 'BOS' in s.type)
    swing_H = len(swings_dict['highs'])
    swing_L = len(swings_dict['lows'])
    
    # Check MSS: cooldown of 12 bars + only fires for swings within 40 bar window
    mss_bull = sum(1 for s in mss if 'Bull' in s.type)
    mss_bear = sum(1 for s in mss if 'Bear' in s.type)
    
    # Check Sweep: needs pierce + close reversal + swing within last 30 bars
    sweep_bsl = sum(1 for s in sweep if s.type == 'Sweep_BSL')
    sweep_ssl = sum(1 for s in sweep if s.type == 'Sweep_SSL')
    
    # Check EQL/EQH: only adjacent pivot comparison
    eqh_count = sum(1 for s in eql if s.type == 'EQH')
    eql_count = sum(1 for s in eql if s.type == 'EQL')
    
    # ── Step 4: Root cause analysis ──
    # How many swing highs within 40-bar window at each bar? (for MSS)
    # How many bars pierce a prior swing but DON'T close back?
    sweep_opportunities = 0
    sweep_pierced_only = 0
    for i in range(5, bars):
        bar = ohlcv[i]
        for s_idx, s_price in ((s.bar_idx, s.price) for s in swings if s.type == 'H'):
            if s_idx >= i-30 and s_idx < i:
                min_pen = max(atr14*0.15, avg_price*0.001)
                if bar['h'] > s_price + min_pen:
                    sweep_opportunities += 1
                    if bar['c'] >= s_price:  # Pierced but didn't close below
                        sweep_pierced_only += 1
                    break
    
    # ── Print ──
    print(f"\n{'─'*60}")
    print(f"  {sym} ({name}) | bars={bars} | avgP={avg_price:.1f} | ATR14={atr14:.2f} ({atr14/avg_price*100:.2f}%)")
    print(f"{'─'*60}")
    print(f"  SWINGS: {swing_H}H + {swing_L}L = {len(swings)} total")
    print(f"    High labels: {[(s.label,s.bar_idx) for s in swings if s.type=='H']}")
    print(f"    Low labels:  {[(s.label,s.bar_idx) for s in swings if s.type=='L']}")
    print(f"")
    print(f"  SIGNAL COUNTS:")
    print(f"    FVG:     Bull={sum(1 for s in fvg if 'Bull' in s.type)} Bear={sum(1 for s in fvg if 'Bear' in s.type)} = {len(fvg)}")
    print(f"    OB(SMC): Bull={sum(1 for s in ob_standalone if 'Bull' in s.type)} Bear={sum(1 for s in ob_standalone if 'Bear' in s.type)} = {len(ob_standalone)}")
    print(f"    OB(Lux): Bull={sum(1 for s in ob_lux if 'Bull' in s.type)} Bear={sum(1 for s in ob_lux if 'Bear' in s.type)} = {len(ob_lux)}")
    print(f"    CHOCH:   Bull={sum(1 for s in choch_bos if 'CHOCH_Bull' in s.type)} Bear={sum(1 for s in choch_bos if 'CHOCH_Bear' in s.type)} = {choch_count}")
    print(f"    BOS:     Bull={sum(1 for s in choch_bos if 'BOS_Bull' in s.type)} Bear={sum(1 for s in choch_bos if 'BOS_Bear' in s.type)} = {bos_count}")
    print(f"    CHOCH+BOS: {choch_count+bos_count}  (max possible: {swing_H+swing_L} swings)")
    print(f"    Sweep:   BSL={sweep_bsl} SSL={sweep_ssl} = {len(sweep)}")
    print(f"    MSS:     Bull={mss_bull} Bear={mss_bear} = {len(mss)}")
    print(f"    EQL/EQH: EQH={eqh_count} EQL={eql_count} = {len(eql)}")
    print(f"")
    print(f"  ROOT CAUSE ANALYSIS:")
    print(f"    CHOCH/BOS: {swing_H+swing_L} swings → {choch_count+bos_count} detected = {(choch_count+bos_count)/(swing_H+swing_L)*100:.0f}% utilization")
    print(f"               Each swing fires AT MOST ONCE (crossed flag). Missing: swings where close never crosses pivot price.")
    print(f"    MSS:       {mss_bull+mss_bear} detected. Cooldown=12 bars limits to ~{bars//12:.0f} max. Window=40 bars.")
    print(f"    Sweep:     {len(sweep)} detected. Opportunities (pierce): {sweep_opportunities}. Pierced-but-no-close-reversal: {sweep_pierced_only}")
    print(f"               Missing: bars that pierce swing but don't close back = {sweep_pierced_only}/{sweep_opportunities}")
    print(f"    EQL/EQH:   {eqh_count+eql_count} detected from {swing_H+swing_L} swings. Only compares ADJACENT pivots of same type.")
    
    # Print example CHOCH/BOS
    print(f"\n  CHOCH/BOS details:")
    for s in choch_bos[:5]:
        m = s.metadata
        print(f"    bar={s.idx} {s.type} price={s.price:.2f} swing_bar={m['swing_bar']} label={m['swing_label']} trend_before={m['trend_before']}")
    
    # Print which swings are NOT crossed
    from v11.signals_v19 import SwingPoint
    uncrossed_H = [s for s in swings if s.type=='H' and not s.crossed]
    uncrossed_L = [s for s in swings if s.type=='L' and not s.crossed]
    if uncrossed_H:
        print(f"  Uncrossed highs: {[(s.label, s.bar_idx, s.price) for s in uncrossed_H]}")
    if uncrossed_L:
        print(f"  Uncrossed lows:  {[(s.label, s.bar_idx, s.price) for s in uncrossed_L]}")
    
    print()

print("="*80)
print("SUMMARY: KEY ISSUES")
print("="*80)
print("""
ISSUE 1: CHOCH/BOS — each swing fires AT MOST ONCE (crossed flag).
         Once a swing is crossed, it's permanently marked and never reused.
         If the first cross is BOS but later becomes CHOCH, it's missed.
         Root: trend_bias determines CHOCH vs BOS at crossing time (static decision).

ISSUE 2: MSS — 12-bar cooldown prevents detection of consecutive MSS events.
         40-bar window limits which swings can trigger MSS.
         Also uses the SAME swings as CHOCH/BOS (different detection logic though).

ISSUE 3: Sweep — requires both pierce AND close reversal.
         Many bars pierce swing but don't close back — these are missed.
         Only checks swings within last 30 bars.

ISSUE 4: EQL/EQH — only compares ADJACENT pivots of same type.
         If two equal highs are 3 pivots apart (with a lower one in between),
         they won't be detected. Also, the 0.5% fixed threshold may be too strict.

ISSUE 5: Sequence windows — fixed 3-5 bar gaps.
         Different stocks have different rhythm (茅台 vs 小盘股).
         High-vol stocks move faster (need shorter windows).
         Low-vol stocks move slower (need longer windows).

ISSUE 6: FRONTEND — only FVG/OB/BPR are drawn as markArea (矩形区域).
         CHOCH/BOS/MSS/Sweep/EQL/EQH are only drawn as horizontal markLine lines,
         which don't show the structural context.
""")
