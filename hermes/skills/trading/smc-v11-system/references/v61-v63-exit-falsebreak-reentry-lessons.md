# V61–V63 SMC exit/false-break/reentry gate lessons

Session context: user asked to improve SMC signal correctness and then specifically raise win rate after V60/V61 by addressing early structural exits, false break / failed retest, and REENTRY quality.

## Durable lessons

### 1. Do not globally delay structural exits
V61 tested widening / delaying structure-stop exits to address `SOLD_EARLY_BY_STRUCTURE_STOP` and low 90D MFE capture. The broad approach did not improve production quality: global structure-stop delay reduced win rate and 90D capture. Treat this as a diagnostic experiment, not a default fix.

Use structure-exit extension only after family-level proof. Broad continuation extension was negative; a small REENTRY runner bucket was locally positive but insufficient for system-level improvement.

### 2. False-break / failed-retest gates belong before entry
V62 improved quality by rejecting trades before entry rather than holding losers longer. Productive front-door gates included:

- move `PRIMARY_SETUP` to watch-only when its family WR is materially weaker
- reject `LiquidityVoid_Bull` continuation/reentry when it maps to fake continuation risk
- require no fast return to range
- require retest to hold the raw zone
- require no 1–3 bar reclaim against the breakout
- require minimum BQ by family (`CONTINUATION >= 50`, `REENTRY >= 55` in that run)

This raised V62 versus V60 on WR, average PnL, realized R, and 90D capture while reducing trade count.

### 3. REENTRY must be a second-confirmation family, not first-retouch replay
V63 showed the strongest REENTRY subset was:

- `zone_type == FVG_Bull`
- `conf_type == BOS_Bull`
- trend score `>= 4`
- breakout quality score `>= 55`

Avoid treating all REENTRY setups equally. In that run:

- REENTRY `OB_Bull` underperformed and caused many SL hits
- REENTRY `FVG_Bull + BOS_Bull` materially outperformed generic REENTRY
- CHOCH/MSS reentry confirmations were weaker than BOS in this context

Encode REENTRY as: post-exit cooling + new directional structure confirmation + FVG quality, not “first retest after exit”.

### 4. Keep version promotion end-to-end
When promoting a candidate SMC version, update all of the following together:

- engine script and output directory
- `ACTIVE_VERSION`, `ACTIVE_TRADE_FILE`, `ACTIVE_PICK_FILE`
- `get_version_trades()` / `get_version_picks()`
- `_active_version_paths()` for rerun support
- version selector / front-end labels
- closed-loop review file naming
- quality/provenance/sequence/sample-bias/release-gate scripts
- browser/API verification for summary, backtest, picks, kline, autopsy

If a front-end message says “current version does not support rerun”, the version was promoted incompletely; add it to `_active_version_paths()` and rerun route mapping.

## Verification pattern

For each candidate version:

1. Run full market backtest / transform from prior baseline.
2. Compute per-family WR/avg PnL/exit reason split.
3. Run quality metrics.
4. Run provenance audit.
5. Run sequence audit.
6. Run sample-bias audit.
7. Run 90D closed-loop review.
8. Run release gate.
9. Restart front-end and verify `/api/summary`, `/api/autopsy/closed-loop`, `/api/picks`, `/backtest`, and `/api/kline_full?...&ver=VX`.

Do not call a version production-ready from aggregate WR alone; require the audit chain plus front-end synchronization.
