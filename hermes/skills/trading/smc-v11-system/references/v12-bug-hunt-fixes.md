# V12 Bug Hunt & Fixes (2026-05-11)

## What Was Found

Three bugs discovered in `signals_v12.py` during 60min 200-stock evaluation:

### 1. Doji terminates impulse prematurely (line 253-256)

```python
# ORIGINAL BUG:
elif phase == 'impulse':
    if is_bull:
        impulse_len += 1
        continue
    elif is_bear:
        ob_idx = bi
        break
    else:
        # doji — treat as end of impulse
        ob_idx = bi
        break

# FIX:
else:
    # doji — count as impulse extension, keep scanning backward
    impulse_len += 1
    continue
```

**Impact**: On 60min data where doji bars are common (~15-25% of bars), doji in the impulse phase was incorrectly treated as the OB bar. This truncated the impulse search, producing too many `impulse_len=1` candidates that were then filtered by `impulse_len < 2`.

### 2. Impulse_len filter too strict (line 258)

```python
# ORIGINAL:
if ob_idx is None or impulse_len < 2:
    continue

# FIX:
if ob_idx is None or impulse_len < 1:
    continue
```

**Impact**: Many valid swing-backward OB scans found the structure (bear pullback → bull impulse → bear OB) but only counted 1 impulse bar because the sequence was BULL→doji (doji terminate) or BULL→BULL→bear (bear terminates impulse, not counted). Dropping to `< 1` lets single-bar impulses through — essential for 60min data where clean 2-bar impulses are rare.

Empirical on 600997.SH (200 bars 60min): out of 12 swing highs, 7 produced impulse_len=1 (previously rejected), only 5 produced impulse_len>=2.

### 3. Walrus operator causes hybrid pass to ALWAYS run (line 398)

```python
# ORIGINAL BUG:
if swing_mode := 'hybrid':   # := is assignment, always truthy

# FIX: Deleted entirely (removed hybrid pass, replaced with constrained forward fallback)
```

**Impact**: `swing_mode` assigned 'hybrid', expression evaluates to 'hybrid' (truthy), so the hybrid pass always executed. On 600997.SH: only 5 swing-backward OBs, but 18 hybrid-forward OBs — **78% of OBs from buggy per-candle scan**.

The hybrid-forward pass is the same V11-style per-candle forward scan that causes OB position offset of 2-5 bars. This is the root cause of V12 WR=17.5%.

## Fix Applied: Constrained Forward Fallback

Hybrid pass deleted and replaced with a constrained forward pass that only activates when swing-backward finds < 3 OBs (indicating insufficient coverage for 60min data).

### Constrained Forward Rules (stricter than old hybrid):

| Rule | Value | Rationale |
|------|-------|-----------|
| Activation | Only if swing-backward < 3 OBs | Preserve swing-backward as primary |
| Positional check | Within 8 bars of a swing point | Position validation |
| body_pct | >= 0.3 | Stricter than backward's 0.15 |
| displacement_ratio | >= 1.0 | Reduced for 60min noise tolerance |
| Impulse position | Must start at i+1 (next bar) | Position correction — verifies OB candle is BEFORE impulse, not inside it |
| min impulse bars | >= 1 | Single-bar impulse sufficient |

### Key Design Difference from Old Hybrid:

Old hybrid scanned every candle with displacement + near-swing check. New constrained forward additionally requires:
- Body >= 0.3% (filters doji)
- Impulse MUST start on i+1 (this is the critical position fix — ensures the OB candle is truly the LAST opposite candle before the impulse, not somewhere inside it)

## V11 vs V12 Direct Comparison

Backtest on same 200 stocks 60min with identical entry/exit (simple FVG+OB + V467 trailing):

| Metric | V11 | V12 | Change |
|--------|:---:|:---:|:------:|
| Tradable | 200/200 | 197/200 | -3 |
| Trades | 1429 | 1147 | -20% |
| WR | 9.7% | 27.2% | +17.5pp (3x improvement) |
| P&L | +1371% | +1510% | +10% |

V12's swing-backward OB filtering eliminates noise trades that V11's per-candle scan produces. 3x WR improvement validates that swing-backward OB positioning is genuinely better.

## Key Insight: 60min Signal Characteristics

All signal engines (V11, V12) produce low WR (10-27%) with the simple FVG+OB+trailing setup on 60min. This is because:
- 60min data has more noise bars (15-25% doji)
- ICT swing-backward structure (bear→bull→bear) is rarer in intraday data
- The simple entry needed the full V467 pipeline (sequence resonance, reversal OB, POI entry) to reach WR=82%

V12 is the better engine for 60min — but it needs the full V467 filtering pipeline, not just raw signal + exit.

## Files Created

- `/root/.hermes/scripts/v11/backtest_compare.py` — Dual-engine (V11/V12) backtest with identical entry/exit, SWITCH toggle at line 13
- `/root/.hermes/scripts/v11/signals_v12.py` — Fixed (doji fix + impulse_len < 1 + constrained forward fallback)
- `scripts/compare_signals_v12_vpine.py` — Signal count comparison diagnostic
