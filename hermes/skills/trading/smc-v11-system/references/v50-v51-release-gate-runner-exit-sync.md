# V50→V51 release gate and frontend sync lessons

## When to use
Use this when an SMC version has passed signal/provenance checks but still shows low MFE capture / early selling, or when promoting a candidate version to the dashboard default.

## Durable lessons

### 1. Diagnose low RR/MFE as an exit problem only after signal provenance passes
Before changing exits, require:
- trade provenance fatal count = 0
- signal sequence violations = 0
- small wins below 2% = 0
- losses inside 1% = 0
- winning trades below 2R = 0

Only then treat low RR / low `avg_90d_capture` as a runner/exit problem rather than a signal-definition problem.

### 2. Early selling evidence pattern
The problematic V50 pattern was:
- `avg_90d_capture` low
- many `SOLD_EARLY_NEXT_90D`
- most early exits attributed to `STRUCT_HL_BREAK`

Deep cause: the trade direction and entry were mostly valid, but structure stop locked at 2R and washed out runners before the next 90-day move.

### 3. Minimal exit repair that preserved high WR
The V51 repair was to keep strict SL and 2R quality gate, but delay structure runner lock:
- V50: structure lock around 2R
- V51: `AFTER_2R_LOCK_R = 4.0`

This is not widening the original stop. It prevents runner exits around 2R while preserving quality filters.

### 4. Quality gate contract for production promotion
A candidate cannot be called production unless `release_gate.pass == true` and all of these are true:
- trade/pick/signal files exist
- provenance fatal count = 0
- sequence violations = 0
- hold over 90 = 0
- small win below 2% = 0
- loss inside 1% = 0
- winning RR below 2R = 0
- MFE capture threshold passes
- sample bias flags are empty

### 5. Pick scope normalization for V50+
V50/V51 pick files may contain:
- `ACTIVE_ENTRY`
- `NEAR_ZONE_WATCH`
- `POST_ENTRY_MONITOR`
- `EXPIRED_REVIEW`
- `REJECTED_CANDIDATE`

Frontend normalization should map:
- `ACTIVE_ENTRY` → `ACTIVE_CANDIDATE`
- `NEAR_ZONE_WATCH` / `POST_ENTRY_MONITOR` → `WATCH_ONLY`
- keep `REJECTED_CANDIDATE` visible in contract/reject APIs

For V50/V51, `/api/picks` should expose current active + watch pool, not only one active entry, otherwise the monitor looks empty even when the watchlist has hundreds of valid near-zone candidates.

### 6. Promotion sync checklist
When promoting a candidate version, update and verify all of:
- `ACTIVE_VERSION`
- `ACTIVE_TRADE_FILE`
- `ACTIVE_PICK_FILE`
- version-specific trade loader
- version-specific pick loader
- engine map / rerun endpoint
- K-line version dropdown default
- K-line full overlay support
- `/api/summary`
- `/api/picks`
- `/api/picks/contract`
- `/api/kline_full?symbol=...&ver=<version>`
- `/autopsy`
- `/live`

After restart, verify the live process is actually the new code. If the old server is still bound to port 8890, `/api/summary` may still report the previous `ACTIVE_VERSION` even after file edits.

## Expected V51-style verification output
Good outcome shape:
- release gate: pass
- provenance: all trades pass, fatal count 0
- sequence: violation count 0
- quality: no small wins / noise losses / low-R winners
- closed loop: higher `avg_90d_capture` and higher average R without collapsing WR
- frontend: summary, picks, K-line, autopsy, live all return without Traceback
