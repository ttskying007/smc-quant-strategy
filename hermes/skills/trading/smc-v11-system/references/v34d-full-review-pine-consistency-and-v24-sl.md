# V34D 全量 Review：Pine 一致性、V24 止损归因、当前缺口

日期：2026-05-23

## 背景

用户指出前端显示 `184笔交易 / 50%胜率 / 92笔止损`，要求全面排查：

- 是信号定义问题、入场点问题、组合方式问题，还是未到入场点位？
- 是否已经与用户提供的 Pine/LuxAlgo 风格脚本一致？
- 重点检查 BOS/CHOCH/MSS、OB、FVG、BPR、BRK、EQL、LV、OTE、PB、RB、Sweep。
- 解释过多止损、入场价格不对、过早止盈止损是否解决。

## 关键结论

### 1. 184笔/50%/92止损来自旧 V24，不是当前 V34D

前端曾默认加载：

```text
/root/.hermes/smc_opt_v24/v24_trades.json
```

该结果不应再作为当前引擎质量判断依据。已将 `smc_unified.py` 默认切换至：

```text
/root/.hermes/smc_opt_v34d_final/v34_trades.json
```

V34D 当前摘要：

```text
7 trades / 85.7% WR / 1 SL / SL rate 14.3% / avg_pnl 2.19%
```

注意：V34D 是干净基线，但样本数太少，不能视为最终系统。

### 2. V24 的止损主因不是 SL 参数，而是信号污染 + 过期 zone + 追高入场

V24 病理特征：

- `ctx_seq_contains_no_ssl = 156 / 184`：多数交易缺少 SSL/Sweep 前序，不符合 SMC 逻辑。
- `ctx_seq_contains_pinbar_onlyish = 84`：Pinbar 被混入核心序列；用户明确要求 PB 只能作入场确认，不是独立 zone/type。
- FVG_Bull 交易 124 笔，胜率约 45.2%，止损率约 54.8%，是主要污染源。
- `zone_age` 平均约 42 bars，P75 约 61 bars，P90 约 86 bars，最大约 141 bars：大量过期 zone。
- `bos_dist_pct` 平均约 14.26%，P90 约 23.1%，最大约 43.2%：离结构突破过远，存在滞后/追高。
- 92 笔止损中 37 笔 1 bar 内止损，59 笔 3 bars 内止损：不是正常波动，而是信号/入场质量问题。

结论：不要继续调 V24 的 SL/TP；V24 应作为反例废弃。

### 3. V34D 已解决的部分

V34D 基线逻辑：

```text
SSL sweep → MSS/CHOCH context → LuxAlgo 同源 OB → OB 回踩确认 → 确认K收盘入场
```

已改善：

- 不再把 PB 当独立信号。
- OB 改为 LuxAlgo `storeOrderBlock()` 同源语义。
- Zone 质量门槛：`zone_width <= 2%`。
- 结构到确认门槛：`struct_to_confirm <= 20 bars`。
- V34D 样本中平均 `struct_to_confirm ≈ 8.29 bars`，最大约 15；平均 OB 宽约 1.23%，最大约 1.92%。

### 4. 当前不能声明“全部 Pine 一致”

逐信号状态：

| 信号 | 当前状态 | Pine 一致性判断 | 注意事项 |
|---|---|---|---|
| BOS | V34D 使用 LuxAlgo leg + close crossover/crossunder | 接近 | 仍需逐事件 diff |
| CHOCH | 同 BOS，并根据趋势 bias 分类 | 接近 | 仍需逐事件 diff |
| MSS | 本地定义为 CHOCH + recent SSL + displacement | 部分 | 需与用户 Pine MSS 逐事件确认 |
| OB | 同源 LuxAlgo `storeOrderBlock` 思路 | 接近 | 当前主要交易化 bull OB |
| FVG | pine_like 有实现，V34D 禁用 | 未完成 | V24 中 FVG 是污染源，不能直接恢复 |
| BPR | 有基础 opposing-FVG-overlap | 未完成 | 未交易化，需避免 O(n²) 爆炸并审计语义 |
| BRK / Breaker | V34D 未实现 | 否 | 旧实现不可直接复用 |
| EQL/EQH | pine_like 有，V34D sweep 未合并 pool | 部分 | 需实现 liquidity pool sweep |
| LV | 有简单 displacement candle 版本 | 不完整 | 非完整 liquidity void 语义 |
| OTE | 有图表/结构区间概念 | 不完整 | anchor 和交易条件未审计 |
| PB | 仅应作为确认 | 方向正确 | 禁止作为独立 zone/type |
| RB | V34D 未实现 | 否 | 需新增/审计 |
| Sweep | V34D 有 wick-through + close-reclaim swing sweep | 部分 | 缺 EQL/EQH pool sweep |

## Workflow Lessons for Future Sessions

1. **先确认前端当前加载的版本和交易文件**：不要直接相信页面显示的交易数/胜率。检查 `smc_unified.py` 的默认版本、API summary、实际 JSON 文件路径。
2. **止损过多必须先做病理归因，不先调 SL/TP**：至少输出 zone_age、bos_dist_pct、struct_to_confirm、MFE/MAE、1/3 bar SL、ctx_seq、zone_type 分桶。
3. **旧版本混合信号不可直接修补**：如果 ctx_seq 中缺 sweep、PB 混入核心序列、FVG 未绑定结构/流动性，就应废弃该版本作为污染源，而不是参数优化。
4. **Pine 一致性必须逐事件 diff**：不要只说“按 Pine 重写”。需要在同一股票同一 K 线比较 index、price、zone 边界、方向和 mitigation 状态。
5. **恢复信号必须单信号隔离回测**：OB-only、FVG-only、BPR-only、OTE-only、BRK-only、RB-only 分别跑，禁止一次性混合导致污染源不可定位。
6. **交易数少不代表失败，但只能称为干净基线**：V34D 的 7 笔/85.7% 可作为基线，不能作为最终系统。下一步是把 FVG/EQL/BPR/OTE/BRK/RB 按 Pine 语义逐个接回。

## Recommended Next Build Order

1. BOS/CHOCH/MSS/OB/Sweep 逐事件 Pine diff。
2. EQL/EQH liquidity pool → Sweep → MSS 集成。
3. FVG 只允许 `SSL sweep → MSS/CHOCH → displacement FVG → 回踩FVG → 确认`，禁止孤立/过期/无结构 FVG。
4. BPR 独立实现与性能优化，再单独回测。
5. OTE、BRK、RB 分别实现、逐事件审计、单独回测。
6. 最后才组合多信号，并保留每笔交易的 source_event、zone_source、confirm_type、struct_to_confirm、zone_age、entry_vs_zone、MFE/MAE。