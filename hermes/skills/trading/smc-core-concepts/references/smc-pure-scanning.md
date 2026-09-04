# SMC 纯结构选股方法论 (2026-05-15)

## 核心原则

**不使用任何通用技术指标**(MA, 百分比, 距N日高/低等)。SMC选股仅基于市场结构。

## SMC Long Entry 完整序列

```
Demand Zone形成(OB_Bull/FVG_Bull at swing low)
  → 价格从Zone反弹确认(rally > zone_high + ATR×0.3)
  → SSL Sweep清扫最近摆动低点
  → CHOCH_Bull结构反转确认
  → 价格回撤到Demand Zone = 最优入场
```

**关键**: 入场在Zone的**回撤测试**(retest), 不是在Zone形成时。

## Score评分体系

每个Demand Zone按SMC事件评分:

| 事件 | 分数 | 说明 |
|------|------|------|
| Zone确认(价格反弹离开zone) | +1 | 证明zone被尊重 |
| SSL Sweep在zone附近 | +2 | 核心SMC:流动性清扫 |
| CHOCH_Bull在zone附近 | +2 | 结构反转确认 |
| 价格在zone内(dz_low ≤ close ≤ dz_high) | +3 | 最优:精确回撤 |
| 价格略破成本线(dz_low×0.97 ≤ close < dz_low) | +2 | 跌破但可接受 |
| 价格接近zone上方(dz_low < close ≤ dz_high×1.03) | +1 | 接近中 |

- **Score ≥ 5**: 至少zone确认 + 1个SMC事件 + 回撤接近 → 可考虑
- **Score ≥ 8**: zone内 + 全序列(Sweep+CHOCH) → 高概率

## 错误的选股方式

❌ `close > MA20` — 通用指标, 非SMC
❌ `距60日高 ≤ 20%` — 任意百分比, 非SMC
❌ `最近N bar触发OB_Bull` — 只看信号触发, 不看回撤
❌ `历史均盈排序` — 选股基于过去, 非当前结构

## 正确的SMC选股

✅ 找Demand Zone(OB_Bull) — 结构性支撑
✅ 验证zone被价格反弹确认 — 证明zone有效
✅ 检查SSL Sweep — 流动性清扫=机构建仓前奏
✅ 检查CHOCH — 结构反转=趋势改变
✅ 当前价格回撤到zone — 入场时机

## 扫描器实现

扫描器(`/tmp/scan_smc.py`)遍历所有股票K线缓存:
1. 检测所有V22信号
2. 对每只股票找最佳Demand Zone
3. 验证SMC序列完整性
4. 按Score排序输出

结果: A股4,905只 → Score≥5: ~774只 → 完整序列(Sweep+CHOCH): ~195只

## 组合信号(序列)诊断

组合信号少不是因为检测不到，而是因为Sweep/CHOCH和OB_Bull在大多数股票上触发于**不同的摆动点**。它们各自检测不同的价格水平，鲜少恰好对齐到同一个SMC序列。

宽松检测(±20bar窗口): 71%的OB_Bull有附近Sweep或CHOCH
严格检测(完整LIQ→CHOCH→OB序列): 约5%的股票满足

这不是扫描器的缺陷，而是市场的真实状态——完整的SMC入场序列本来就是稀缺的高质量信号。
