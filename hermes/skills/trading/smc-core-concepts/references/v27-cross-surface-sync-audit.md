# V27 Cross-surface Sync Audit Notes

## What must match
- Signal definition text
- Signal generation code
- Backtest entry/exit logic
- Pick generation and filtering
- K-line marker rendering
- Analysis/review statistics

## Canonical fallback rules
- If historical trade data lacks `won`, compute `won = pnl_pct > 0`.
- For zone retests, prefer wick-touch semantics unless the strategy explicitly uses close-only.
- Never let UI derive a different win/loss meaning from the backend.

## Symptoms of drift
- Trades and picks disagree on dates or counts.
- Frontend markers show a different status than the trade export.
- Review pages count wins differently from backtest tables.
- A signal name stays the same but its event order changed.

## Verification
- Re-run the full scan after a fix.
- Compare trade count, WR, exit distribution, and pick count.
- Confirm chart markers, table rows, and summary stats all reflect the same contract.
