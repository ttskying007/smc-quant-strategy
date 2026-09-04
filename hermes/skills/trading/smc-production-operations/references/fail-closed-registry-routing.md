# Fail-closed registry routing: regression pattern

## Failure mode

A production registry can correctly revoke authorization with:

```json
{
  "state": "FAIL_CLOSED_REPLAY_GATE_FAILED",
  "production_strategy": null,
  "buy_enabled": false
}
```

A UI branch that tests only `state == "EMPTY_BOOK"` misses this state and can display a legacy engine's historical backtest. That is an authorization and semantics failure even if no write occurs.

## Required routing rule

- Determine whether production is disabled from the authoritative authorization fields, principally `production_strategy is None`.
- Use `buy_enabled` as the additional execution guard.
- Treat human-readable `state` values as explanatory labels, not the sole authorization switch.
- Never fall back to legacy trade/pick artifacts when the strategy is absent.

## Regression checks

1. Prepare/read a registry with a non-literal fail-closed state, `production_strategy: null`, and `buy_enabled: false`.
2. Request the backtest/research route: it must render the frozen research page, not legacy historical metrics.
3. Request the period API: it must preserve `research_only=true`, `production_write=false`, `watchlist_write=false`, and `buy_enabled=false`.
4. Restart the real dashboard server and open the route in a browser; handler-level checks alone are insufficient.
5. For frozen period reports, assert annual trade-count sum = monthly trade-count sum = overall closed-trade count and all period T+1 violation counts are zero.

This regression remains about routing and display authorization only; it does not authorize production writes or promotion.
