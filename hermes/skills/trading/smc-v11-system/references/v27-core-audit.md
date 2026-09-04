# V27 Core Signal Audit Framework

## 7-Point Audit Checklist

Run after ANY modification to `smc_core_v27.py` or `v27_full_scan.py`. All 7 must pass.

```python
import json
trades = json.load(open('/root/.hermes/smc_opt_v27/v27_trades.json'))
picks = json.load(open('/root/.hermes/smc_opt_v27/v27_picks.json'))

# 1. OB anchor — every OB must have anchor_event_idx
ob_trades = [t for t in trades if t.get('zone_type') == 'OB']
assert all(t.get('zone',{}).get('anchor_event_idx') for t in ob_trades), "OB anchor missing"
assert all(t.get('zone',{}).get('anchor_event_idx', 0) <= t.get('source_event_idx', 0) for t in ob_trades), "OB anchor after event"

# 2. BPR anchor — every BPR must have both FVGs (opposing directions)
bpr_trades = [t for t in trades if t.get('zone_type') == 'BPR']
assert all(t.get('zone',{}).get('fvg1') and t.get('zone',{}).get('fvg2') for t in bpr_trades), "BPR missing FVGs"
assert all(t.get('zone',{}).get('fvg1',{}).get('direction') != t.get('zone',{}).get('fvg2',{}).get('direction') for t in bpr_trades), "BPR same-direction FVGs"

# 3. Time order — entry must be AFTER signal
assert all(t.get('entry_index', 0) > t.get('signal_index', 0) for t in trades), "entry <= signal"

# 4. Zone order — zone must exist at or before entry
assert all(t.get('zone_idx', 0) <= t.get('entry_index', 0) for t in trades), "zone > entry"

# 5. Causal — must have audit.causal flag
assert all(t.get('audit',{}).get('causal') for t in trades), "non-causal"

# 6. MSS sweep prerequisite — every MSS struct_event must have has_sweep_precursor
mss = [t for t in trades if t.get('struct_event',{}).get('type') == 'MSS']
assert all(t.get('struct_event',{}).get('has_sweep_precursor') for t in mss), "MSS missing sweep"

# 7. Picks state — V27 picks must have state field
assert any(p.get('state') for p in picks), "Picks missing state field"

print("ALL 7 CHECKS PASSED")
```

## Key Metrics Reference (V27.1 Baseline)

```
Trades:  47,448  (4,556 unique stocks)
WR:      59.7%
Avg PnL: +6.44%
RR:      3.69x

Zone:    OB=34,445 (WR=60.8%) | OTE=8,971 (WR=60.5%) | BPR=4,032 (WR=49.2%)
Exit:    TP_HIT=59.5% | SL_HIT=40.2% | TIMEOUT=0.3%
Picks:   6,934 ACTIVE | 17,368 HISTORICAL
```

## V27 Core Architecture

```
confirmed_swings(left=3, right=3)
    ↓
structure_signals (state machine: bullish/bearish/unknown)
    ├── BOS: continuation (same trend)
    ├── CHOCH: reversal (opposite trend)
    └── MSS: CHOCH + sweep precursor + trending prev_state
    ↓
fvg_list → bpr_signals (opposing FVG overlap, 100-bar window, min_width 0.5%)
sweep_signals (confirmed swing + wick pierce + close reclaim)
ob_signals (event-anchored backward scan, displacement=scoring only)
ote_signals (impulse-bound, no future scanning, fib 0.62-0.79)
po3_signals (accumulation → sweep → structure event)
    ↓
build_bullish_setups (event → zone → retrace → PINBAR confirm → T+1 entry)
backtest_setups (SL/TP check, 60-bar timeout)
```

## Performance: BPR O(n²) → O(n×k)

BPR detection compares all bull FVGs × all bear FVGs. Original O(n²) was >60 min for 4905 stocks.

Fix: 100-bar time window — only compare FVGs within ±100 bars:
```python
nearby_bears = [brf for brf in bear_fvgs if abs(brf['index'] - bf_idx) <= max_gap]
```

Result: 4905 stocks in 261.8s (~4.4 min).

## Common Pitfalls

### `prev_trend` NameError
In `structure_signals()`, trend is updated to `new_trend` before MSS check. The original value is lost. Fix: save `old_trend = trend` before update, use `old_trend` in MSS check.

### `except Exception: pass` Hides Errors
`v27_full_scan.py` main loop catches all exceptions silently. First 5 stocks print errors, rest are swallowed. This hid the `prev_trend` NameError. Fix: print first 5 errors then continue silently for the rest.

### 0 % 500 == 0 Print Spam
Progress line fires on every iteration when processed=0. Fix: `if processed > 0 and processed % 500 == 0`.

### Empty Metrics Crash
`compute_metrics([])` returns `{'n_trades': 0}` without 'wr' key. Fix: handle empty case with safe dict.
