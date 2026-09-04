# V66 Frontend/Live Source Parity Audit

Use when Lei says the SMC frontend does not match the reported output, or when `/monitor`, `/api/picks`, and `/live` show different counts/fields.

## Core lesson

Do not treat field non-blank checks as full frontend synchronization. In V66-style dashboards, the same visible page can combine multiple truth sources:

| Surface | Typical source | Failure mode |
|---|---|---|
| `/monitor` current picks table | `v66_picks.json` ACTIVE_CANDIDATE rows | Small current active count |
| `/api/picks` | `get_active_picks()`; for V66 may include ACTIVE_CANDIDATE + WATCH_ONLY | Count differs from monitor headline/table |
| `/monitor` realtime-monitor table | `positions.json` OPEN/NEXT_DAY_PENDING/WATCH_ONLY | Old ingested positions appear under current page |
| `/live` | `positions.json` OPEN + NEXT_DAY_PENDING, fallback to active picks only if no positions | Live page can show stale/legacy positions even after the scan engine was fixed |
| `trade_ledger.json` | monitor lifecycle BUY/SELL events | BUY-only ledger means no SL/TP learning closure |

## Mandatory audit sequence

1. Count raw current picks, API picks, live rows, positions, and ledger actions separately.
2. Validate field contract on both API rows and browser-rendered first screen:
   - pick/select date
   - join date
   - Zone type or zone bounds
   - cost line
   - volatility / vol class
3. If fields are non-blank but counts disagree, stop calling it a field bug. Diagnose source parity:
   - `/monitor` current-pick table vs monitor-position table
   - `/api/picks` ACTIVE/WATCH scope policy
   - `/live` positions-first policy
4. Quantify stale-position contamination:
   - OPEN, NEXT_DAY_PENDING, WATCH_ONLY, CLOSED counts
   - `entry <= SL`
   - `entry < zone_low`
   - `SL ≈ zone_low * 0.995`
   - `SL <= 3%`
   - ledger BUY vs SELL count
5. Only after source parity is clean should strategy quality claims be made.

## Known V66 failure pattern

A fixed `daily_scan.py` does not automatically repair old `positions.json` rows. `/live` may still show hundreds of old OPEN/PENDING positions with stale SL/zone semantics. This explains why backend output from current picks can disagree with the realtime page.

Example red flags to report explicitly:

- `/live` rows > `/api/picks` rows because `/live` is positions-first.
- `/monitor` heading count differs from `/api/picks` because one is current ACTIVE_CANDIDATE while the other includes WATCH_ONLY.
- `positions.json` has OPEN/PENDING rows with `SL≈zone_low*0.995` after the engine was supposedly fixed.
- `trade_ledger.json` has BUY rows but 0 SELL rows, so SL/TP review closure is broken.

## Repair order

1. Unify source-of-truth policy for `/monitor`, `/api/picks`, and `/live`.
2. Quarantine legacy `positions.json` rows or mark them WATCH_ONLY/INVALID before judging current strategy.
3. Add hard gates for executable realtime rows: reject `entry <= SL`, reject/diagnose `entry < zone_low`, flag `SL≈zone_low*0.995`.
4. Restore SELL/review ledger closure so SL/TP events produce reviewable outcomes.
5. Re-run browser verification after service restart and report both API zero-blank counts and browser first-row values.
