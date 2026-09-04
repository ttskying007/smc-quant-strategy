# V432–V437 causal production rebuild and BUY_VALID fail-closed contract

Date: 2026-07-14

Use when the SMC system has a historically strong package but current production must be rebuilt from raw latest-market data.

## Causal corrections

- V185 historical package is not a valid production baseline. V432 found all 247 V175 rows entered 2/3 bars before their takeover confirmation, while all 87 child rows depended on three post-reclaim bars and lacked required provenance indices. Preserve history as rejected research only; `current_scanner_rebuild_allowed=false` means active/picks must be physically emptied.
- V365 is not a valid survivor. V366 found 402/402 candidates entered before required confirmation. V367 corrected entry timing and found no fixed-gate walk-forward survivor; V368 independently confirmed the corrected causality. Keep V365 only as a no-write/no-buy negative-control shadow.
- Supply-Failure Breaker passed independent semantic oracle (V434/V435) but failed the single frozen economic replay (V436); close the ontology with no threshold/SL/TP/hold variants.
- Target-First DOL V437 passed the pre-outcome semantic/support gate; only an independent oracle may run next.

## Production architecture

Physically separate:

1. historical backtest rows;
2. latest raw scanner candidates;
3. explicit BUY_VALID current candidates;
4. real positions/ledger;
5. shadow/research artifacts.

Never rematerialize current picks from historical trades or historical active packages.

## BUY_VALID authorization

For automatic or API daily ingest, active-looking metadata is insufficient. Require all fields:

- `is_active_pick is True`
- `pick_scope in {ACTIVE_CANDIDATE, ACTIVE_ENTRY}`
- `live_guard_status == BUY_VALID`
- `trade_action == BUY`
- `buy_enabled is True`
- `tradable is True`

If any field is missing, do not create OPEN or NEXT_DAY_PENDING and do not append BUY ledger events. Return an unauthorized diagnostic only. Manual operator entry remains a separate explicit path.

## Refresh fail-closed gate

Before scanner/rematerialize/ingest:

- refresh return code must be zero;
- request coverage and coherent latest-date coverage must pass;
- latest date must not regress, be future-dated, or stale;
- intraday partial daily bar must be excluded.

On failure, skip every downstream production step and write a fail-closed ops report. Existing positions may remain for risk monitoring, but current candidate output must be empty.

## API truthfulness

When V185 is causality-rejected:

- `/api/summary` must report `production_state=EMPTY_BOOK_FAIL_CLOSED`, `production_write=false`, production metrics zero, and put old metrics under `research_history`;
- `/api/picks` and `/api/live-prices` return zero current rows;
- data date still comes from the passed refresh gate.

## Verification observed on 2026-07-14

- Full refresh: requested 4,905, ok 4,903, failed 2, latest 20260713, current-date coverage 99.65%, gate pass.
- Daily ops: `FAIL_CLOSED_V185_CAUSALITY`, ingest added 0.
- Current V185 active rows: 0; no BUY events or positions created that day.
- V365 shadow: all write flags false, buy disabled, rejected negative control.
- Focused tests passed: refresh fail-closed, complete BUY_VALID authorization, monitor T+1/live-price execution contract.
