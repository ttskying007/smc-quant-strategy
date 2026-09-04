# V24 cron frontend validation pitfall

## What happened
During the V24 closed-loop cron run, the engine completed successfully and wrote fresh V24 trades/picks, but the frontend initially still resolved to a higher-priority version because `ACTIVE_VERSION` was ordered to prefer later versions first. HTTP 200 alone was not enough to prove the UI was showing V24.

## Durable lesson
For version-specific cron jobs, verify both:
1. the data files were regenerated for the target version, and
2. the frontend's active-version selector actually prioritizes that target version.

If the selector prefers higher versions first, the page can render successfully while silently showing the wrong dataset.

## Verification pattern
- Check the target version stats file after engine run.
- Ensure the target version appears first in `ACTIVE_VERSION` selection order when the cron intends to validate that version.
- Validate page content, not just HTTP status:
  - `/` should show the target version label and target trade/pick counts.
  - `/monitor` should show the target pick universe.
  - `/backtest` should show the target backtest summary.
- Confirm the counts and version labels match the engine output before declaring success.

## Practical sign of success
For V24, the dashboard, monitor, and backtest pages should all visibly say `V24` and reflect the V24 counts, not merely return 200.