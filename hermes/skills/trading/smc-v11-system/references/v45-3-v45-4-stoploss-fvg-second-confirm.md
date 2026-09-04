# V45.3/V45.4 Stop-Loss Autopsy and FVG Second-Confirm Gate

## Trigger
Use this reference when a V45-family SMC run shows elevated stop-losses and the user asks whether the cause is signal definition, entry point, SMC combination logic, or entries occurring before the true POI.

## Durable lesson
Do not answer elevated SL with exit tuning first. Diagnose in this order:

1. **Signal branch attribution** — split SL by `zone_type`, `sequence_kind`, `conf_type`, `market_state`, `entry_mode`, `execution_zone_mode`.
2. **Path replay** — for each SL, compute MFE before SL, MAE before SL, and post-SL 10-bar rebound. If many SLs rebound strongly, early stop/partial-loss is likely harmful.
3. **Entry validity** — verify entry stayed inside raw zone and execution zone; do not use aggregate WR/RR as proof of correctness.
4. **Branch-specific repair** — only repair the branch where SL concentrates. Do not change OB when FVG is the problem.

## V45.3 finding
V45.2/V45.3 SL autopsy found that most SLs were not permanent signal failures: many trades stopped out and then rebounded. Aggressive early partial-loss reduced nominal SL rate but damaged WR/avg/total because it sold fake-breaks before recovery.

Accepted V45.3 exit layer:

- Keep V45.2 entries/signals unchanged.
- Keep structural stop; no early partial-loss before structure fails.
- TP1 at 2R with smaller 20% partial.
- BE at 1R after 3 bars.
- No high-water trailing until TP2 protective stop.

Result shape: preserved WR and SL rate while slightly improving avg/total. Lesson: when SLs frequently rebound, improve winner capture instead of prematurely cutting losers.

## V45.4 finding
SL concentration was primarily FVG, not OB. Therefore V45.4 became a quality gate over V45.3:

- OB branch unchanged.
- FVG wide raw zones and very fresh/unmatured signals are not deleted; they are marked `SECOND_CONFIRM_REQUIRED`.
- Held FVG setups should be recompiled later through a legal reclaim/second-confirmation entry, not treated as permanently invalid.

Example evidence thresholds from that run:

- `raw_zone_width_pct > 4.6` had materially worse FVG SL/WR.
- fresh `signal_index > 709` had materially worse FVG SL/WR and represented unfinished retests.

These thresholds are not universal constants; recompute them from the current run before hardcoding. The durable pattern is: detect bad FVG buckets, hold them for second confirmation, keep OB untouched.

## Required report fields
For any V45 stop-loss repair, output at minimum:

- before/after metrics: trades, wins, losses, WR, avgPnL, totalPnL, SL count/rate;
- by-zone metrics, especially FVG vs OB;
- removed/held bucket metrics, including their WR/avg/SL rate;
- reject/hold reason counts;
- correctness contract checks: no direct chase, no standalone IFVG, no expired/invalidated setup trades, raw/execution zone coverage, entry-above-zone invalid counts;
- frontend/API verification if default version changes.

## Pitfalls
- Do not call a held FVG setup “bad signal” unless path replay proves the SMC premise failed. Wide/fresh FVG often needs reclaim/second-confirmation rather than deletion.
- Do not optimize exit parameters against all trades when only one signal branch causes the SL excess.
- Do not update `/v45` default solely because WR improves if total recall collapses without explicitly labeling the version as stricter/high-confirmation.
- Do not let picks include `SECOND_CONFIRM_REQUIRED` setups as immediate entries; keep them watch-only until reclaim confirms.
