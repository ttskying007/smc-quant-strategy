# V183-V185 post-V175 research closure

Date: 2026-06-25

## Trigger
Use when continuing post-V175 SMC research after V177-V182, especially if deciding whether to keep iterating on V128/V167/V175 filters, V175 exits, or fresh generators.

## Predeclared usable gates

Production upgrade usable:
- non-leaking source-side rule;
- T+1 violations = 0;
- combined engine `n >= 260`;
- `min_year_n >= 40`;
- `WR >= 84%`;
- `AvgPnL >= 6.2%`;
- `all_year_WR_min >= 82%`;
- `micro_profit_pct <= 1%`;
- no frontend/watchlist/API mutation before dry-run passes.

Research child engine usable:
- 100% non-overlap vs V175;
- `n >= 120`;
- `min_year_n >= 20`;
- `WR >= 86%`;
- `AvgPnL >= 6.5%`;
- `all_year_WR_min >= 83%`;
- T+1 violations = 0.

## V183 fresh reversal lifecycle generator

Artifact: `/root/.hermes/smc_audit/v183_fresh_context_lifecycle_generator_20260625_155910/`

Source: raw daily K-line cache only, no V128/V167/V172/V175 filtering.

Rule architecture:
`environment -> SSL sweep -> CHOCH -> demand OB POI -> touch -> reclaim -> next-open entry -> T+1 exit`.

Result:
- Decision: `V183_FRESH_GENERATOR_NO_GATE_PASS__NO_WRITE`.
- Scanned 4,646 symbols, raw setups 629.
- Best variant `v183_rr2p2_hold40`: `n=362`, `WR=38.12%`, `Avg=0.8866%`, `SL=60.50%`, `T+1=0`, overlap vs V175 = 0.
- Combined with V175 remains unusable: WR only ~56.65%, Avg ~2.98%.

Conclusion: classical-looking SSL sweep -> CHOCH -> demand reclaim, when rebuilt from raw K-lines, is still mostly a false-positive reversal generator. The failure is signal-layer quality, not exit layer.

## V184 fresh continuation HOLD generator

Artifact: `/root/.hermes/smc_audit/v184_fresh_continuation_hold_generator_20260625_160355/`

Source: raw daily K-line cache only.

Rule architecture:
`bullish structure continuation -> BOS -> narrow demand POI -> pullback touch -> HOLD_ABOVE_POI takeover -> next-open entry -> T+1 exit`.

Result:
- Decision: `V184_NO_GATE_PASS__NO_WRITE`.
- Scanned 4,643 symbols, raw setups 5,808.
- Best variant `v184_rr2p2_h40`: `n=1777`, `WR=37.54%`, `Avg=0.3240%`, `SL=62.41%`, `T+1=0`, overlap vs V175 = 0.
- Combined with V175: `n=2024`, `WR=43.18%`, `Avg=1.0227%`, unusable.

Conclusion: simple BOS + narrow POI + hold-above-POI is not enough. It expands coverage but destroys quality; high false-positive SL rate proves the missing piece is not just continuation vs reversal, but stricter source-side smart-money takeover semantics.

## V185 V128 augmented source-feature frontier

Artifact: `/root/.hermes/smc_audit/v185_v128_augmented_source_feature_frontier_20260625_161758/`

Source: V128 shadow rows plus newly computed pre-entry K-line geometry features. No outcome/leak fields were allowed in rule predicates.

Added pre-entry features included:
- `pre_ret5/10/20`, `pos20/60`, `dist20h/60h`, `range20/60`, `higher_low_pct`, `vol_ratio20_60`, `entry_gap_prev_close_pct`.

Fast frontier search over semantic seeds and 1-2 geometric/source rules produced:
- Decision: `V185_NO_GATE_PASS__NO_WRITE`.
- Candidate count retained after frontier thresholds: 0.

Conclusion: the earlier V180 closure was not materially overturned by adding simple pre-entry K-line geometry. V128 is not hiding an obvious production child behind these source-side scalar/geometric gates.

## V186 breadth context probe

Artifact: `/root/.hermes/smc_audit/v186_breadth_context_probe_20260625_162632/`

Source: V183/V184 fresh candidates plus raw K-line market breadth computed by date. Breadth was attached at pre-entry confirmation date (`hold_date` or `reclaim_date`), not after trade outcome.

Result:
- Decision: `V186_BREADTH_CONTEXT_NO_GATE_PASS__NO_WRITE`.
- Breadth dates built: 693; enriched candidate rows: 2,139.
- Best rule: `v184_rr2p2_h40_rows.csv AND up1_pct>=55 AND riskoff_pct<=15`.
- Best child: `n=377`, `WR=49.34%`, `Avg=1.5071%`, `T+1=0`, overlap vs V175 = 0.
- Combined with V175: `n=624`, `WR=62.98%`, `Avg=3.3051%`, `all_year_WR_min=59.84%`.

Conclusion: broad market context improves the failed fresh continuation generator (about 37% WR -> 49% WR in the best simple breadth bucket), but it is still far below research/production gates. Breadth alone is not the missing qualitative engine.

## Closed directions after V177-V186

Closed:
1. Generic executable exit overlays on V175.
2. V175 TIME-row 60min production claim with current historical coverage.
3. V128 existing scalar/source filters.
4. Delayed V128 takeover confirmation.
5. V167 leftover as non-overlap child engine.
6. Runner exits on the best V167 leftover child.
7. Fresh raw-Kline reversal lifecycle generator using SSL sweep -> CHOCH -> demand reclaim.
8. Fresh raw-Kline continuation generator using BOS -> narrow POI -> HOLD_ABOVE_POI.
9. V128 augmented simple pre-entry K-line geometry frontier.
10. Simple market-breadth filters on the failed V183/V184 fresh generators.

Still valid/current:
- V175 remains the verified production artifact: `n=247`, `WR=83.81%`, `Avg=6.0493%`, `min_year=38`, T+1=0, semantic label repaired.
- V175 active picks were observed slightly stale relative to latest V128 snapshot (26 physical vs 27 read-only recompute), but this is an active-materialization sync task, not a new strategy-quality discovery.

## Next research direction

Do not keep adding scalar filters or generic exits.

The next qualitative research must rebuild the candidate generator around a stronger, explicit source-side story not yet tested by V183/V184:

1. **Market/sector breadth context first**: broad demand permission before single-stock POI. V183/V184 used stock-only context and failed.
2. **Post-entry/near-entry source semantics before entry**: require constructive takeover evidence that is not simply touch/reclaim or hold-above-POI, e.g. sequential HH/HL after reclaim before next-open entry, or failed supply absorption with volume/range contraction.
3. **Target geometry before entry**: candidate creation should require reachable BSL/structure target geometry with enough distance and not rely on fixed RR after the fact.
4. **Separate continuation and reversal generators** with independent gates; do not mix them into one umbrella story.

Operational next step:
- Build V186 as a shadow-only generator that adds market/breadth context and pre-entry target geometry before candidate creation. If breadth data is unavailable historically, first create a breadth-cache feasibility audit; do not claim production from stock-only rules again.
