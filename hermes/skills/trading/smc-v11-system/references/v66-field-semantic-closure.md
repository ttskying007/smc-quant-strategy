# V66 Field + Semantic Closure Pattern

Use this reference when a production SMC version has already been made runnable, but the user asks to continue into a full closure across pages/API/JSON plus signal-definition audit.

## Trigger

- User reports frontend/API field gaps such as missing 选股日期、加入日期、Zone、成本线、波动.
- User then asks whether signal definition / combination / trigger / entry position / entry condition is actually correct.
- The production version is an overlay/gate on older trade rows rather than a strict signal generator.

## Required Sequence

1. **Separate field contract from signal correctness**
   - Fix page/API/JSON missing fields first with a central normalizer.
   - Do not claim signal correctness because display fields are now complete.

2. **Use one field-contract function**
   - Add or extend a central helper such as `_apply_smc_field_contract()`.
   - Fill: `select_date`, `pick_date`, `join_date`, `zone_type`, `zone_low`, `zone_high`, `cost_line`, `smart_money_cost`, `volatility_pct`, `engine`.
   - Also fill semantic transport fields: `semantic_layer`, `strict_audit_status`, `signal_correctness_claim`, `entry_mode`, `market_state`.

3. **Preserve fields through lightweight caches**
   - If K-line/API views use a stripped cache, add new contract fields to its allowlist.
   - Otherwise physical JSON may be correct while K-line/API still returns null.

4. **Patch all consumers, not only the list page**
   - Selection/monitor page table.
   - Live API snake_case and camelCase outputs.
   - K-line API trade rows, especially if they rebuild a compact `trade_list` manually.
   - Backtest/analysis/autopsy pages if they filter or copy trade rows before rendering.

5. **Write semantic layer audit separately**
   - Generate a machine-readable audit file, e.g. `v66_semantic_layering.json`.
   - Layer examples:
     - `A_STRICT_SEMANTIC_KEEP`
     - `B_FIELD_ENTRY_REPAIRABLE`
     - `D_REBUILD_FVG_ENTRY_MODE`
     - `E_REJECT_SEMANTIC_POLLUTED`
   - Physical production JSON may be enriched with these labels, but the labels must not silently promote a legacy signal to strict SMC.

6. **Do not mislabel daily candidates**
   - Daily candidates are current scan rows, not necessarily historical trades.
   - If they do not match historical audit rows, assign `PENDING_DAILY_REPLAY` / inferred entry state rather than copying an old trade’s semantic verdict by symbol.

7. **Restart and verify via HTTP**
   - Compile first.
   - Restart the frontend service.
   - Verify `/monitor`, `/api/live-prices`, and `/api/kline?...&ver=<version>`.
   - Count bad fields programmatically; do not rely on eyeballing one page.

## Verification Contract

Minimum pass criteria:

| Surface | Required |
|---|---|
| Physical trades/picks/candidates | zero missing for date, zone, cost, volatility, semantic, entry mode, market state fields |
| Selection page | headers include 选股日期/加入日期/Zone/成本线/波动 and any newly added audit columns |
| Live API | bad field count = 0 across selected field list |
| K-line API | trade rows include normalized field contract; bad field count = 0 |
| Signal correctness | if strict audit fails, report BLOCKED even if WR is excellent |

## Pitfalls

- High WR after overlay/gating is not proof that OB/FVG/BOS/CHOCH definitions are correct.
- Fixing physical JSON is insufficient if the web service serves stale memory cache; restart and verify HTTP.
- Fixing `_api_live_prices` is insufficient if `_api_kline_full` reconstructs `trade_list` and drops fields.
- Do not copy semantic audit verdicts from historical trades into daily candidates by symbol only.
- If strict engines improve semantics but fail full-market effect, keep them as parallel candidates and do not replace production.
