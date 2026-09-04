# V40 Replay Exit Autopsy — 选股/入场/出场三段复盘

Date: 2026-05-23

## Trigger
用户指出不能只看交易数、WR、SL/TP 聚合指标；必须按顺序复盘：

1. 选的股票/信号到底正确不正确。
2. 入场点到底正确不正确。
3. 出场到底正确不正确。

重点案例类型：刚卖出不久就涨、没有吃到趋势就卖、买入超过 30 天仍不涨、持股 3 天卖出但第 4/5 天才涨。

## Durable workflow correction
以后迭代 SMC 交易系统时，不要直接从 SL 触发多/交易数少推断信号不好。必须先做 replay autopsy：

1. **信号/选股正确性**：买入后 10/20/30/45/60 bar 的 MFE/MAE；若 30/60 天有足够 MFE，说明股票信号可能正确。
2. **入场正确性**：入场后是否先大幅 MAE、多久到 2R/3R/5%、是否超过 30 bar 仍无趋势；超过 30 天仍不涨通常归因信号或入场错误。
3. **出场正确性**：卖出后 1/3/5/10/20/30 bar 是否继续上涨；若刚卖后上涨或趋势继续，归因卖早/出场规则错误。

## V39 autopsy result
Files:

- `/root/.hermes/scripts/v25/v39_replay_autopsy.py`
- `/root/.hermes/smc_opt_v39/v39_replay_autopsy.json`

Summary:

```json
{
  "n": 13,
  "signal_correct_rate": 84.6,
  "entry_bad_count": 2,
  "sold_early_5d_count": 10,
  "sold_early_10d_count": 11,
  "held_too_long_no_move_count": 0,
  "too_slow_or_bad_signal_count": 3,
  "avg_mfe_10": 4.08,
  "avg_mfe_30": 10.42,
  "avg_mfe_60": 20.44,
  "avg_mae_10": -1.99,
  "avg_post_exit_mfe_5": 3.78,
  "avg_post_exit_mfe_10": 6.66,
  "median_bars_to_2r": 19,
  "median_bars_to_5pct": 21
}
```

Diagnosis:

- 选股/信号不是主问题：30日 MFE 达标率 84.6%，平均 30日 MFE 10.42%，60日 MFE 20.44%。
- 入场有少量问题：entry_bad=2/13；无超过 30 天仍不涨案例。
- 出场是主问题：卖出后 5 日继续涨 10/13，卖出后 10 日继续涨 11/13；V39 trailing stop 过早，未吃到趋势。

## V40 fix
Files:

- `/root/.hermes/scripts/v25/v40_exit_grid.py`
- `/root/.hermes/scripts/v25/v40_final_engine.py`
- `/root/.hermes/smc_opt_v40/v40_trades.json`
- `/root/.hermes/smc_opt_v40/v40_metrics.json`
- `/root/.hermes/smc_opt_v40/v40_replay_exit_report.json`

Exit rule:

- max_hold: 75 bars
- TP1: 1.5R, sell 30%
- TP2: 3.2R, sell 25%
- runner: keep 45%, no hard TP3 full close
- break-even: after >=3 bars and >=1R, stop to +0.1%
- trailing: activate only after 6R, lock high_water - 1.2R

V39 → V40:

| Version | Trades | WR | SL rate | Avg PnL | Total PnL |
|---|---:|---:|---:|---:|---:|
| V39 | 13 | 84.6% | 7.7% | +2.60% | +33.79% |
| V40 | 13 | 92.3% | 7.7% | +4.44% | +57.67% |

## Pitfall
Do not optimize exits only by static TP/SL ratios. For this SMC system, many valid signals need 2-4 weeks to realize: median bars_to_2R=19, median bars_to_5pct=21. A trailing stop that activates too early can convert correct signals into small wins and miss the actual trend.
