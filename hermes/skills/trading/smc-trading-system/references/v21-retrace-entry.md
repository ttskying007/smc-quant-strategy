# V21 三阶段入场逻辑

## 用户发现的致命缺陷 (2026-05-18)

用户查看003027.SZ时发现: T1的OB在2025-12-17价格19元，当前2026-05-18价格26元。序列正确但入场位置与当前行情无关——引擎在OB后第2根K线即入场，不等回撤不等确认。

## V19旧逻辑 (被废弃)

```python
# 旧: 价格在Zone上方1%就入场 → 太松
for j in range(ob_idx + 1, n):
    if closes[j] <= dz_low * 1.01:  # 仅1% buffer
        entry_price = closes[j]      # 当日收盘价入场(非T+1)
        break
```

**三个问题**:
1. 不等回撤: Zone从未被真正测试(价格可能远高于Zone)
2. 不等确认: 没有Pinbar/IDM/反转蜡烛验证 → 可继续下跌击穿Zone
3. T+1不现实: close入场而非次日open → 回测虚高

## V21新逻辑

三阶段流程: 回撤入Zone → 反弹确认 → T+1开盘入场

```python
# Stage 1: 价格回撤进入Zone
in_zone = dz_low * 0.99 <= closes[j] <= dz_high * 1.01

# Stage 2: 反弹确认 (三选一)
# A) Pinbar bounce: 下影线刺破Zone下沿, 实体收回
# B) IDM sweep: 前bar跌破Zone, 当前bar收盘收回
# C) Bull reversal: close > open 且 close > dz_low

# Stage 3: 确认后下一bar开盘买入 (T+1)
entry_bar = j + 1
entry_price = opens[entry_bar]
```

## 回测对比

| | V19 | V21 | 变化 |
|---|---|---|---|
| 交易 | 203笔 | 844笔 | +316% |
| 胜率 | 95.1% | 91.8% | -3.3pp |
| 均盈 | +14.33% | +11.65% | -2.68pp |
| 累计 | +2,909% | +9,833% | +238% |

交易量4倍、累计收益3倍，胜率微降但入场逻辑符合SMC标准。

## Breach检查也修复

旧: 任何close < dz_low*0.98 = 击穿
新: 跌破后3bar内收回(IDM恢复) → 不算真击穿

## 入场确认方式统计 (844笔实测)

| 确认方式 | 笔数 | 占比 | WR | avgPnL | 描述 |
|----------|------|------|-----|--------|------|
| IDM_BOUNCE | 601 | 71.2% | 90.8% | +11.54% | 前bar扫荡穿Zone,当前bar收盘收回 |
| PB_BOUNCE | 127 | 15.0% | 93.7% | +11.72% | 长下影Pinbar刺穿Zone,实体收回Zone内 |
| REV_BOUNCE | 116 | 13.7% | 94.8% | +12.17% | 收盘>开盘且>Zone下沿(多头反转) |

**IDM_BOUNCE是主力**(71%)，但WR最低(90.8%)。**REV_BOUNCE最优**(WR=94.8% avg=+12.17%)但仅占14%。
三种确认方式在引擎中按优先级检测: Pinbar → IDM → REV (先到先得)。

## 入场几何验证

- 69%交易在Zone 5根K线内入场(zone_bar→entry_idx≤5)
- 71%入场价在Zone内部(cost_line的±2%)
- 仅9笔(<1%)入场价低于Zone下沿
- 典型间距: zone→+3~6bar回撤→确认→+1bar入场

## 引擎 `opens` 变量缺失陷阱 ⚠️

V18引擎没有`opens`列表(旧入口逻辑只用`closes`)。V21新逻辑需要`opens[j]`用于:
- Pinbar检测: `wick_low = min(opens[j], closes[j]) - lows[j]`
- T+1开盘入场: `entry_price = opens[entry_bar]`

必须在数据提取处添加:
```python
opens = [b['o'] for b in daily]
```

否则报 `NameError: name 'opens' is not defined`。V18→V21迁移时将整个`for ob in ob_bulls`循环内的入口段重写时容易遗漏。
