# Source-isolated OHLCV provenance and audit pattern

## Purpose

Keep historical market-data evidence reproducible and prevent false confidence from mixing providers, adjustments, or derived timeframes.

## Storage contract

```text
raw_multitf/
  source_raw/
    <provider>/
      daily/
      m15/
      m60/
      weekly/
  source_registry.json
```

- One provider namespace per cache.
- Never repair a provider gap from another provider.
- Preserve older cache roots read-only during migrations; use copy-only migration and atomic per-file writes.

## Bar contract

Every normalized bar should retain OHLCV plus:

```text
source
adjustment
requested_range
received_range
provider_timestamp
coverage_audit
cross_source_validation
source_kind                 # provider_raw | same_source_deterministic_aggregation
provenance_schema
```

`weekly` must derive from same-source daily. `m60` must derive from same-source m15 unless it is explicitly declared an independent provider timeframe.

## Source-local audit gates

For every symbol and provider namespace:

1. daily timestamps strictly ascend and OHLC is valid;
2. every daily trading date has exactly 16 standard A-share m15 slots;
3. every daily trading date has exactly 4 m60 slots;
4. weekly OHLCVA exactly matches same-source daily aggregation;
5. m60 OHLCVA matches same-source m15 aggregation; numerical checks may use a scale-aware tolerance only for float accumulation noise;
6. all required provenance fields exist and the `source` value matches the namespace.

A provider is source-local research-ready only after the entire intended universe passes. Keep failure records; do not hide missing frames by taking a daily-only symbol list.

## Cross-provider validation

Compare only identical symbol/date/slot pairs. Report overlap count, window, price/volume deltas, adjustment labels, and mismatch counts. A close match does **not** authorize substitution. Any difference or unknown adjustment convention means the providers remain isolated.

Use two states:

- `READ_AUTHORIZED_SAME_SOURCE_ONLY`: full local coverage and audit pass; research must read one provider namespace only.
- `READ_BLOCKED__SOURCE_NOT_PROMOTED`: requested independent/cross-source validation is unavailable or incomplete.

## Operational safety

- Treat a blocked primary provider as `NO_BUILD`, not as no-data for each symbol.
- Do not permanent-quarantine symbols after a source-wide authentication or provider failure.
- Do not let a successful historical replay imply production eligibility.
