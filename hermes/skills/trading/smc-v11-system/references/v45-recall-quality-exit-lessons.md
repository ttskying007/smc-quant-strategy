# V45.1–V45.3 Native SMC Recall, Quality, and Exit Lessons

## Trigger
Use this reference when continuing V45+ native K-line SMC work after a stop-loss spike or low-recall diagnosis. The durable lesson is the workflow, not the exact metrics.

## Correct workflow
1. **Do not relax correctness first.** Keep the V45 native contract: event ledger from K-line cache, no V44 trade reconstruction, no `DIRECT_SIGNAL_CLOSE`, no standalone IFVG, no expired/invalidated setup trades, entry must be inside both raw zone and execution zone.
2. **Separate the three layers:**
   - signal/sequence correctness: liquidity → structure → POI → raw retest → confirmation → armed;
   - entry correctness: raw-zone retest plus execution sub-zone, not chase;
   - exit/risk correctness: only after signal+entry contract passes.
3. **Use lifecycle watchlist for active picks.** Do not derive active picks from completed historical trades. Generate states such as `WAITING_FOR_RETEST`, `RETESTED_WAITING_CONFIRM`, and `ARMED_READY` from the setup lifecycle.
4. **When recall is too low, add legal branches, not shortcuts:** continuation branch, execution sub-zone, and strictly defined confirmation expansion are acceptable; chase/direct close/standalone IFVG are not.
5. **When SL is high, split by mechanism before changing parameters:** sequence kind, zone type, confirmation type, entry mode, market state, hold bars, MFE/MAE, gap, and post-stop rebound.
6. **Reject optimizations that improve one headline number but worsen trade quality.** An aggressive early partial-loss scheme can reduce nominal SL rate while lowering WR/avg/total; reject it if full metrics deteriorate.
7. **Prefer quality filters over exit hacks when bad branches are identifiable.** In this session, removing weak confirmation/entry branches improved quality without breaking the entry contract.

## V45.1 recall repair pattern
Implemented as an independent engine file so history remains traceable. The accepted pattern:
- native event ledger from full-market K-line cache;
- sequence compiler for `liquidity → structure → POI → raw retest → confirmation → armed`;
- continuation branch;
- execution sub-zone under raw zone;
- legal confirmation expansion;
- active watchlist generated from lifecycle state.

Validation checklist:
```json
{
  "native_from_kline_not_v44_trade_reconstruction": true,
  "entry_gate_coverage": 1.0,
  "entry_inside_raw_zone_coverage": 1.0,
  "entry_inside_execution_zone_coverage": 1.0,
  "direct_signal_close_trade_count": 0,
  "standalone_ifvg_trade_count": 0,
  "expired_setup_traded_count": 0,
  "invalidated_setup_traded_count": 0,
  "active_picks_not_historical_all_market": true
}
```

## V45.2 quality-filter pattern
After V45.1 restored recall, split results by sequence/zone/confirmation/entry mode. Remove weak branches only when the split shows durable underperformance and high SL, while preserving the same entry contract.

Example branch removals from this session:
- `PINBAR_EXEC_MID_RECLAIM` behaved like weak/fake confirmation;
- delayed `LIMIT_RETOUCH_EXEC_HIGH` behaved like second failed retest;
- `REVERSAL + FVG + TWO_BAR_REJECTION_HOLD` was weaker than continuation/FVG and bullish rejection branches.

The important reusable rule: **remove bad branches by mechanism, not by optimizing WR blindly.** Keep removed trades in a `removed_trades` file with reason counts.

## V45.3 exit/risk lesson
Only tune exits after the signal and entry layers pass. First perform SL path autopsy:
- MFE before SL;
- MAE before SL;
- whether 1R was reached before SL;
- 5/10/20-bar rebound after SL;
- sequence/zone/confirmation split.

A surprising durable lesson from this run: many FVG SLs were fake-break losses that rebounded shortly after the stop. Therefore, aggressive early partial-loss or tighter stops can reduce the nominal SL rate but worsen WR/avg/total. When that happens, reject the scheme.

Accepted conservative exit overlay:
- keep V45.2 entries/signals unchanged;
- keep structural stop;
- do not early partial-loss cut;
- move TP1 farther out with smaller partial so valid winners can run;
- arm BE only after price proves itself;
- avoid high-water trailing until later protective logic.

## Frontend/API sync pattern
For each V45.x candidate:
- write output under `/root/.hermes/smc_opt_v45_x/`;
- expose versioned bundle loading in `smc_unified.py`;
- allow `?ver=v45_1`, `?ver=v45_2`, `?ver=v45_3` while making the latest candidate default only after validation passes;
- keep `/stoploss` and `/v45` diagnostic pages separate from the legacy main dashboard;
- keep `/api/summary` fast: do not load huge full trade JSON during health checks.

## Files created in the representative session
- `/root/.hermes/scripts/v25/v45_1_recall_repair.py`
- `/root/.hermes/scripts/v25/v45_2_quality_filter.py`
- `/root/.hermes/scripts/v25/v45_3_exit_risk.py`
- `/root/.hermes/smc_opt_v45_1/`
- `/root/.hermes/smc_opt_v45_2/`
- `/root/.hermes/smc_opt_v45_3/`

These paths are session artifacts; use them as examples, not as mandatory future names.
