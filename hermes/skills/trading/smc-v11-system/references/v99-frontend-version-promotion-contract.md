# V99 version promotion + frontend contract closure

Use this when promoting an SMC candidate/gate layer above an existing production engine (for example V99 wrapping V98/V88) and the user expects the dashboard to reflect the new layer immediately.

## Durable lessons

1. **Do not stop at generated files.** A candidate layer is not production until all frontend data paths read it:
   - `/api/picks`
   - `/api/live-prices`
   - `/api/reload`
   - `/api/summary`
   - backtest/analysis/autopsy pages that call cached trades
2. **Picks and trades are separate routes.** It is possible for `/api/picks` and `/api/live-prices` to show the new engine while `/api/summary` still reports old `ACTIVE_TRADE_FILE` stats. Treat this as incomplete.
3. **Cache source must switch with the candidate.** For wrapper versions above an active base version, update both active pick merge logic and trade-cache source (`_cache_valid`, `_refresh_cache`, `get_version_trades` or equivalent) so summary/equity/analysis routes use the wrapper trades.
4. **Restart or invalidate cache after code changes.** `/api/reload` cannot pick up source-code routing changes if the server process is still running the old code. Restart the 8890 service/process, then call `/api/reload`.
5. **Field contract verification must cover both picks and live.** Check missing counts for: `pick_date`, `join_date`, `选股日期`, `加入日期`, `zone`, `zone_type`, `cost_line`, `smart_money_cost`, `volatility_pct`, `volatility`.
6. **If adding profit-protection exits, simulate bar-by-bar only.** Do not use final MFE to decide trailing stops. Store the rule and trail events in trade rows for auditability.
7. **Run variant matrices before finalizing a protective stop.** Profit protection can raise WR while lowering average PnL. Compare several lock levels and select the one matching the user's stated objective, then report both WR and avg PnL tradeoff.

## Minimal release checklist

| Check | Required result |
|---|---|
| Script syntax | `python3 -m py_compile` passes for modified scripts |
| Full generation | wrapper output files exist and are non-empty |
| T+1 audit | `entry_date != exit_date` for all trades |
| Active field contract | all required pick/live fields have 0 missing |
| `/api/picks` | rows use new engine and required fields are filled |
| `/api/live-prices` | rows use new engine; cost line/volatility are non-empty even during休市 |
| `/api/reload` | trade count reflects wrapper trade file, not old base trade file |
| `/api/summary` | total trades/WR/avg PnL reflect wrapper report/trades |
| Browser/API freshness | server restarted or cache invalidated after routing changes |

## Pitfall pattern

A common incomplete promotion looks like this:

- `v99_active_picks.json` is generated.
- `/api/picks` shows V99 rows.
- `/api/live-prices` shows V99 rows.
- But `/api/summary` still reports V88/V98 old trade count and metrics.

Root cause: only pick merge logic was updated; cached trade source still points at `ACTIVE_TRADE_FILE`. Fix the trade cache/routing source, restart the service, then verify `/api/reload` and `/api/summary` again.
