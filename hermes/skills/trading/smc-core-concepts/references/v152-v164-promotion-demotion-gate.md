# V152→V164 Promotion/Demotion Gate Lesson

Use this reference when an SMC iteration appears to have a high headline WR but may contain lifecycle/execution artifacts, or when deciding whether a research scanner contract can replace frontend/production routing.

## Core lesson

Do not keep a version promoted just because it was previously routed in the frontend. If a later audit proves synthetic exits, micro-profit clustering, historical-pick pollution, or scanner/production mismatch, immediately demote it to historical diagnostic status and verify the live API/frontend no longer routes it.

## Fixed decision boundary

| State | Usable when | Not usable when |
|---|---|---|
| Production/API routing | promoted report/trades/picks are clean; endpoints prove no deprecated version string; current picks are not historical completed trades; WATCH_ONLY rows do not compute live PnL | synthetic BE > 0; micro-profit cluster; historical trades masquerade as current picks; scanner-time contract not proven |
| Next production candidate | n >= 200, min yearly sample >= 30, synthetic_be = 0, micro_pct <= 1%, T+1 = 0, losing rows and excluded buckets audited, scanner-time dry-run contract passed | only aggregate WR/RR is good; losing/excluded buckets not traced; contract only exists in historical backtest rows |
| Research / field contract | dry-run proves fields can be generated scan-time, no outcome leak, required fields complete, production files unchanged | should not be promoted until monthly/rolling robustness and live scanner integrity also pass |

## Required sequence after pollution is found

1. Demote the polluted promoted version in frontend/API routing first.
2. Keep polluted artifacts on disk only as `diagnostic` / historical files.
3. Audit the clean candidate:
   - synthetic BE count
   - micro-profit bucket count/rate
   - T+1 violation count
   - min yearly sample and yearly counts
   - losing-row taxonomy
   - excluded bucket taxonomy
4. Run scanner-time dry-run contract from the real current candidate stream, not from historical chosen trades.
5. Verify live endpoints after restart:
   - `/api/summary`: expected fallback/promoted version, no deprecated version string
   - `/api/picks/contract`: tradable/watch/raw counts separated
   - `/api/picks`: no `exit_date`, `net_pnl_pct`, `hold_bars` pollution; no deprecated version string
   - `/api/live-prices`: `tradableLiveCount` and `watchContextCount` separated; WATCH_ONLY rows have `tradable=false`, `isTradableLive=false`, `pnlPct=0`
6. Browser-smoke `/`, `/monitor`, `/live` and require zero console JS errors.
7. Persist both a machine-readable endpoint bundle and a short final closure report under `~/.hermes/smc_audit/`.

## V152/V153/V160/V164 example pattern

- V152: invalidated as production due to synthetic BE and ~0.5% micro-profit pseudo-wins; demote to historical diagnostic.
- V153: valid next candidate audit shape: `n=221`, `WR=83.26%`, `avg=3.3327%`, `synthetic_be=0`, `micro_pct=0.90%`, `T+1=0`, `min_year_n=34`; still do not write production until scanner contract and bucket audits pass.
- V160/V161: research/scanner-field contract only; if scanner integrity bug allows FAILED/RECOVERY/UNCLEAR rows as BUY, do not promote even if historical backtest rows were clean.
- V164: corrected scanner dry-run can prove scan-time filtering and no outcome leak, but remains research-only unless full production gates pass.

## Reporting rule for Lei

End the report with an explicit stop/continue decision:

- `目标完成，停止继续迭代。` when demotion/API closure and candidate classification are fully verified.
- `不可晋级生产，继续研究。` when only dry-run/field contracts passed.
- Never leave the version status ambiguous; ambiguity causes endless iteration.