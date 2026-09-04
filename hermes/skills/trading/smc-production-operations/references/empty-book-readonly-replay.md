# EMPTY_BOOK no-write replay: failure mode and acceptance pattern

## Failure mode

A dashboard used one manual endpoint for two incompatible meanings:

1. run a frozen V517/V519 strict-T+1 research replay; and
2. create/update production candidates.

Its first branch rejected every request when the production registry was not `LIVE_READY`. As a result, a correct manual replay was reported as an error merely because the production promotion gate had failed. Earlier UI code also sent a legacy version selector (`V175`), risking a historical-engine fallback.

## Correct semantics

- `EMPTY_BOOK` means no production strategy is authorized and no production write is allowed.
- It does **not** mean frozen causal research cannot be rerun.
- The no-write replay API must return `ok=true` when execution succeeded even if `production_gate_pass=false`.
- A separate result field must record the promotion decision and explain that production stays empty.

## Concrete acceptance output

A verified V517/V519 replay returned:

```json
{
  "ok": true,
  "engine": "V519_FROZEN_STRICT_T1_REPLAY",
  "state": "FAIL_CLOSED_REPLAY_GATE_FAILED",
  "trades": 386,
  "wr": 60.6218,
  "avg_net_pnl_pct": 0.4602,
  "profit_factor": 1.1817,
  "t1_violations": 0,
  "production_gate_pass": false,
  "production_write": false,
  "watchlist_write": false
}
```

The relevant fact is: the replay executed successfully, T+1 remained clean, and no production state was mutated. The gate still failed because the overall average net PnL was below the predeclared threshold and the 2023 yearly average was negative.

## UI acceptance

The monitor page must expose an enabled action named **运行冻结研究回放（只读）** in `EMPTY_BOOK`. After a click it must display a message equivalent to:

```text
完成：386笔；生产门禁未通过，保持 EMPTY_BOOK
```

It must not display a production-gate failure as a generic action failure, and it must not provide a control that promises “重新选股” when no production candidate can legally be written.

## Minimal verification sequence

1. Directly POST the endpoint with an empty request body.
2. Assert: `ok=true`, `production_write=false`, `watchlist_write=false`, and `t1_violations=0`.
3. Check that the registry remains `production_strategy=null`, `buy_enabled=false`.
4. Open the monitor page, click the exact control, and inspect the rendered status text.
5. Confirm no historical V88/V175 artifact was invoked or surfaced as a current candidate.
