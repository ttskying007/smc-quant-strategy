# V107 TRADEABLE_REGIME Audit Lesson

Use this after V104 strict reclaim semantics pass and V105/V106 reject TP/SL micro-tuning.

## Purpose

V107 is research-only market-state validation. It must not touch production/API/frontend unless promotion gates pass. It keeps V104 structural TP/SL unchanged and adds only ex-ante market breadth + entry-quality gates.

## Required inputs

- V104 strict reclaim trades: `~/.hermes/smc_opt_v104_strict_reclaim/v104_trades.json`
- Full raw K-line cache: `~/.hermes/kline_cache/*_daily_300.json`
- Compute full-market breadth on each entry date using only bars at or before that date.

## Valid features

Allowed ex-ante features:
- full-market `up20_pct`, `up60_pct`, `ret20_pos_pct`, `ret60_pos_pct`, `avg_ret20`, `avg_ret60`;
- signal-family / trend-state labels already known at entry;
- V104 entry-quality fields such as `risk_pct`, `retrace_pct`, `chase_pct`, `disp_atr`.

Forbidden for promotion:
- MFE/MAE or any post-entry outcome field;
- historical completed-trade whitelist;
- TP < 1R micro-profit exits or tightened SL hacks;
- routing research rows into `/api/picks`, `/api/live-prices`, monitor state, or frontend defaults.

## Findings from 2026-06-19 V107 audit

Artifact: `~/.hermes/smc_audit/v107_tradeable_regime_audit_20260619.json`.

Baseline V104: 487 trades, WR 54.62%, SL 42.92%, avg +0.4248%, stable3=8.

Regime split with unchanged structural exits:

| Regime | n | WR | SL | Avg | Stable3 | Interpretation |
|---|---:|---:|---:|---:|---:|---|
| BULL_EXPANSION | 143 | 69.93% | 28.67% | +2.1987% | 3 | Directionally right but still below WR>=70/stability gate |
| BULL_RECOVERY | 54 | 51.85% | 46.30% | +0.1183% | 3 | Not tradable alone |
| REPAIRABLE_RANGE | 98 | 54.08% | 41.84% | +0.5305% | 0 | Not tradable |
| NO_TRADE_BEAR_STRESS | 176 | 39.77% | 57.39% | -1.3914% | 5 | Hard block / no-trade regime |
| MIXED_CHOP | 16 | 93.75% | 6.25% | +4.9342% | 2 | Too small; research clue only |

Best V107 rule: `TRADEABLE_ONLY + risk<=8 + retrace 20-40 + chase<=4`; 77 trades, WR 80.52%, SL 19.48%, avg +3.5812%, stable3=7, but n<100 and stable3<12, so **not promoted**.

## Promotion gate

V107 can only promote if all hold:

- semantic audit fail_count == 0;
- structural exits unchanged from V104;
- no micro TP/SL tuning;
- n >= 100;
- WR >= 70%;
- SL <= 30%;
- stable3 months >= 12;
- current fresh scan can generate active candidates without using historical trades.

If no rule passes all gates, report `RESEARCH_ONLY_NOT_PROMOTED`. The valid next direction is not TP/SL tuning; it is deeper signal semantic re-derivation inside BULL_EXPANSION/MIXED_CHOP to find why only a small subset is structurally valid.
