# Candidate-to-Production Gap Pattern: Anti-SL Gate Not Deployed

When a verified SL-reduction solution exists as a candidate but live trading still triggers SL, check whether the candidate was ever integrated into the production pipeline.

## Pattern: The V71 Case

| Layer | Result | Status |
|-------|--------|--------|
| V66 production backtest | 137 trades, WR=90.51%, SL=12 (8.76%) | ✅ Running |
| V71 anti-live-SL gate | 62 trades, WR=98.39%, SL=0 (0%) | ✅ **Verified as candidate only** |
| Live monitor positions | 7 positions, 4 with ENTRY_ABOVE_ZONE_HIGH | 🔴 **At risk** |

**Gap**: V71 rules exist in `v71_anti_live_sl_gate.py` as a standalone script but are **never called** by the production daily-scan/monitor pipeline in `smc_unified.py`.

## How the Gap Forms

1. A problem is identified (live SL rate too high)
2. A candidate fix is designed and verified in isolation (V71: 62 trades, 0% SL)
3. The candidate is marked "candidate — don't replace production"
4. **No integration task is created** to move the candidate rules into the production pipeline
5. The candidate exists as a static data file (`smc_opt_v71/v71_picks.json`) but the daily scanner and monitor keep using V66 rules
6. Live positions continue to have the original problems (entry above zone, SL at zone_low)

## Diagnostic: Check for This Gap

```python
# In the production code (smc_unified.py), search for:
- Any anti_live or sl_gate string
- MAX_ENTRY_ABOVE_ZONE_HIGH_PCT or similar constants
- A production_gate field on API output
- V71 being referenced in the daily-scan path

# If none found, the verified candidate has NOT been deployed.
```

## Production Integration Checklist

| Check | What to look for |
|-------|-----------------|
| Constants | Are V71's thresholds (0.8%, 1%, 6%, 2.5%) present in smc_unified.py? |
| Gate function | Is there a `pass_production_gate(t)` or similar called per pick? |
| API field | Does `/api/live-prices` have a `productionGate` / `production_gate` field per pick? |
| Monitor creation | When `build_monitor` creates a new position, does it run SL risk checks? |
| Reject path | Are rejected trades written to a monitor-visible reject list? |

## Priority

This is **P0** if live positions currently show ENTRY_ABOVE_ZONE_HIGH violations. The gap means the verified fix is not protecting live trading, and the next SL loss was preventable.

## Integration Pattern for Future Anti-X Gates

When designing any gate (anti-SL, anti-drawdown, anti-gap), immediately add:

1. The gate function in the same file as the production pipeline (smc_unified.py), not a standalone script
2. A per-pick `productionGate` field written to the live API
3. A monitor-page column showing gate status
4. Rejected trades go to a visible reject list
