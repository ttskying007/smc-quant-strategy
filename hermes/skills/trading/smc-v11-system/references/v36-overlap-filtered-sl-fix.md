# V36 重叠去重 + RANGE FVG 止损修复

## 触发场景
用户发现止损触发较多，要求全面排查：是信号问题、入场点问题、SMC 信号定义问题、组合方式问题，还是未到入场点位。

## 关键结论
V35 止损增多不是 SL/TP 公式主因，而是信号组合污染：

1. **同一 executable entry 被 OB/FVG 重复交易**：同一 symbol + entry_index 同时产生 OB 和 FVG trade，导致同一套 SMC story 被重复计算，且弱 FVG 污染更干净的 OB。
2. **TREND_UP FVG 是追涨型失效簇**：V35 TREND_UP cohort WR=42.9%、SL=57.1%、avg_pnl=-0.51；很多不是需求区回踩，而是后段延续追涨。
3. **BPR 语义仍过宽**：没有 standalone profitable cohort，不可交易。
4. **SL/TP 不应先改**：V36 保持 V34/V35 SL/TP 不变，仅修复组合和入场过滤后，SL率从 28.6% 降至 8.3%，证明主因在信号/组合而非出场公式。

## 修复规则
V36 规则：

```text
SSL → MSS/CHOCH → OB/FVG → 真回踩 → zone内确认 → 入场
```

硬过滤：

```text
1. 同一 symbol + entry_index 只保留一笔，优先级 OB > FVG > BPR
2. FVG 只允许 RANGE market_state
3. 禁止 TREND_UP FVG 交易
4. BPR 继续隔离，仅保留检测/审计
5. 未触达 zone 不入场
6. 不允许 next-open 追价
7. SL/TP 保持不变，除非组合过滤后仍证明出场模型是主因
```

## 全量验证结果

| 版本 | 交易数 | WR | SL数 | SL率 | Avg PnL | Total PnL |
|---|---:|---:|---:|---:|---:|---:|
| V34D OB-only | 7 | 85.7% | 1 | 14.3% | +2.19% | +15.32% |
| V35 加 FVG/BPR | 21 | 66.7% | 6 | 28.6% | +0.98% | +20.68% |
| V36 overlap-filtered | 12 | 83.3% | 1 | 8.3% | +1.72% | +20.64% |

V36 分组：

| 类型 | 交易数 | WR | SL率 | Avg PnL |
|---|---:|---:|---:|---:|
| OB | 7 | 85.7% | 14.3% | +2.19% |
| FVG | 5 | 80.0% | 0.0% | +1.06% |

V36 所有交易均为 RANGE market_state。

## 代码/产物

```text
/root/.hermes/scripts/v25/v36_engine.py
/root/.hermes/smc_opt_v36/v36_trades.json
/root/.hermes/smc_opt_v36/v36_picks.json
/root/.hermes/smc_opt_v36/v36_setups.json
/root/.hermes/smc_opt_v36/v36_metrics.json
/root/.hermes/smc_opt_v36/v36_fix_report.json
```

前端同步：

```text
/root/.hermes/scripts/smc_unified.py
ACTIVE_VERSION = V36
/api/summary => total_trades=12, win_rate=83.3, avg_pnl=1.72, signals={OB:7,FVG:5}
```

## 未来执行纪律
当用户要求“止损多/入场不对/信号不准”排查时，不要先改 SL/TP。必须先做：

1. 按 zone_type / market_state / conf_type / entry_mode / entry_index overlap 分解 SL 来源。
2. 检查同一 entry 是否重复交易多个 PD array。
3. 检查 FVG 是否在 TREND_UP 中变成追涨 continuation，而非回踩 demand。
4. 隔离未通过 standalone cohort 的 BPR/LV/OTE/RB。
5. 保持 SL/TP 不变做 A/B，只有组合过滤后仍无改善，才进入出场模型修复。
