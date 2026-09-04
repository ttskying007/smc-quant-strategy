# V27 Signal Audit Guide

## Core Principle
**Audit before fixing. Never claim bugs without empirical evidence.**
The user corrected a session where theoretical risk was presented as confirmed bugs.
The right approach: read code → build audit script → run full scan → let data drive conclusions.

## 7-Point Audit Framework

| # | Check | What to verify |
|---|-------|---------------|
| 1 | BOS/CHOCH | Confirmed swing (right bars) + structure state machine. Break uses close beyond swing, not wick. |
| 2 | MSS | Must have sweep precursor (sweep + CHOCH + displacement), not just CHOCH from trending state. |
| 3 | OB | 100% anchor to structure event. Scans backward from event, finds nearest opposite candle. Displacement scoring only. |
| 4 | OTE | No future leak: impulse_end_idx <= event_idx. Impulse bound to prior confirmed swing. |
| 5 | BPR | opposing FVG overlap only. Must have fvg1 + fvg2 with opposite directions. Min width filter. |
| 6 | SWEEP | Confirmed swing + wick pierce + close reclaim. Not rolling high/low. |
| 7 | Data consistency | Trades/picks/chart markers all from same event ledger. No re-detection in adapter or frontend. |

## Audit Script Template

```python
# Check anchors
ob_no_anchor = [t for t in trades if not t.get('zone',{}).get('anchor_event_idx')]
bpr_no_fvgs = [t for t in bpr_trades if not (t.get('zone',{}).get('fvg1') and t.get('zone',{}).get('fvg2'))]

# Check time order
bad_order = [t for t in trades if entry_idx <= signal_idx]
zone_after_entry = [t for t in trades if zone_idx > entry_idx]
non_causal = [t for t in trades if not audit.causal]

# Check MSS sweep
mss_no_sweep = [t for t in mss_trades if not struct_event.has_sweep_precursor]
```

## Key Pitfalls Discovered

### BPR O(n²) Performance
BPR detection compares every bull FVG with every bear FVG. For stocks with 200 FVGs, that's 40k comparisons.
**Fix**: Add time window (max_gap=100 bars). Only compare FVGs within the window.
Result: 60+ min → 4.4 min for full 4905-stock scan.

### K-line vs Trade Date Format Mismatch
K-line dates: "2025-02-17" (with hyphens). Trade entry_date: "20250704" (no hyphens).
Frontend date_map must normalize both formats:
```python
d_norm = d_raw.replace('-', '')
date_map[d_raw] = i
if d_norm != d_raw: date_map[d_norm] = i
```

### Silent Exception Swallowing
`except Exception: pass` hides ALL errors in scanner loop.
**Fix**: Print first 5 exceptions, then continue silently.

### prev_trend Variable Bug
When `trend` is updated to `new_trend` before MSS check, the original trend is lost.
**Fix**: Save `old_trend = trend` before update, use in MSS condition.

### 0%500 Print Spam
When `processed=0`, `0 % 500 == 0` is True, causing infinite status prints.
**Fix**: `if processed > 0 and processed % 500 == 0:`
