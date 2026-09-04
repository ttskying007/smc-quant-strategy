# Stale-date / EMPTY_BOOK UI diagnosis

## Symptom

A user sees an old date such as “last pick date” while market data has advanced materially, and suspects the scanner or frontend has stopped.

## Correct separation

| Domain | Date meaning | Must it track the current market date? |
|---|---|---:|
| Committed data epoch | Freshest usable market data | Yes |
| Production scanner | Current candidate materialization | Only when a strategy is licensed |
| Frozen replay | Historical study cutoff | No |
| Legacy artifacts | Historical trade/signal cutoff | No |

`EMPTY_BOOK` means the scanner intentionally produces no current candidates when no strategy has passed promotion. This must remain distinguishable from a data-refresh failure.

## Minimal evidence chain

1. Registry: `production_strategy is None`, `buy_enabled=false`, zero active BUY_VALID rows.
2. Current API: `/api/summary` exposes a committed current epoch; `/api/live-prices` has the same `dataDate`, `scanner_state=NOT_RUN_EMPTY_BOOK`, and `picks=[]`.
3. Refresh manifest: current market date, committed status, coverage/gate result.
4. Scheduler/observer: ran after refresh; its blocker is a production/research gate, not a data-fetch failure.
5. Browser: production and live pages show the current epoch and no candidate; legacy page explicitly labels its latest date as historical only.

## Allowed UI repair

Use a wording-only patch when needed:

- rename a mixed tab from “当前选股/研究历史” to “生产状态 / 冻结研究”;
- show `当前最新选股日：无` in fail-closed production;
- show `最后历史信号日：YYYY-MM-DD。这不是“当前最新选股日”。` on legacy artifacts.

Do not re-enable old scanners, copy historical trades into active picks, or alter registry authorization to make the dashboard show a newer pick.

## Acceptance checklist

- Python syntax check passes.
- Existing fail-closed tests pass.
- Actual server is restarted, not merely source-edited.
- `/api/summary`: current committed date, `buy_enabled=false`, zero current BUY_VALID.
- `/api/live-prices`: matching data date, empty picks, `NOT_RUN_EMPTY_BOOK`.
- Browser page visibly distinguishes historical date from current production state.
