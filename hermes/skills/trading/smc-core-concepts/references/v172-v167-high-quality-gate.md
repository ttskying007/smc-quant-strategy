# V172 / V167 高质量门禁（2026-06-23）

触发场景：V167 已达到生产可用，但仍需要从“可用”提升到“更高单笔质量”，并且要避免无休止迭代。

## 可用/不可用边界

生产可用：
- n >= 200
- min_year_n >= 35
- WR >= 82%
- AvgPnL >= 3%
- micro_profit_pct <= 1%
- T+1 violations = 0
- 前端字段合同 0 缺失

质量升级可用：
- n >= 200
- min_year_n >= 35
- WR >= 83%
- AvgPnL >= 5.5%
- T+1 violations = 0

低于上述或存在 outcome leak / 字段缺失 / T+1 违规 = 不可用。

## V172 有效规则

在 V167 exact scanner gate 基础上增加两个扫描时可得字段：

```text
v85_zone_width_pct >= 2
AND v132_post_zone_pullback_depth_pct_3 <= 2
```

语义：只保留有足够 OB/zone 宽度，且 reclaim 后 3bar 没有明显回踩破坏的强接管结构。它不是 TP/SL 参数调优，而是候选质量门禁。

## 实测结果

V167 基线：793 笔 / WR 82.09% / AvgPnL +4.5403% / SL率 12.48% / min_year_n 80。

V172：247 笔 / WR 83.81% / AvgPnL +6.0493% / SL率 8.91% / min_year_n 38 / T+1=0。

变化：WR +1.72pp，AvgPnL +1.509pp，SL率 -3.57pp。交易量下降但仍满足生产门槛，属于“质量升级可用”。

## 前端/实时闭环要求

1. 生成隔离目录：`/root/.hermes/smc_opt_v172_v167_high_quality_gate/`。
2. 路由优先级必须 V172 > V167。
3. `/api/picks` 不能只看文件里的历史 live_guard；必须与 `/api/live-prices` 实时价格守门一致。
4. 当前价超过 entry ±1.5%、已到 TP、已破 SL 的候选必须降级 WATCH_ONLY。
5. 验收：`/api/summary` 显示 V172；`/api/picks` 与 `/api/live-prices` 的 BUY 数一致；浏览器 console 0 JS error；页面不出现字段缺失/DNA UNKNOWN。

## 当前实盘状态（2026-06-23）

V172 已提升为前端默认。回测生产可用，但实时价格守门后当前 BUY=0，26 条全部 WATCH_ONLY；因此结论是“策略质量升级完成，但当前没有可买点”。
