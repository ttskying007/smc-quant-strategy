# V296 second60 anti-chase + lifecycle gate

## 触发场景

V294 的 `k=2, market_up>=65, industry_up>=50, stock hold zone` 已把 V292/V293 first60 基线提升到 181笔 / WR 71.27 / Avg +2.85 / 2025 WR 74.44 / 2026 WR 68.13 / GAP_SL 1.66 / T+1=0，但 202602-202604 月度仍弱。V295 复盘确认弱月根因是 `浅扫 + 宽/中蓄势 + 弱/中 impulse + 接管后仍下探`，不是 T+1、微利或简单行业阈值。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v296_second60_antichase_lifecycle_gate.py`
- 结果：`/root/.hermes/smc_audit/v296_second60_antichase_lifecycle_latest.json`
- 输入：V293 enriched rows 659笔（V292 `first60_bull_hold_zone`）。
- 方法：重新模拟 k2/k3 second/third 60m persistence，只保留可在 entry-session 第 k 根 60m 收盘时可得字段；再测试 anti-chase / lifecycle gates。
- 写入：no-write；不写 production/frontend/watchlist。
- T+1：退出从下一交易日开始，best T+1 violations=0。

## 基线对比

| 层级 | N | WR | Avg | 2025 | 2026 | 月度最低 | SL% | GAP_SL% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V293 source first60 hold | 659 | 56.60 | +1.09 | 62.21 | 53.85 | 38.36 | 38.39 | 2.73 |
| V296 all persistence candidates | 356 | 68.26 | +2.53 | 75.00 | 60.71 | 38.89 | 23.88 | 2.25 |
| V294 best k2 persistence | 181 | 71.27 | +2.85 | 74.44 | 68.13 | 45.00 | 21.55 | 1.66 |
| V296 best gate | 122 | 72.95 | +3.14 | 69.70 | 76.79 | 58.33 | 19.67 | 3.28 |

## 最佳规则

`post_hold_min_pct<=4 & exclude_midwide_shallow_nonstrong`

其中 `exclude_midwide_shallow_nonstrong` 表示排除：

```text
sweep_bucket == SWP_SHALLOW<1
AND acc_bucket in {ACC_WIDE>=7, ACC_MID4_7}
AND impulse_bucket != IMP_STRONG>=1.5
```

结果：

| N | WR | Avg | 2025 | 2026 | 月度WR | T+1 |
|---:|---:|---:|---:|---:|---|---:|
| 122 | 72.95 | +3.14 | 69.70 | 76.79 | 202511 66.67 / 202512 70.18 / 202601 100 / 202602 58.33 / 202603 63.64 / 202604 66.67 / 202605 60 | 0 |

## 机制结论

1. V295 的弱月诊断成立：过滤 `中/宽蓄势 + 浅扫 + 非强 impulse` 的假接管后，弱月月度 WR 从 V294 的 45/45/50 提升到 58.33/63.64/66.67。
2. `post_hold_min_pct<=4` 有效：说明 second60 hold 之后仍大幅下探的票，不是真接管而是冲高回落/派发。
3. 继续提高市场/行业阈值不是主解；真正有效的是个股自身 lifecycle 质量门禁。
4. 该规则样本只有 122 笔，月份仅覆盖 2025-11 到 2026-05，仍不可生产；但它把 V294 的弱月缺陷闭环为明确结构门禁。
5. 下一轮不应继续调 `market_up/industry_up/k`，而应验证该 lifecycle gate 是否能在更长历史/更原生 intraday 数据上复现：需要 60m/15m 更长历史，或构造同源 `ACC→MAN→DIS` 操盘生命周期生成器。

## 验证

Focused ad-hoc verification PASS：

```json
{
  "status": "PASS",
  "checked": [
    "sf helper",
    "metrics helper",
    "lifecycle gates",
    "summary contract",
    "artifact rows + gate invariants"
  ],
  "source_n": 659,
  "best_rows": 122,
  "t1_violations": 0
}
```

该验证不是完整 canonical test suite green。
