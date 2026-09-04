# V306 Opening Gap Source + Morning Persistence Audit

## Trigger
After V302-V305 proved same-source 15m lifecycle and first60/first120 persistence still fail as standalone signals, test the next concrete branch: whether entry-day opening gap source distinguishes real supported takeovers from fake takeovers.

## Scope
- Script: `/root/.hermes/scripts/v25/v306_opening_gap_source_audit.py`
- Result: `/root/.hermes/smc_audit/v306_opening_gap_source_latest.json`
- Rows: 88,351 V305 executable morning candidates
- Symbols: 4,197
- Daily files scanned: 4,905
- Entry dates: 65
- T+1 violations: 0
- No production/frontend/watchlist writes.

## Method
For each V305 candidate, compute entry-day opening-gap context using only entry-time available data:

- `stock_gap = open / previous_close - 1`
- market median gap / gap-up breadth / hot-gap share
- industry median gap / gap-up breadth / hot-gap share
- stock relative gap vs industry and market
- stock gap rank inside industry

Classify source:

| Class | Meaning |
|---|---|
| `INDUSTRY_GAP_LED` | stock gaps up while its industry opens strong vs market |
| `MARKET_GAP_LED` | broad market gap support |
| `STOCK_ISOLATED_GAP` | stock gaps up without market/industry support |
| `UNSUPPORTED_GAP` | stock gaps up but does not fit clear market/industry support |
| `SMALL_GAP` / `NO_GAP_OR_DOWN` | weak/no opening impulse |

Then combine with V305 morning persistence classes.

## Results
Baseline remains weak:

| Scope | N | WR | Avg | SL | GAP_SL |
|---|---:|---:|---:|---:|---:|
| all V305 rows | 88,351 | 39.56% | -0.70% | 51.75% | 4.47% |

Best large diagnostic dimensions:

| Dimension | N | WR | Avg | Months | Notes |
|---|---:|---:|---:|---|---|
| `INDUSTRY_GAP_LED` | 1,462 | 63.27% | +3.84% | 202605/202606 only | Strong but short coverage |
| `INDUSTRY_GAP_LED|MORNING_OK` | 1,060 | 62.55% | +3.74% | 202605/202606 only | Morning persistence adds little beyond industry gap source |
| `UNSUPPORTED_GAP` | 1,343 | 55.99% | +1.79% | 202605/202606 only | Better than baseline but still not production |

Best combos:

| Combo | N | WR | Avg | Month WR |
|---|---:|---:|---:|---|
| `INDUSTRY_GAP_LED + ACC_VWIDE>=5 + SWEEP<0.6` | 90 | 77.78% | +9.73% | 202605 100 / 202606 74.36 |
| `INDUSTRY_GAP_LED + i_gap_up>=65 + m120_iup>=65` | 458 | 71.83% | +5.76% | 202605 71.78 / 202606 71.88 |
| `INDUSTRY_GAP_LED + stock industry gap rank>=80 + RISK>=8` | 524 | 66.98% | +6.74% | 202605 65.20 / 202606 68.35 |

## Interpretation
Opening-gap source is the strongest state layer found after V305: real industry-supported gap opens sharply reduce fake takeover failure and improve both WR and Avg. However, all high-quality pockets are concentrated in 202605/202606 because local 15m/V305 coverage is near-term only, so it cannot be promoted to production or treated as a multi-year conclusion.

Critical mechanism finding:

> The useful signal is not generic first60/first120 persistence. The useful signal is **industry-led opening gap + same-morning industry participation**. This points to board/industry capital transmission rather than individual-stock DNA.

## Closure / Next Step
Do not continue tuning simple gap buckets. V306 proves the promising direction is real-time industry leadership transmission, but current data coverage is too short.

Next research direction:

1. Build `Industry Leadership Transmission` using entry-day first15/first30/first60 industry leaders:
   - identify leading industries at open,
   - measure whether candidate stock belongs to/participates in that leader industry,
   - measure stock rank inside industry,
   - verify whether leader strength persists into first60/first120.
2. If still short coverage, fetch/extend 15m history or use daily board/limit-up proxies only as diagnostics.
3. Do not connect V306 to production until multi-month/longer-history stability is proven.

## Verification
Focused ad-hoc verifier passed:
- compile/import + bucket boundaries
- metrics fixture
- no-write contract
- source-row count recomputation
- T+1=0
- top-combo selector fields contain no outcome fields

Verifier output: `status=PASS`, rows=88,351, symbols=4,197, T+1=0.
