# Resumable source-isolated cache controller

Use this pattern when a source-local historical OHLCV cache takes longer than one interactive or cron execution window.

## Invariants

- Derive missing symbols from the **intersection of every committed required frame** (`daily`, `weekly`, `m60`, `m15`), not a single frame. A process interruption between atomic writes must leave the symbol incomplete and eligible for retry.
- Keep each provider namespace isolated. The controller may resume the same provider only; it must never fill a gap from another provider.
- Persist an atomic status record containing complete count, remaining count, last batch result, retry count, and next delay.
- Use a nonblocking file lock so a second scheduler/service invocation exits without concurrent writers.
- A source request failure should retry with bounded exponential backoff; do not permanently quarantine every symbol during a provider-wide outage.
- On completion, run a coverage ledger against the dated canonical universe and a full source-local integrity audit before reporting completion. Completion of a recent partial range does not authorize a longer historical research range or production promotion.

## Durable execution

For a long controller, prefer a boot-enabled system service over a one-shot background process. Configure restart behavior, verify service enablement, then deliberately terminate the controller once and confirm a different PID resumes work. Keep file writes atomic so this recovery test cannot corrupt a half-written cache.

## Progress reporting

Report the canonical denominator, complete count, missing count, per-asset-class counts, and the research/promotion gate separately. Do not call a source cache "full market" merely because its cached subset passed integrity checks.
