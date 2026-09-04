---
name: smc-signal-verify
version: 1.0.0
description: >
  SMC 信号验证系统。对已识别的 SMC 信号进行多维度验证，
  计算信号质量评分，给出入场/观望/放弃建议。
  当用户说"验证信号"、"这个信号怎么样"、"信号质量"、
  "信号确认"、"入场检查"时触发。
user-invocable: true
metadata:
  category: trading
  emoji: ✅
  tags: [smc, signal-verification, confirmation, entry-check]
  requires_skills: [smc-core-concepts, smc-signal-scanner]
---

# SMC Signal Verify — SMC 信号验证系统

## 概述

对检测到的 SMC 信号进行多维度深入验证，从趋势、流动性、价格区域、
时间维度、多时间框架对齐 5 个方面评估信号质量，给出明确的行动建议。

## 验证工作流

```
原始信号
    │
    ├─ ① 趋势一致性验证 (高TF)
    ├─ ② 流动性验证 (已猎杀? 还有未触动?)
    ├─ ③ 价格区域验证 (在折扣区? PD Array叠加?)
    ├─ ④ 时间验证 (Killzone?)
    └─ ⑤ 多TF对齐验证 (周/日/4H/1H/15min)
           │
           └─ 综合评分 → 入场 / 等待 / 放弃
```

## 5 维验证评分系统

### 信号序列验证 (V19+)

信号前的类型顺序同样重要 — 参考 V19 信号序列评分 (`smc-v11-system` > `references/signal-sequence-patterns.md`):

| 信号序列 | WR | 建议 |
|---------|-----|------|
| Sweep → FVG | 84.6% | ✅ 强烈建议入场 |
| OB → FVG | 90.0% | ✅ 最佳序列 |
| FVG → OB | 100% | ✅ 罕见但完美 |
| OOOOO (连续OB) | 16.7% | ❌ 跳过 |
| SOOSO | 0% | ❌ 跳过 |
| seq_score >= 0.6 | 79% | 建议入场 |
| seq_score >= 0.7 | 92% | 强烈入场 |

### 验证器结果

```python
verification_result = {
    "signal_summary": "BTCUSDT 看涨信号 | SSL Sweep + Bullish FVG + CHOCH",
    "score": 78,
    "grade": "B+",
    "verdict": "观望 — 等待价格回踩 FVG 区域",
    "details": {
        "trend_alignment": {...},
        "liquidity_check": {...},
        "price_zone_check": {...},
        "time_check": {...},
        "multi_tf_check": {...}
    }
}
```

### 1. 趋势一致性验证 (30分)

| 检查项 | 分值 | 通过条件 |
|--------|------|----------|
| 高TF趋势与信号方向一致 | 15 | Daily/Weekly 趋势方向 = 信号方向 |
| 没有高位追入 | 8 | 价格在 Discount Zone 内 |
| CHOCH 已确认 | 7 | 价格已突破结构关键点 |

### 2. 流动性验证 (20分)

| 检查项 | 分值 | 通过条件 |
|--------|------|----------|
| 流动性已猎杀 | 10 | BSL/SSL Sweep 已发生 |
| 上方无未触流动性 | 5 | 上方无明显 EQH 或前高还未测试 |
| 影线比合理 | 5 | Sweep 影线比 ≥ 2.0 |

### 3. 价格区域验证 (25分)

| 检查项 | 分值 | 通过条件 |
|--------|------|----------|
| FVG 是 Unmitigated | 10 | 价格尚未进入 FVG 区域 |
| FVG 强度 ≥ 2 | 5 | FVG gap 宽度 > 平均K线范围 50% |
| OB 在附近 | 5 | OB + FVG 距离 < 5根K线范围 |
| OTE 折扣区 | 5 | 入场点在 0.618-0.79 之间 |

### 4. 时间验证 (10分)

| 检查项 | 分值 | 通过条件 |
|--------|------|----------|
| 当前在 Killzone | 6 | 处于 AM/PM/London Killzone |
| 非重大新闻前后 | 4 | 不在 CPI/FOMC/NFP 前后30分钟 |

### 5. 多时间框架对齐验证 (15分)

| 检查项 | 分值 | 通过条件 |
|--------|------|----------|
| 日线趋势支持 | 5 | Daily 趋势 = 信号方向 |
| 4H 有 FVG/OB | 5 | 4H 图表上有未覆盖的 FVG/OB |
| 1H 结构完整 | 5 | 1H 上出现 CHOCH 后已稳定 |

### 评分等级

