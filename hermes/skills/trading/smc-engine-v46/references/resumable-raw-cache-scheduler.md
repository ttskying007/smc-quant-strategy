# Resumable raw market-cache scheduler

Use this when a multi-timeframe cache is built incrementally from a provider that can return empty history, stall, or silently repeat already-complete work.

## Invariants

- A completed symbol is only one whose required frames exist **and** passed frame-slot validation.
- Permanent no-data is a separate, auditable state; never treat it as a completed cache.
- A batch must contain the exact currently-missing symbols, not a lexical `resume-from` range plus `limit`.
- Each provider subprocess has a bounded timeout and its own process group; on timeout, terminate the whole group and retain atomic files already written.
- Reports must distinguish `BATCH_RUNNING`, clean terminal states, and timeout/failure states. Never leave a stale generic `RUNNING` report.
- Use an outer non-overlap lock for the scheduler plus an independent cache-write lock.

## Reliable pattern

1. Derive `eligible_missing = universe - valid_complete - permanent_quarantine`.
2. Persist the selected exact batch as a newline-delimited symbol file.
3. Invoke the builder with `--symbols-file`; do not let it select adjacent already-complete symbols by code order.
4. Write `BATCH_RUNNING` with the exact symbols before launching the provider subprocess.
5. On known permanent outcomes such as validated `DAILY_EMPTY`, atomically write a quarantine record containing symbol, reason, and timestamp.
6. After the batch, recompute missing from disk and report `before`, `after`, `completed`, subprocess return code, and timeout status.
7. Verify progress using all frame counts, not just one cache directory.

## Pitfalls observed

- Checking only whether an m15 filename exists is insufficient as a definition of complete; use validated required-frame coverage for release/audit decisions.
- A range-based builder can repeatedly process cached symbols after one permanent failure at the front of the missing list, yielding `returncode=0` and `completed=0` forever.
- A batch can partially finish before a provider socket blocks. Atomic per-symbol writes make the completed subset safe, but the controller must kill the child process group and resume from the recomputed gap.
- A cron wrapper should run one bounded batch, use `flock -n`, and have an outer timeout longer than (but close to) the inner provider timeout.
