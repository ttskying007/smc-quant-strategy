# 三周期状态机 TP 分级执行合同预注册（M0-TP2）

> 状态：PREREGISTRATION_FROZEN | 日期：2026-08-17
> 依据：v676 三周期主轴（第一轮已验证 WR 68.5%）+ v88 liq_then_2r_runner 思路 + V633 经济门槛
> 针对病灶：第一轮 payoff 0.44（TP 命中 70% 但平均盈利 << 平均亏损）—— TP 目标相对 SL 距离不足（RR 结构问题）

## 1. 与第一轮的区别（新执行语义，非调参）

| 项 | 第一轮（CLOSED） | M0-TP2（本预注册） |
|---|---|---|
| TP | 单目标（最近 swing high / 周线 BSL） | **TP1 = 1R 部分止盈 40% + runner** |
| runner | 无（一次全平） | 剩余 60% 目标 = max(2R, 周线 BSL)，**SL 上移 BE** |
| 目的 | - | 在保持 WR 的同时提高 payoff（先落袋 1R，剩余跟随结构） |

## 2. 冻结执行合同

```
入场 E     下一交易日开盘（T+1 严格，入场日禁卖）
SL         min(zone_low, sweep_low) × 0.99（结构双低点，入场前可见）
risk       = entry - SL
TP1        = entry + 1 × risk；命中后止盈 40% 仓位（落袋）
BE         = entry（TP1 命中后 SL 上移至保本）
TP2        = max(entry + 2 × risk, 周线 BSL if > 2R)（剩余 60% runner 目标）
max_hold   40 根日 K
exit       优先级：SL/BE 优先碰撞 → TP1 → TP2；TIME40 收盘
fee        双边 0.20%
T+1        入场当日禁卖，same-bar 冲突 SL 优先
```

## 3. 经济门槛（V633，冻结）

n≥1000、每年≥300、WR≥55%、AvgNet≥+0.5%、PF≥1.15、payoff≥0.70、每年 AvgNet>0、月 n>4、T+1=0

## 4. 判定

- gate_pass 且 payoff > 0.70 → 本执行合同成立，进入后续（2023 数据补全后重验）
- 失败 → CLOSED_NO_VARIANTS（该执行语义关闭，不再调阈值/权重）
- 对照：与第一轮 payoff 0.44 对比，验证 TP 分级是否改善赔率结构
