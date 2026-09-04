# SMC Frontend Field Contract Audit Notes

## Scope
This note captures a repeated frontend sync pattern in the SMC system: selection page, backtest, analysis, autopsy, docs, kline, and live pages must all show the same field contract and version badge.

## What to verify first
1. Route text contains the expected labels: `选股日期`, `加入日期`, `Zone`, `成本线`, `波动`, `DNA`, `组合合同`.
2. API payloads contain the same normalized fields on `/api/picks`, `/api/live-prices`, and `/api/kline_full`.
3. Rendered DOM for async sections actually shows the values; snapshot text alone can miss delayed JS updates.

## Field aliases that must be present
- `pick_date` / `select_date`
- `join_date`
- `signal_date`
- `zone` / `zone_low` / `zone_high`
- `cost_line` / `smart_money_cost`
- `volatility_pct`
- `risk_pct` / `sl_pct`
- `dna_preferred_behavior`
- `combo_contract_key`
- `signal_price`
- `exit_reason`
- `hold_bars`

## Common failure modes
- A template literal or f-string leaves a placeholder like `{FRONTEND_VERSION}` visible in the UI.
- The page title is fixed, but the table data still misses the contract fields.
- K-line async overlays render correctly in the badge but not in the trades table.
- Live rows may show values on screen while the API response still lacks the canonical aliases.

## Verification pattern
Use a three-layer check:
- HTML text for each route.
- JSON contract check for each API.
- Browser DOM check for the async K-line/live sections.

If any layer disagrees, patch the shared field contract in the backend first, then the page renderer.