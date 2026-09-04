# V30 Strict SMC Sequence + Frontend Sync Lessons (2026-05-21)

## Trigger
Use this reference when the user reports that SMC signals are inaccurate, Pinbar is being overused, or backtest/picks/K-line/analysis pages disagree.

## Root cause discovered
V29 had good aggregate metrics but the mechanism was wrong:

- 91.7% of trades were based on BOS, which is trend continuation, not a reversal trigger.
- 0/387 trades carried a Sweep field.
- `ctx_seq` was only `{zone_type}→{source_event}→{conf_type}` and not a real chronological SMC chain.
- Pinbar was treated as the only confirmation and was not strictly required to form at the PD Array / zone boundary.
- Sweep detection existed in the signal core but was not part of `build_bullish_setups()`.

## Correct V30 contract
The correct bullish SMC sequence is:

```text
SSL Sweep → CHOCH/MSS → OB/OTE/BPR → Pinbar/BullishRejection at zone → T+1 Entry
```

Hard invariants:

1. Do not use BOS as an entry event for the reversal engine. BOS can be chart context, but not the V30 setup anchor.
2. Require SSL Sweep within the lookback window before CHOCH/MSS.
3. Pinbar is not a standalone signal and not the only allowed confirmation. It must form at/near the zone boundary.
4. `BULLISH_REJECTION` is an allowed zone-local confirmation when the candle touches the zone and rejects upward.
5. `ctx_seq` must be a chronological chain, e.g. `SSL→MSS→OB→BULLISH_REJECTION→Entry`.
6. Picks must carry exact chain indices: `sweep_idx`, `source_event_idx`, `zone_idx`, `conf_index`, `entry_index`.

## Implementation pattern

- Add/maintain `build_bullish_setups_v30()` in `smc_core_v27.py` rather than silently changing old V27 semantics.
- Use V30 sequence builder + V29 quality/context filters + V28 adaptive exits.
- Scanner path: `/root/.hermes/scripts/v25/v30_full_scan.py`.
- Data output:
  - `/root/.hermes/smc_opt_v30/v30_trades.json`
  - `/root/.hermes/smc_opt_v30/v30_picks.json`
  - `/root/.hermes/smc_opt_v30/v30_metrics.json`
  - `/root/.hermes/smc_opt_v30/v30_diagnostics.json`

## Frontend sync checklist
When a new SMC engine version is promoted, update all surfaces, not just data files:

1. `ACTIVE_VERSION`, `ACTIVE_TRADE_FILE`, `ACTIVE_PICK_FILE` in `smc_unified.py`.
2. K-line version selector default option.
3. `ver_map` and `_ver_paths` in `/api/kline_full`.
4. Dashboard labels, monitor labels, backtest labels, diagnostics labels.
5. `/api/picks`, `/api/summary`, `/api/diagnostics`.
6. K-line highlight mapping for exact chain indices:
   - `1 LIQ:SSL`
   - `2 MSS/CHOCH`
   - `3 Z:OB/OTE/BPR`
   - `4 PINBAR/REJ`
   - `5 ENTRY`
7. Analysis/autopsy pages must not keep stale old-version text such as `V25`/`V29`.
8. Restart the 8890 frontend and verify pages plus APIs.

## Verification commands

```bash
python3 -m py_compile \
  /root/.hermes/scripts/v25/smc_core_v27.py \
  /root/.hermes/scripts/v25/v30_full_scan.py \
  /root/.hermes/scripts/smc_unified.py

PYTHONUNBUFFERED=1 python3 /root/.hermes/scripts/v25/v30_full_scan.py
```

After scan, verify invariants:

```python
import json
from pathlib import Path
tr = json.loads(Path('/root/.hermes/smc_opt_v30/v30_trades.json').read_text())
print('trades', len(tr))
print('BOS', sum(1 for t in tr if t.get('source_event') == 'BOS'))
print('missing_sweep', sum(1 for t in tr if int(t.get('sweep_idx', -1) or -1) < 0))
```

Expected for V30 promotion: `BOS == 0` and `missing_sweep == 0`.

## User-facing reporting rule
For Lei’s SMC work, do not stop with a plan or a long abstract report. Deliver:

1. What changed.
2. Full validation numbers.
3. Which frontend pages/APIs were verified.
4. Exact files changed.
5. Any remaining structural risk.

Do not present multiple options; test and ship the best path.
