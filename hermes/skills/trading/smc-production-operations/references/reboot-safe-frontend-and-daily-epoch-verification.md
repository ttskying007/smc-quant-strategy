# Reboot-safe dashboard and daily-epoch verification

## Problem class

A user can report that a dashboard has not updated after a machine reboot. This can be either:

1. a real service-recovery outage;
2. a valid daily-data cadence issue (a close-based daily epoch cannot be final during the morning session); or
3. a fresh data epoch that the browser has not rendered yet.

Never infer the cause from an old PID, a remembered log line, or a stale page.

## Minimal evidence chain

1. Record boot time and compare it with the service's first `ActiveEnterTimestamp` / journal start in the current boot. A service enabled *now* may have been installed or started only after the reboot; it is not proof that it was present at boot.
2. Verify the dashboard unit is `enabled`, `active`, waits for `network-online.target`, and has `Restart=always` (or an equivalent supervised restart policy). The dashboard must have one service owner, not a competing watchdog that launches a second Python process.
3. Verify the post-close scheduler independently: enumerate its owner and prove the actual invocation from current-boot cron/journal evidence. Do not run a second observer merely to test it, because a refresh can race and mutate current artifacts.
4. Read the committed epoch manifest and refresh report directly. Require a committed status, market date, request coverage, current-date coverage, and explicit failures.
5. Verify the dashboard after the service check/restart with a browser-rendered assertion for the same epoch ID, market date, status, and fail-closed state.

## Timing semantics

For a close-based daily-bar workflow, the normal output deadline is the configured post-close task, not the morning market session. A missing same-day final daily epoch at 09:27 is not automatically a sync failure. State the scheduled cadence plainly, then separately prove whether the prior committed epoch remains visible.

## Controlled recovery acceptance

When an outage is confirmed and the unit is already configured, a bounded `systemctl restart` is an acceptable recovery test. Afterward require:

- new main PID;
- listener bound on the dashboard port;
- `enabled` and `active` states;
- browser page renders the committed epoch, not a cached historical date;
- `EMPTY_BOOK` / `buy_enabled=false` is unchanged unless an independently authorized production action occurred.

## Pitfalls

- Do not treat current `enabled` state as historical proof of boot-time launch.
- Do not call a close-based daily scanner broken merely because it has not published during the morning.
- Do not use stale logs to diagnose a live service.
- Do not restart or manually rerun a post-close observer if its completed epoch already proves success.
- Do not turn a research setup or a current-epoch observation row into a production pick while diagnosing operations.