| 分数 | 等级 | 含义 | 行动 |
|------|------|------|------|
| 90-100 | S | 圣杯级信号 | 🚀 全力入场，重仓位 |
| 80-89 | A+ | 极强 | ✅ 入场 |
| 70-79 | A | 强 | ✅ 入场，设紧止损 |
| 60-69 | B+ | 中强 | 👀 等更佳入场点 |
| 50-59 | B | 中等 | 👀 等确认K线 |
| 40-49 | C+ | 偏弱 | ⏸ 观望 |
| 30-39 | C | 弱 | ⏸ 观望或放弃 |
| <30 | D | 极弱 | ❌ 放弃 |

## 验证报告模板

```
══════════════════════════════════════════
  SMC 信号验证报告
══════════════════════════════════════════

📌 信号: {symbol} | {signal_type} | {timeframe}
   当前价格: {current_price}

────────────────────────────────────
 ① 趋势一致性 [{trend_score}/30]
────────────────────────────────────
  • Daily趋势: {trend} ✓/✗
  • 折扣区: {in_discount} ✓/✗ (折扣区: {ote_range})
  • CHOCH确认: {choch_status}
  点评: {trend_comment}

────────────────────────────────────
 ② 流动性检查 [{liq_score}/20]
────────────────────────────────────
  • Liquidity Sweep: {sweep_detail}
  • 上/下方流动性: {remaining_liquidity}
  点评: {liquidity_comment}

────────────────────────────────────
 ③ 价格区域 [{zone_score}/25]
────────────────────────────────────
  • FVG状态: {fvg_status} (范围: {fvg_range})
  • OB位置: {ob_detail}
  • OTE折扣区: {ote_detail}
  点评: {zone_comment}

────────────────────────────────────
 ④ 时间检查 [{time_score}/10]
────────────────────────────────────
  • Killzone: {killzone_status}
  • 新闻风险: {news_risk}
  点评: {time_comment}

────────────────────────────────────
 ⑤ 多TF对齐 [{multitf_score}/15]
────────────────────────────────────
  • Daily: {daily_status}
  • 4H: {h4_status}
  • 1H: {h1_status}
  点评: {multitf_comment}

══════════════════════════════════════════
 综合评分: {total_score}/100 → {grade}级
 建议: {verdict}
══════════════════════════════════════════
```

## 快速验证工作流

> ⚠️ **信号准确性前置检查 (V22)**: 在验证前，先确认信号引擎版本及检测准确性。
> 如果用户反馈"信号不准确"，优先执行 `smc-core-concepts` > `references/signal-accuracy-diagnostic.md` 
> 中的逐bar诊断流程，而非直接调参。
> 
> **OB置信度过滤**: SMC2026 OB (confidence=0.65) 仅渲染不交易；LuxAlgo OB (confidence=0.75) 有CHOCH/BOS上下文，用于交易入场。

### 用户交互流程

1. **用户提供**: 标的代码 + 信号方向 + 时间框架
2. **获取数据**:
   - 加载 `smc-core-concepts` 了解信号判断方法
   - 加载 `smc-signal-scanner` 使用检测算法
   - 调用 Hubble API 获取多TF K线数据
3. **运行 5 维验证**:
   - 使用 verify_signal() 函数
   - 输出验证报告
4. **给出建议**: 入场/等待/放弃 + 推荐入场价格区间

### 快速验证函数

```python
def quick_verify(symbol, direction, market='us', timeframe='1d'):
    """
    快速验证一个信号
    Example: quick_verify('AAPL', 'long', 'us', '1d')
    """
    # 获取多TF数据
    tfs = {'1w': None, '1d': None, '4h': None, '1h': None}
    if timeframe != '1w':
        tfs['1w'] = fetch_klines(market, symbol, 'weekly', 50)
    tfs['1d'] = fetch_klines(market, symbol, 'daily', 200)
    if timeframe != '1d':
        tfs['4h'] = fetch_klines(market, symbol, '60min', 300)
        tfs['1h'] = fetch_klines(market, symbol, '30min', 500)
    
    # 运行验证
    result = verify_signal(tfs, direction)
    return result
```

### 入场检查清单（用于验证的最后确认）

```
入场前最后检查:
  ✅ 方向与 Daily 趋势一致
  ✅ 流动性已被猎杀 (Sweep 发生)
  ✅ 有 Unmitigated FVG
  ✅ 有 OB 支撑/阻力
  ✅ 价格在 Discount Zone
  ✅ 当前是 Killzone
  ✅ 多TF对齐
  ✅ 最后一根K线收在 FVG/OB 方向
  ✅ 盈亏比 ≥ 1:2
  ✅ 止损距离合理 (不超过 ATR 2x)

检查通过数 ___ / 10
8+ = 直接入场
6-7 = 等一根确认K线
<6  = 观望或放弃
```