# V21 max_age Trap (2026-05-18)

## Discovery

V21 engine (built from V18 base) produced 844 trades vs V19's 203. User: "是放宽了什么限制吗，选股多出来很多"

## Root Cause

V18's `max_age` was `regime_params.get('max_age', 120)` — defaulting to 120 bars for ALL regimes. V19 had per-regime caps:

| Regime | V19 max_age | V21(original) | Impact |
|--------|-------------|---------------|--------|
| HIGH_VOLATILITY | 100 | **120** | +20% stale zones |
| RANGING | 50 | **120** | +140% stale zones |
| STRONG_TREND_UP | 100 | **120** | +20% |
| WEAK_TREND_UP | 40 | **120** | +200% |

V21 inherited V18's loose parameter because V18's `MarketRegime.get_sltp_params()` was designed for SL/TP params, not `max_age`. The default 120 allowed 6-month-old zones.

## Fix

```python
# V21 fix: per-regime max_age
max_age_map = {'HIGH_VOLATILITY': 60, 'RANGING': 30, 'STRONG_TREND_UP': 60, 'WEAK_TREND_UP': 30}
max_age = max_age_map.get(regime, 40)
```

## Result

| | Before | After |
|---|--------|-------|
| Trades | 844 | 445 (-47%) |
| WR | 91.8% | 87.6% |
| avgPnL | +11.65% | +11.31% |

WR dropped because many filtered trades were actually profitable — but they were based on stale zones that shouldn't be traded in realtime.

## Lesson

When building a new engine from an old base, check ALL filtering parameters, not just the entry logic. `regime_params` from `MarketRegime.get_sltp_params()` does NOT set `max_age` — this field must be explicitly defined per-engine.
