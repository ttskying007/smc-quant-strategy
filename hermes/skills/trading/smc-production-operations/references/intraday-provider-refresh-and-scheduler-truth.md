# Intraday provider refresh and scheduler truth

## Use when

A full-market daily refresh or post-close scanner appears to have run but produces no committed epoch, stale scheduler status, or misleading `EMPTY_BOOK` interpretation.

## Separate these facts

1. **Data-plane failure**: refresh cannot create a committed epoch. Scanner/release must not run. This is distinct from a valid zero-signal scan.
2. **Valid scan / no setup**: epoch is committed; scanner runs; current raw setup count is zero.
3. **Release-blocked setup**: epoch is committed; scanner has a full current setup; research/release gate blocks production admission.
4. **EMPTY_BOOK**: no promoted strategy; it must not be represented as a scanner crash.

## Required post-close status contract

After every run, persist and expose:

- committed/rejected epoch id and market date;
- refresh return code, request coverage, current-date coverage, and gate failures;
- scanner/release/shadow/controller return codes separately;
- controller `stderr` whenever nonzero;
- whether the result is a valid blocked/no-op state or a real pipeline failure.

The dashboard scheduler state must be updated from the actual scheduled result, not from a static or retired job record. A real refresh rejection should produce a nonzero process exit, while a successfully executed fail-closed no-op is a normal, explicit operational state.

## Mutable intraday-bar pitfall

Some providers return only the currently forming bar for a market segment (notably a segment such as BJ), while other symbols return historical bars. Never:

- overwrite committed daily history with that mutable bar;
- use a different provider's adjusted series as a silent fallback;
- infer market-closed status from a JSON field without probing that field exists for the specific response shape.

Safe behavior requires an **independent, tested market-session witness**. While that witness proves the exchange is open, retain the already committed prior completed bar for a symbol whose provider response contains no completed bars. The staged copy must be byte-identical to the committed cache. Only after a close witness may the new bar replace the last committed bar, subject to source-alignment checks.

## Verification checklist

- Test the exact provider payload for SH, SZ, and BJ; record whether the market-status field actually exists.
- Exercise one mutable-bar symbol using a temporary stage directory and prove the preserved staged cache hash equals the committed cache hash.
- Run a full refresh and require the normal committed-epoch coverage gate; do not call a helper test a production repair.
- Then run scanner → release → shadow → controller and verify API/UI expose the same epoch and outcome.
- If the provider status witness is absent or ambiguous, remain fail-closed and surface `REFRESH_NOT_COMMITTED`; do not downgrade the coverage gate.
