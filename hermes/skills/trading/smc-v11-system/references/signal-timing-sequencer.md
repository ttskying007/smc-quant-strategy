# Signal Time-Sequence Scoring — V33 Architecture Design

## Core Philosophy

A-share daily SMC signals = Market maker's "script". Each signal is a line of dialogue; the ORDER determines story direction.

Traditional systems check "does signal X exist?". This system asks "what story do the last N signals tell?".

## Three-Layer Architecture

### Layer 1: Signal Chain Codes

Each core signal type maps to a 1-char code:

Core signals (kept): FVG(F/f), OB(O/o), Sweep(S/s), CHOCH(C/c)
Filtered out (noise for timing): BPR, LiquidityVoid, RejectionBlock

The last N (max 6) same-direction core signals within lookback=30 bars are concatenated:
```
Sweep@bar30, OB@bar33, FVG@bar35 → chain = "SOF"
```

**Critical**: Target signal is excluded from chain (not counted as preceding).

### Layer 2: Pattern Database

Gold patterns (WR~85%):
  CF: CHOCH→FVG, bonus+0.35
  SF: Sweep→FVG, bonus+0.30
  FO: FVG→OB, bonus+0.30

Silver patterns (WR~70-80%):
  FF: FVG→FVG, bonus+0.20
  OF: OB→FVG, bonus+0.18
  OFC: OB→FVG→CHOCH, bonus+0.45 (WR=88% verified!)
  COF: CHOCH→OB→FVG, bonus+0.40
  FFO: FVG→FVG→OB, bonus+0.30
  CSF: CHOCH→Sweep→FVG, bonus+0.50

Bronze (skip or marginal):
  CO: CHOCH→OB, bonus+0.15
  OO: OB→OB, bonus+0.05
  SS: Sweep→Sweep, bonus-0.10

**Match algorithm**: Longest substring first. Priority: length > bonus.

### Layer 3: Composite Score

score = 0.50(base) + pattern_bonus + timing_penalty + cluster_bonus + separation_bonus

Timing penalty by distance from last preceding signal:
  ≤3 bars: +0.05 (tight confirmation)
  4-8 bars: 0.00 (acceptable)
  9-15 bars: -0.05 (decaying)
  >15 bars: -0.15 (stale)

Cluster bonus by number of preceding core signals:
  0 (isolated, fresh): 0.0
  0 (isolated, old): -0.1
  1-3: +0.05
  4-6: 0.00
  >6: -0.10

Grading: A(≥0.75) B(≥0.60) C(≥0.50) D(≥0.35) F(<0.35)

## Validation Results (200 stocks, V33)

Trades: 1,849 | WR: 71.3% | RR: 4.85x | PF: 24

Best patterns:
  OFC (OB→FVG→CHOCH): 8 trades, WR=88%, P&L=+3.25%
  SF (Sweep→FVG): 18 trades, WR=78%, P&L=+1.87%
  FF (FVG→FVG): 384 trades, WR=73%, P&L=+1.19%
  Isolated (fresh): 738 trades, WR=73%, P&L=+1.53%

## Daily A-share Limitation

73% of isolated FVGs already have 73% WR. The time-sequence scoring cannot dramatically improve global WR because:
1. 99.5% of trades exit in 1 bar (gap determines outcome)
2. SL=0.3% gets stopped by noise regardless
3. The baseline is already high

**Real value**: Identifying TOP patterns for concentrated trading, not universal WR uplift.

## Code

Module: /root/.hermes/scripts/v11/signal_timing_sequencer_v11.py
Integrated: /root/.hermes/scripts/v11/rolling_backtest_v33.py
