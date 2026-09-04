# V93 RECOVERY 二级门禁与 TIME_STOP 高 MFE Runner 复盘

## 触发场景

用于 SMC 全量回测/扫描系统中，已经确认主线信号与 zone_mid 入场改善后，继续处理两个剩余结构问题：

1. `RECOVERY` 市场状态整体表现弱，但不能简单全禁，需要找可恢复子桶。
2. `TIME_STOP` 中存在高 MFE 样本，说明信号有效但收益捕获不足，需要 runner/延迟退出逻辑，而不是简单调大 TP/SL。

## 关键流程

### 1. RECOVERY 不可整体恢复，必须二级门禁

全量 `zone_mid_limit + micro` 复盘口径：

| 桶 | n | WR | SL率 | 结论 |
|---|---:|---:|---:|---|
| RECOVERY 全量 | 5811 | 84.08% | 15.80% | 不可整体放开 |
| RECOVERY_REJECT | 5556 | 83.89% | 15.98% | 继续隔离 |
| RECOVERY_BULL_FAST_DEEP_RISK | 255 | 88.24% | 11.76% | 可作为 shadow/watchlist 子桶 |

二级门禁定义：

```python
market_state == 'RECOVERY'
daily_state == 'BULL_CONTINUATION'
hold_bars <= 1
zone_width <= 1.6
risk_signal > 5
```

标签：`RECOVERY_BULL_FAST_DEEP_RISK`

注意：该桶总体过线，但 2023/2026 年度切片仍未达生产阈值（2023 WR 85.37%/SL 14.63%，2026 WR 85.56%/SL 14.44%），所以只能作为 shadow/watchlist 标注，不能替代生产基线或整体放开 RECOVERY。

### 2. TIME_STOP 高 MFE 是收益捕获问题，不是信号失败

高 MFE TIME_STOP 口径：

| 桶 | n | WR | SL率 | avg | avg MFE-R |
|---|---:|---:|---:|---:|---:|
| TIME_STOP 且 MFE>=1.5R | 548 | 100.00% | 0.00% | +1.9693% | 42.101R |

结论：这类样本已经证明信号有效，问题是退出没有吃到后续收益。不要先调大 TP/SL；应设计只作用于 `TIME_STOP && MFE>=1.5R` 的 runner/延迟退出。

已验证 runner 方案：

| 方案 | WR | SL率 | avg | 说明 |
|---|---:|---:|---:|---|
| baseline zone_mid_micro | 87.99% | 11.92% | +1.3536% | 原始 |
| delay_to_1_5r_floor | 87.99% | 11.92% | +1.3536% | 基本无提升 |
| delay_to_2r_floor | 87.99% | 11.92% | +1.3621% | 小幅提升 |
| mfe_50pct_cap_3r | 87.99% | 11.92% | +1.3908% | 最优，且不增加 SL |

推荐规则：`mfe_50pct_cap_3r`：

```text
IF exit_reason == TIME_STOP AND mfe_r >= 1.5:
    delayed exit captures 50% of MFE, capped at 3R
```

该规则是审计层/候选规则，不能直接声称实盘可实现；正式接入前必须基于未来已知性重放退出路径，确保不使用未来 MFE 做当下决策。

## 实现与测试锚点

- 审计脚本：`/root/.hermes/scripts/v25/v93_recovery_time_runner_audit.py`
- 回归测试：`/root/.hermes/scripts/v25/test_v93_recovery_time_runner_audit.py`
- V91 scanner 接入字段：
  - `v93_recovery_gate_label`
  - `v93_recovery_pass`
  - `v93_time_stop_runner_variant`
  - `v93_time_stop_runner_rule`

## 验收要求

1. RECOVERY 二级门禁必须报告整体和逐年切片，不能只报总体 WR/SL。
2. RECOVERY 子桶即使总体过线，如年度切片不过线，只能 shadow/watchlist，不能生产晋级。
3. TIME_STOP runner 必须证明：
   - 只作用高 MFE TIME_STOP；
   - 不增加 SL；
   - 不降低 WR；
   - 平均收益提升；
   - 不使用未来 MFE 作为实盘即时决策。
4. 前端/API 验收必须继续保持选股日期、加入日期、Zone、成本线、波动、入场、SL、TP、RR 字段零空值。
