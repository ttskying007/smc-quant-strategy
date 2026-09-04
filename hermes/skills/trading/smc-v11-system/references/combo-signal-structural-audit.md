# Combo Signal Structural Audit — 2026-05-14

## Root Cause Analysis

### Problem 1: OB_Bull Never Matched in Sequences
**Finding**: 29/35 stocks have OB_Bull signals, but 0/35 sequences use OB_Bull.
**Root cause**: OB_Bull is ALWAYS co-located with LIQ signals (Sweep_SSL, EQL) on the same bar. The sequence detector requires signals on DIFFERENT bars. This is intrinsic to SMC theory — OB (Order Block) forms at swing lows, and LIQ signals also detect swing lows. They are two expressions of the same event.
**Impact**: OB_Bull can never participate in combo sequences. However, OB_Bull standalone has WR=89.5% — it doesn't need a preceding signal.
**BEST FIX**: Keep OB_Bull as a standalone tier-1 signal. Don't force it into sequences.

### Problem 2: FVG zone_low Too Far From Entry
**Finding**: 34/35 FVG combos have zone_low >5% below entry. Median ~9%.
**Impact**: Using zone_low as SL means allowing 9% drawdown — too wide. Capping at 3% means the SL is purely mechanical, losing all structural meaning.
**BEST FIX**: Use nearest swing low as SL for FVG combos (not zone_low), or cap at 3% but accept the mechanical nature.

### Problem 3: FVG Combo With Preceding LIQ/STRUCT Improves WR
**Finding**: FVG with preceding LIQ/STRUCT: WR=74.5% vs isolated FVG: WR=64.5% (+10pp).
**Conclusion**: The combo concept IS valid for FVG. The preceding LIQ/STRUCT provides real signal quality improvement.
**Gap effect**: gap≤10 combos perform better (WR~78%) than gap>10 (WR~72%).

### Problem 4: 3% SL Cap Creates Fragile Trades
**Finding**: With 3% SL cap, 96% of FVG L2 combos hit SL (only 4% WR on 30-day signals).
**Root cause**: A-share stocks easily move 3% within 20 bars. The cap is too tight for FVG's wide zones.
**Contrast**: OB_Bull with raw zone_low achieves 98.2% WR — OB's zone is naturally tight.
**BEST FIX**: For FVG combos, use swing-low-based SL (typically 2-5% below entry) instead of zone_low-based SL.

### Problem 5: Monitor TP/SL Bar-by-Bar Bug (FIXED)
**Finding**: Monitor only checked LAST bar's high/low, missing TP hits on intermediate bars.
**Example**: 002289_SZ hit TP at bar=299 (h=48.98 ≥ TP=48.07) but monitor only saw bar=300.
**Fix**: Walk forward through ALL bars from entry to now in kline_cache daily data.

## Recommended Architecture: Layered Signal System

| Tier | Signal | WR | Trades | SL Method |
|------|--------|-----|--------|-----------|
| L1 | OB_Bull standalone | 89.5% | 76 | zone_low (naturally tight) |
| L2 | LIQ/STRUCT→FVG gap≤10 | ~78% | 23 | swing-low based |
| L3 | LIQ/STRUCT→FVG gap>10 | ~72% | 32 | swing-low based |
| ❌ | FVG isolated (no preceding) | 64.5% | 62 | — filter out |

## Key Files
- `/root/.hermes/scripts/v11/scan_LD_v3.py` — Layered scanner (L1+L2+L3)
- `/root/.hermes/scripts/v11/monitor_check.py` — V3 monitor with bar-by-bar TP/SL walk
- `/root/.hermes/smc_opt_v21/LD_picks_v3.json` — Layered picks output
- `/root/.hermes/scripts/v11/scan_LD_v2.py` — V2 scanner (OB-priority attempt, abandoned)
