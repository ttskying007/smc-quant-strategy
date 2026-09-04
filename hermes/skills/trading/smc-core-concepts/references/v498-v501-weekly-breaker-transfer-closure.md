# V498–V501 Weekly Breaker → Daily Transfer closure

Use when continuing pure-structure SMC research after weekly BOS-demand and weekly FVG-demand transfers are closed.

## Frozen ontology

1. Aggregate raw local daily bars into completed ISO weeks.
2. Confirm a unique 2-left/2-right weekly swing low, visible only at pivot+2.
3. Require a later weekly bearish BOS close below that visible low by 0.3%.
4. Scan backward at most 6 completed weeks from the bearish BOS for the nearest bullish candle; its `[min(open,close), high]` is the failed bearish OB.
5. Require a later weekly close above the OB high within 20 weeks, activating the OB as a bullish breaker.
6. Only after the completed activation week: first daily overlap touch → later close reclaim above breaker → later hold above breaker → next-session open.
7. SL is breaker low×0.99; target is the nearest weekly swing high already confirmed by hold; time30, fee 0.2%, conservative SL on collision, strict T+1.
8. One position per symbol; suppress overlapping entries. No threshold, exit, year, or regime search (`search_count=1`).

## Replay implementation pitfall

Do **not** clone a generic seed-by-seed replay and treat every semantic seed as an independent trade. A symbol may have several overlapping weekly Breaker identities while an earlier position is still open. That inflates closed trades (for example, an unsuppressed run can report about 66k trades instead of the valid serial 50,605) and changes WR/payoff/PF. The executable replay must sort candidates by entry date per symbol, accept the earliest eligible entry, suppress every later entry whose date is not strictly after the accepted trade's exit date, and report `overlapping_entries_suppressed`. The independent chronology audit must recompute this invariant in addition to T+1 and metric equality. Semantic seed count is not executable trade count.

## Verified evidence

- 4,897 symbols; 67,684 semantic seeds.
- Independent raw-bar Oracle: 67,684/67,684 pass; zero mismatches and zero forbidden outcome headers.
- Serial strict-T+1 closed trades: 50,605; 15,767 overlapping entries suppressed.
- Aggregate: gross WR 68.1889%, net≥0.8 WR 56.7770%, AvgNet +0.3668%, payoff 0.5641, PF 1.1224, SL 26.7266%.
- 2023: n=2,334, WR 41.1311%, AvgNet -1.7481%, payoff 0.8800, PF 0.5945.
- 2024: n=19,853, WR 63.1240%, AvgNet +0.5730%, payoff 0.6987, PF 1.1504.
- 2025: n=20,899, WR 76.4247%, AvgNet +0.7410%, payoff 0.4735, PF 1.3563.
- 2026: n=7,519, WR 67.0701%, AvgNet -0.5616%, payoff 0.4347, PF 0.8114.
- Independent V501 recomputation exactly matches every aggregate/year metric; T+1, chronology, serial overlap, and duplicate-entry failures are all zero.

## Decision

Close this ontology. The high aggregate WR is a small-win/large-loss profile: average win +5.0517% versus average loss -8.9553%. It is also structurally regime-dependent, with negative expectancy in 2023 and 2026. Do not reopen through BOS threshold, OB lookback, activation window, SL, TP, hold, year, or regime variants.

Artifacts: `v498_weekly_breaker_daily_transfer_latest.json`, `v499_weekly_breaker_daily_transfer_oracle_latest.json`, `v500_weekly_breaker_daily_transfer_frozen_t1_replay_latest.json`, `v501_weekly_breaker_independent_metric_audit_latest.json`.
