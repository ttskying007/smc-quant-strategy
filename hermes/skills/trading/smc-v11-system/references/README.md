# smc-v11-system references index

This index records support files added when `SKILL.md` is too large for direct patching.

- `latest-data-first-daily-selection.md` — Required SMC daily production order: refresh full-market K-lines before selection, scan latest complete day, merge into production candidates, ingest realtime, log data freshness/scan/merge/ingest, and invalidate frontend cache on both picks and trades mtimes.
