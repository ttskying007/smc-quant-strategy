# Post-V175 SMC research direction governance

Date: 2026-06-26

## Trigger

Use when the user asks to continue SMC research after a long V175/V185-style investigation, especially with wording like “持续研究/持续迭代/直到有质变/不要无休止迭代”.

## User workflow requirement

For this class of SMC task, do not ask the user to choose the next branch and do not keep producing endless incremental versions. The workflow must be:

1. **Declare gates before researching** — define what is usable and unusable before running another scan.
2. **Review already executed research first** — check skill references/audit artifacts so the same failed branch is not rerun under a new name.
3. **Close branches explicitly** — if a direction fails the fixed gates, mark it closed and stop iterating it.
4. **Continue only if the next step changes information content or mechanism** — e.g. new data layer, new candidate-supply construction, or integration hardening of a passed candidate.
5. **After a gate-passing candidate appears, shift from exploration to stabilization** — verify live guard, current scanner rematerialization, endpoint routing, field pollution, and active-source separation.

## Fixed decision language

Use three labels:

- **Production usable**: passes all declared production gates, T+1=0, non-leaking, endpoint/field checks pass.
- **Shadow/research usable**: promising but not production; may need live guard/current scanner validation.
- **Unusable/closed**: fails gate due leakage, T+1, micro-profit pollution, weak Avg/WR, low n/year concentration, or repeated mechanism failure.

Do not soften “unusable” into “needs more tuning” when the failure mode is structural.

## Post-V175/V185 state to remember

V185 combined supersedes V175 as the current qualitative improvement baseline:

- V175 baseline: `n=247`, `WR=83.81%`, `Avg=6.0493%`, `minYear=38`, `yearWRmin=81.71%`, `micro≈1.21%`, T+1=0.
- V185 combined: `n=334`, `WR=86.23%`, `Avg=6.5628%`, `minYear=41`, `yearWRmin=82.81%`, `micro=0.90%`, T+1=0.
- V185 child alone is not standalone due low year coverage, but V185 combined passes the production-upgrade gate.

Therefore new research should be judged against **V185 combined**, not merely against V175.

## What not to repeat

Do not continue these branches unless a new data source or new mechanism is introduced:

- scalar filters over V128/V167/V172/V175;
- generic BE/partial/trailing exit overlays on V175;
- daily OHLCV fresh generators that only rename SSL/CHOCH/OB/retest patterns;
- market breadth as a standalone alpha gate;
- 60min replay that raises WR via micro-profit pollution;
- low-sample high-Avg pockets with poor year coverage.

## Required next-step shape after a pass

If a candidate like V185 passes gates, the next steps are not more random research. They are:

1. verify current API state (`/api/summary`, `/api/picks`, `/api/live-prices`);
2. check old labels, completed-trade pollution, write flags, active-source separation;
3. inspect live guard semantics (`WATCH_ONLY`, `NON_TRADABLE_CONTEXT`, `BUY_VALID`, etc.);
4. rematerialize only from the latest scanner/dry-run source, not historical trades;
5. only then consider default routing/promotion.

## Report style for Lei

Use compact Chinese tables with clear conclusions. Avoid long exploratory prose. The report should say:

- what is done;
- what is closed;
- what is currently usable;
- what is not usable;
- what the next concrete step is;
- whether the overall goal is complete or blocked.
