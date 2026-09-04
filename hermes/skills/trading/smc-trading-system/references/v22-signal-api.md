# V22 Signal API Quick Reference

## Import and Call

```python
from v11.signals_v22 import detect_all_signals_v22

all_sigs, summary, swings, swings_dict = detect_all_signals_v22(ohlcv_data)
```

Returns a 4-tuple:
- `all_sigs`: list of `Signal` objects (all 16 signal types merged, sorted by `.idx`)
- `summary`: dict with `total_signals`, `type_counts`, `swing_highs`, `swing_lows`, `swings`
- `swings`: list of `SwingPoint` objects
- `swings_dict`: dict with `highs` and `lows` lists

## Signal Class (dataclass-like, NOT dict)

```python
class Signal:
    type: str          # e.g. 'OB_Bull', 'CHOCH_Bull', 'Sweep_SSL'
    idx: int           # bar index (0-based, last bar = len(ohlcv)-1)
    direction: str     # 'bull', 'bear', or 'neutral'
    price: float
    upper: float       # zone top / signal high bound
    lower: float       # zone bottom / signal low bound
    strength: float    # 0-10 scale
    confidence: float  # 0.0-1.0
    timeframe: str     # 'daily'
    confirmed_at: int
    volume_ratio: float
    grade: int
    trend_aligned: bool
    metadata: dict
```

**CRITICAL**: Access fields as ATTRIBUTES, not dict keys:
```python
# ✓ CORRECT:
s.type, s.idx, s.upper, s.lower, s.confidence

# ✗ WRONG (will raise TypeError):
s['type'], s['idx'], s['upper'], s['lower']
```

## OB Signal Zone Bounds

For `OB_Bull` (demand zone):
- `s.upper` = OB high (top of demand zone)
- `s.lower` = OB low (bottom of demand zone, the cost basis)

For `OB_Bear` (supply zone):
- `s.upper` = OB high
- `s.lower` = OB low (top of supply zone)

## Signal Types (16 total)

| Type | Description |
|------|-------------|
| `FVG_Bull`, `FVG_Bear` | Fair Value Gap |
| `IFVG_Bull`, `IFVG_Bear` | Inverse FVG |
| `OB_Bull`, `OB_Bear` | Order Block (LuxAlgo + SMC2026 merged) |
| `BPR_Bull`, `BPR_Bear` | Breaker |
| `CHOCH_Bull`, `CHOCH_Bear` | Change of Character |
| `BOS_Bull`, `BOS_Bear` | Break of Structure |
| `Sweep_SSL`, `Sweep_BSL` | Liquidity Sweep |
| `MSS_Bull`, `MSS_Bear` | Market Structure Shift |
| `EQL_High`, `EQL_Low` | Equal High/Low |
| `OTE_Bull`, `OTE_Bear` | Optimal Trade Entry |
| `BreakerBlock_Bull`, `BreakerBlock_Bear` | Breaker Block |
| `LiquidityVoid` | Liquidity Void |
| `Rejection_Resistance`, `Rejection_Support` | Rejection Block |
| `PO3_Acc`, `PO3_Man`, `PO3_DIS` | Power of 3 |
| `Pinbar_Bull`, `Pinbar_Bear` | Pinbar |

## V13 Engine Entry Point

```python
from v11.v13_engine import run_full
result = run_full()  # runs all 4905 stocks, saves JSON+CSV
```

Config in v13_engine.py top:
- `V13_MAX_AGE = 120` — zone max age in bars (user accepts all: 40/60/80/100/120/200)
- `V13_REQUIRE_CHOCH = False`
- `V13_ALLOW_PO3 = False`
