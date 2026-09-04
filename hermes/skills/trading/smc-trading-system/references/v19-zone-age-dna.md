# V19.1 Zone Age Analysis & Stock DNA

## Zone Age Impact (2026-05-16)

Analysis of 295 V19 trades revealed zone_age as the #1 failure predictor:

| zone_age | Trades | WR | Avg PnL |
|----------|--------|-----|---------|
| 1 | 232 | 91% | +5.83% |
| 2 | 39 | 100% | +7.21% |
| 3 | 10 | 90% | +9.94% |

**82% of losing trades had zone_age=1** (18/22 losses).
zone_age=1 means the OB was just formed on the previous bar — no price history to confirm the zone holds.

### Filter Applied

```python
# At entry point (j = ob_idx + 1 for zone_age=1):
if j == ob_idx + 1:
    if lows[j] < dz_low:  # Zone breached on entry bar
        continue  # Skip this setup
```

Filter eliminated 23 risky trades → **WR 92.5%→97.1%, losses 22→8**.

## Stock DNA Structure

Each stock in `/root/.hermes/smc_opt_v19/stock_dna.json`:

```json
{
  "000001.SZ": {
    "trades": 1,
    "won": 1,
    "wr": 100.0,
    "avg_pnl": 5.5,
    "avg_atr": 3.2,
    "avg_hold": 8.0,
    "avg_zone_age": 2.0,
    "best_regime": "HIGH_VOLATILITY",
    "best_seq": "OB→CH→IDM",
    "best_seq_pnl": 5.5,
    "seqs_won": {"OB→CH→IDM": 1},
    "seqs_lost": {},
    "avg_v19": 7.0,
    "fail_reasons": {},
    "fail_count": 0
  }
}
```

## Key DNA Aggregations

- **Best regime**: HIGH_VOLATILITY (207/283 stocks, 73%)
- **Best sequence**: OB→CH→IDM (116 stocks, avg PnL +5.8%)
- **Highest PnL sequence**: LIQ→OB→CH→IDM (9 stocks, avg PnL +11.2%)
- **Most dangerous combo**: STRONG_TREND_UP + OB→CH→PB→IDM (100% failure rate)
- **WR distribution**: 261 stocks at 100% WR, 20 below 50%
