# V25 Data Pipeline Configuration

## File Naming Pattern

V25.5 state-adaptive backtest writes to `v255_trades.json`, but frontend's `reload_trades()` loads `v25_trades.json`:

```
/root/.hermes/smc_opt_v25/
├── v25_picks.json         ← full_scan.py writes here
├── v25_trades.json        ← backtest_v25.py writes here (simple, WR=63.3%)
└── v255_trades.json       ← state_backtest.py writes here (adaptive, WR=67.7%) ✅
```

## Correct Pipeline

```bash
# 1. Generate picks (saves to v25_picks.json)
cd /root/.hermes/scripts/v25 && python3 full_scan.py

# 2. Run state-adaptive backtest (saves to v255_trades.json)
cd /root/.hermes/scripts/v25 && python3 state_backtest.py

# 3. Copy results to v25_trades.json for frontend
cp /root/.hermes/smc_opt_v25/v255_trades.json /root/.hermes/smc_opt_v25/v25_trades.json
```

## Frontend reload_trades() Priority

```python
def reload_trades():
    t = load_json(Path('/root/.hermes/smc_opt_v25/v25_trades.json'), None)
    if t: return t
    t = load_json(Path('/root/.hermes/smc_opt_v24/v24_trades.json'), None)
    if t: return t
    # ... fallbacks
```

Step 3 is critical — without it, frontend shows stale or worse results.

## Why Two Backtest Engines

- **backtest_v25.py**: Simple exit simulation, fixed parameters, WR=63.3%. Reads from `v25_picks.json`.
- **state_backtest.py**: Adaptive by market state (TREND_UP/DOWN/HIGH_VOL/LOW_VOL/RANGE), WR=67.7%. Reads from `v25_picks.json`.

The state backtest classifies each stock at entry time into one of 5 market states and applies different SL/TP/hold parameters per state. RANGE state is skipped entirely (WR=44% in testing).
