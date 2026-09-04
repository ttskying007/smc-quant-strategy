# V183-V185 old-pool frontier closure and V186 generator direction

Date: 2026-06-25

## Trigger

Use when continuing SMC research after V175 semantic split and V180-V182 closure, especially if the user asks whether to keep filtering V85/V128/V167/V175 pools or to define the next research direction.

## Predeclared gates

Production upgrade usable:
- non-leaking source-side rule only;
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

Unusable:
- outcome leakage (`exit_reason`, realized PnL, MAE/MFE, hit flags, final hold outcome, etc.);
- any T+1 violation;
- higher WR by cutting AvgPnL or adding BE/micro-profit pollution;
- 60min production claim with insufficient historical coverage;
- simply relabeling/filtering V167/V172/V175/V85 rows;
- single-year concentration or insufficient `min_year_n`.

## Completed audits

### V183 — V85 non-overlap frontier search

Artifact: `/root/.hermes/smc_audit/v183_v85_new_generator_frontier_20260625_230012/`

Input:
- V175 baseline: `n=247`, `WR=83.81%`, `Avg=6.0493%`, T+1=0.
- V85 non-overlap 2023-2026: `n=23303`, `WR=64.47%`, `Avg=0.5597%`, T+1=0.

Search:
- retained rules: `2861`;
- production pass: `0`;
- child pass: `0`.

Best rule:

```text
target_rr >= 5 AND v85_zone_width_pct >= 1.5
```

Metrics:
- child: `n=172`, `WR=73.26%`, `Avg=8.3387%`, `min_year_n=12`, `all_year_WR_min=66.67%`, micro=0, T+1=0.
- combined with V175: `n=419`, `WR=79.47%`, `Avg=6.9891%`, `min_year_n=59`, `all_year_WR_min=77.42%`, micro=0.72, T+1=0.

Decision: `V183_NO_USABLE_V85_FRONTIER__NO_WRITE`.

Mechanism conclusion: high target RR raises Avg but does not prove signal quality. Failures remain POI close-break / structure damage and year stability is below gate.

### V184 — high-RR continuation failure-bucket autopsy

Focus pool:

```text
V85 non-overlap
AND CONTINUATION_EXPANDED_HOLD_ABOVE_POI
AND target_rr >= 4
```

Pool metrics:
- `n=739`, `WR=70.64%`, `Avg=5.5236%`, `min_year_n=74`, `all_year_WR_min=64.86%`.

Exit mix:
- `TAKE_PROFIT_LIQUIDITY_TARGET=514`;
- `EXIT_POI_CLOSE_BREAK=179`;
- `EXIT_TREND_STRUCTURE_DAMAGE=40`;
- `TIME_STOP_NO_SEMANTIC_EXIT=6`.

Notable buckets:
- `BULL_CONTINUATION`: `n=404`, `WR=72.28%`, `Avg=5.6221%`.
- `RECOVERY`: `n=262`, `WR=70.23%`, `Avg=5.8767%`.
- `target_rr 5-6`: `n=137`, `WR=80.29%`, `Avg=6.109%`, but yearly WR still below gate.
- `zone_width 1.5-1.75`: `n=92`, `WR=73.91%`, `Avg=6.7745%`, still below WR/year stability.

Decision: no static pre-entry geometry bucket reaches production or research-child gates.

Mechanism conclusion: the issue is not RR. The missing proof is whether the POI is real demand before entry.

### V185 — delayed survival entry probe

Artifact: `/root/.hermes/smc_audit/v185_delayed_survival_entry_probe_adhoc/`

Hypothesis tested:

> If high-RR continuation fails because POI breaks after entry, wait 0-5 bars and require survival/hold before buying.

Modes:
- `close_above_zh`;
- `low_above_zl`;
- `close_above_zl`;
- `higher_lows`.

Best results still failed:
- wait=0, `higher_lows`: `n=394`, `WR=50.00%`, `Avg=-0.0163%`, `min_year_n=39`, `all_year_WR_min=37.50%`.
- wait=0, `close_above_zl`: `n=389`, `WR=49.87%`, `Avg=-0.0863%`.
- wait=1, `higher_lows`: `n=180`, `WR=56.11%`, `Avg=-0.1653%`.
- wait=3, `close_above_zh`: `n=222`, `WR=57.66%`, `Avg=-0.7409%`.

Decision: delayed survival entry is not a fix. It destroys the original high-RR edge and still does not eliminate POI breaks.

## Closed paths

Do not continue these unless a materially new input source is introduced:

1. More scalar filters over V175/V172.
2. Generic exit overlays on V175.
3. 60min historical production exits with current low coverage.
4. V167 leftover child engine.
5. Waiting extra daily bars after V128/V85 reclaim.
6. Simple fixed runner exits.
7. V85 high-RR continuation filtering.
8. Delayed survival entry after the existing V85 entry.

## Next direction: V186

The next qualitative-change path is a **new candidate generator**, not another filter over old pools.

V186 should generate from source in this order:

```text
Environment → structure advance → pullback POI → demand absorption/acceptance → second advance → candidate entry → semantic exit
```

Research focus:
- prove demand validity before candidate creation;
- distinguish true demand absorption from ordinary pullback survival;
- require continuation structure to advance after POI acceptance, not just touch/reclaim;
- rebuild reversal separately rather than reusing weak SSL/CHOCH buckets;
- keep target geometry as a constraint but not as evidence of quality;
- enforce T+1 by construction.

## Practical workflow for future sessions

1. Start from fresh kline/cache source, not historical trade files.
2. Create V186 as shadow-only; write to `smc_audit/` or `smc_opt_v186_*` only after dry-run naming clearly marks no production write.
3. Run unit tests for no outcome-field usage and T+1 construction before full scan.
4. Evaluate against the gates above.
5. If V186 fails, classify by semantic exit buckets before proposing another mechanism.
6. Do not mutate frontend/watchlist/API until the production gate passes and a separate sync audit is planned.
