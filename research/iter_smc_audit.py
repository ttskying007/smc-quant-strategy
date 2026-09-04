# -*- coding: utf-8 -*-
"""SMC 核心指标优化测试：新 pivot/sweep/BOS 参数 vs 旧参数
对比同一股票 2024-2026 的回测信号质量"""
import io, json, os, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"

# --- OLD params ---
OLD_PIVOT = 3
OLD_SWEEP_PCT = 0.003
def is_swing_low_old(ks, j):
    if j < OLD_PIVOT or j + OLD_PIVOT >= len(ks): return False
    lo = ks[j]["l"]
    return lo < min(ks[k]["l"] for k in range(j - OLD_PIVOT, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + OLD_PIVOT + 1))
def is_swing_high_old(ks, j):
    if j < OLD_PIVOT or j + OLD_PIVOT >= len(ks): return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - OLD_PIVOT, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + OLD_PIVOT + 1))

# --- NEW params ---
NEW_PIVOT = 5
NEW_SWEEP_PCT = 0.015  # 1.5%
def is_swing_low_new(ks, j):
    if j < NEW_PIVOT or j + NEW_PIVOT >= len(ks): return False
    lo = ks[j]["l"]
    return lo < min(ks[k]["l"] for k in range(j - NEW_PIVOT, j)) and lo <= min(ks[k]["l"] for k in range(j + 1, j + NEW_PIVOT + 1))
def is_swing_high_new(ks, j):
    if j < NEW_PIVOT or j + NEW_PIVOT >= len(ks): return False
    hi = ks[j]["h"]
    return hi > max(ks[k]["h"] for k in range(j - NEW_PIVOT, j)) and hi >= max(ks[k]["h"] for k in range(j + 1, j + NEW_PIVOT + 1))


def sweep_signals(daily, swing_lows, sweep_pct, is_sw_func):
    """Count sweep + BOS signals per stock."""
    sweep_signals = []
    for i in range(60, len(daily) - 5):
        # sweep detect
        swept = None
        for j in reversed(swing_lows):
            if j + (NEW_PIVOT if is_sw_func == is_swing_low_new else OLD_PIVOT) >= i:
                continue
            if daily[i]["l"] <= daily[j]["l"] * (1 + sweep_pct) and daily[i]["c"] > daily[j]["l"]:
                swept = j
                break
        if swept is None:
            continue
        # BOS: close > swing high visible at sweep
        swing_high_vis = max(daily[k]["h"] for k in range(swept, i + 1))
        if daily[i + 1]["c"] > swing_high_vis if i + 1 < len(daily) else False:
            # also check full bar break (new condition)
            full_break = daily[i + 1]["l"] > swing_high_vis if i + 1 < len(daily) else False
            sweep_signals.append({"idx": i, "swept": swept, "bos": daily[i + 1]["c"], "full": full_break})
    return sweep_signals


# Test on 5 stocks
codes = ["000651.SZ", "000404.SZ", "600519.SH", "300750.SZ", "603038.SH"]
for code in codes:
    sym = code.split(".")[0]
    ex = "SH" if code.startswith("6") else "SZ"
    p = os.path.join(KT, f"{sym}_{ex}_daily_800.json")
    if not os.path.exists(p):
        continue
    daily = we.bars_for(p)
    if len(daily) < 200:
        continue
    # OLD swing lows
    old_lows = [j for j in range(OLD_PIVOT, len(daily) - OLD_PIVOT) if is_swing_low_old(daily, j)]
    old_highs = [j for j in range(OLD_PIVOT, len(daily) - OLD_PIVOT) if is_swing_high_old(daily, j)]
    new_lows = [j for j in range(NEW_PIVOT, len(daily) - NEW_PIVOT) if is_swing_low_new(daily, j)]
    new_highs = [j for j in range(NEW_PIVOT, len(daily) - NEW_PIVOT) if is_swing_high_new(daily, j)]
    
    old_sweeps = sweep_signals(daily, old_lows, OLD_SWEEP_PCT, is_swing_low_old)
    new_sweeps = sweep_signals(daily, new_lows, NEW_SWEEP_PCT, is_swing_low_new)
    
    print(f"\n{code}:")
    print(f"  Pivot 3: {len(old_lows)} 低点 {len(old_highs)} 高点 | Sweep+信号: {len(old_sweeps)} | 全bar BOS: {sum(1 for s in old_sweeps if s['full'])}")
    print(f"  Pivot 5: {len(new_lows)} 低点 {len(new_highs)} 高点 | Sweep+信号: {len(new_sweeps)} | 全bar BOS: {sum(1 for s in new_sweeps if s['full'])}")