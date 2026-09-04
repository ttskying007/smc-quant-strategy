# Phase2 Strict L→D Field-Contract + Per-Trade Closure

## Trigger

Use this reference when a Phase2 / V66 / V68 SMC task combines:

- `/monitor` missing or blank `选股日期` / `加入日期`
- `/monitor` or `/live` blank Zone, cost line, or volatility
- strict L→D backtests that look valid in aggregate but need per-trade semantic replay
- user asks for “全面详细深入验证” and “复盘每笔交易”

## Durable session lesson

Do not treat this as a frontend-only display bug. Close three layers together:

1. **Physical JSON field contract** — repair source files, not only rendered HTML.
2. **API contract** — `/api/picks` and `/api/live-prices` must both show zero blanks.
3. **Browser DOM contract** — verify real table headers and first rows from `/monitor` and `/live`.

For strategy changes, do not promote a candidate until every trade passes semantic ordering, T+1, and required-field gates.

## Field contract checklist

Required pick/live fields:

| Logical field | Accepted sources |
|---|---|
| select date | `pick_date`, `select_date`, `conf_date`, `confirm_date`, `retrace_date`, `entry_date`, `signal_date`, `date` |
| join date | `join_date`, `joined_date`, `joined_at`, `created_at`, fallback to select date |
| zone | `zone_type` or both `zone_low` + `zone_high`; also sync `dz_low` / `dz_high` |
| cost line | `cost_line`, `smart_money_cost`, `v25_cost_line`, fallback to zone midpoint, then entry price |
| volatility | `volatility_pct`, `risk_pct`, `v25_sl_pct`, `v25_atr_pct`, `v25_vol_class` |

Treat these as blank for this class of task:

```python
None, '', 0, '0', '-', '0.00', '0.00%'
```

## Strict L→D semantic gates

Candidate sequence:

```text
SSL_SWEEP -> BULL_DISPLACEMENT -> FVG_DEMAND -> RECLAIM_ENTRY
```

The important bug found in-session: a strict FVG candidate must not enter on the same bar that creates/forms the POI. Enforce:

```python
entry_idx > max(zone_bar, confirm_bar)
```

For bullish FVG audit, `zone_bar` may equal `confirm_bar` or be `confirm_bar + 1` depending on whether the implementation labels the middle or third candle of the three-candle FVG. A valid audit should allow:

```python
liq_bar <= zone_bar <= confirm_bar + 1
entry_idx > max(zone_bar, confirm_bar)
```

Do **not** flag `retrace_pct == 0` as a missing field. It can be a valid shallow/edge touch value.

T+1 gate remains hard:

```python
exit_date > entry_date
# simulate from entry_idx + 1, never same trading day
```

## Acceptance pattern from the repaired candidate

After fixing same-bar FVG entry and re-auditing all trades:

| Gate | Required result |
|---|---:|
| semantic_order_fail | 0 |
| t_plus_1_fail | 0 |
| field_contract_fail | 0 |
| audit_fail | 0 |

Example candidate contract:

```text
Phase2_Strict_LD_FVG_RR08_Risk6_8
filters:
  zone_type = FVG_Demand
  rr_target = 0.8
  risk_pct in [6, 8]
```

In the verified run this produced 6543 trades, WR 61.76%, avg PnL +0.7303%, and all per-trade gates passed. Do not hard-code these numbers as future truth; use them as a sanity check for similar full-market runs.

## Verification commands/patterns

After any field-contract or strict-LD repair:

```bash
python3 -m py_compile /root/.hermes/scripts/smc_unified.py \
  /root/.hermes/scripts/v25/phase2_strict_ld_backtest.py \
  /root/.hermes/scripts/v25/phase2_ld_audit_and_extract.py
```

Then verify:

1. Physical files: V66/V68 picks/trades zero blank counts.
2. `/api/picks`: zero blanks for select date, join date, zone, cost, volatility.
3. `/api/live-prices`: zero blanks for pickDate, joinDate, zone, costLine, volClass.
4. Browser DOM:
   - `/monitor` table 1 has `选股日期`, `加入日期` populated.
   - `/monitor` active picks table has `引擎`, `选股日期`, `加入日期`, `Zone`, `成本线`, `波动` populated.
   - `/live` has `选股日`, `加入日`, `成本线`, `Zone`, `波动` populated.

## Reporting to Lei

Report compactly with tables:

- What was fixed
- Full-market candidate metrics
- Audit gates with zero-fail counts
- API zero-blank counts
- DOM verification examples
- Explicitly state whether production was promoted or only candidate data was generated

Do not claim “完成” unless frontend/API/physical files and per-trade gates are all verified.
