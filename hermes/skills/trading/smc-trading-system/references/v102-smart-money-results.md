# V10.2 Smart Money Engine — Definitive Results (2026-05-15)

## Final Performance

```
878 stocks / 4905 | 1,839 trades | WR=84.2% | PnL=+9.81%
SL=2.45% (0.5-2% adaptive + 3-8% structural)
Hold=5.1 bars | TP=63.5% | 2024-05 ~ 2026-05
```

## Signal Comparison (V9 vs V10.2)

| Signal | V9 trades | V9 WR | V10.2 trades | V10.2 WR | Verdict |
|--------|:---------:|:-----:|:------------:|:--------:|---------|
| OB_Bull | 4,848 | 85.3% | 1,220 | 82.5% | ✅ Core signal |
| Sweep_SSL | 3,771 | 70.6% | 619 | 87.4% | ✅ Confirmed by V10 |
| FVG_Bull | 4,175 | 49.6% | removed | — | ❌ Fill rate too high |
| BOS_Bull | 2,656 | 41.9% | removed | — | ❌ Not standalone |
| CHOCH_Bull | 1,558 | 59.4% | removed | — | ❌ Insufficient n |

V9 total: 17,008 trades, WR=64.1%, PnL=+4.19%
V10.2 total: 1,839 trades, WR=84.2%, PnL=+9.81%
→ 11x fewer trades, 2.3x higher PnL per trade. Quality over quantity.

## SMC Context Methodology

### The LIQ→CHOCH→OB Sequence

The SMC (Smart Money Concepts) standard entry sequence:
1. **LIQ Sweep**: Price sweeps below a swing low (SSL) or above a swing high (BSL) — this is the "liquidity grab"
2. **CHOCH/BOS**: The market structure breaks — a Change of Character or Break of Structure confirms the reversal
3. **OB Entry**: An Order Block forms at the reversal point — this is the entry zone
4. **Retest**: Price returns to the OB zone — this is the optimal entry
5. **Entry**: Enter at the OB zone lower boundary

### Context WR Gradient (AI Analysis)

Analysis of 1,000 randomly sampled trades from V9:

| SMC Context Elements | WR |
|:---------------------|:--:|
| 0 (isolated signal) | 42.3% |
| 1 element | 64.3% |
| 2 elements | 79.4% |
| 3 elements | 87.3% |
| 4 elements | 92.0% |

Context elements checked: LIQ sweep (Sweep_SSL/BSL), Structure break (CHOCH/BOS), At swing point, FVG nearby.

### Implementation in V10.2

```python
SIGNAL_REQUIREMENTS = {
    'OB_Bull': {
        'require_context': True,
        'context_types': ['Sweep_SSL','Sweep_BSL','CHOCH_Bull'],
        'context_window': 10  # bars before signal
    },
    'Sweep_SSL': {
        'require_zone': True,
        'zone_types': ['OB_Bull'],
        'zone_window': 5  # bars after signal
    },
}
```

### Why FVG/BOS/CHOCH Failed

- **FVG_Bull**: Daily FVG (Fair Value Gap) gets filled too quickly on A-shares. Fill rate >50% on most stocks. Even with SMC context, WR only reaches 64% (zone_FVG_Bull context).
- **BOS_Bull**: Break of Structure alone doesn't provide an entry zone. It confirms the trend but the entry needs an OB or FVG. As standalone: WR=41.9%.
- **CHOCH_Bull**: Change of Character has too few samples to be statistically significant. Only 15-97 trades in full backtest.

## 60min Entry Paradox

AI analysis of OB_Bull entries by source:

| Entry Source | Trades | WR | avg PnL |
|:-------------|:------:|:--:|:-------:|
| Daily direct | 3,132 | 99.4% | +9.69% |
| 60min precise | 1,716 | 59.7% | +6.02% |

**Explanation**: OB signals detected on daily charts represent genuine institutional order blocks. When zooming into 60min, noise (market microstructure) creates false signals that appear to be OBs but aren't. The daily timeframe filters out this noise naturally.

**Recommendation**: Use daily entries exclusively. 60min data only for visualization.
