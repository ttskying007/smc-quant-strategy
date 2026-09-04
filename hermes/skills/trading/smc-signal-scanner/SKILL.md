---
name: smc-signal-scanner
version: 1.1.0
description: >
  SMC 信号扫描器。使用 Hubble 数据服务扫描股票/加密货币市场的
  15种 SMC 信号：FVG、IFVG、Sweep、OB、CHOCH(V1+V2)、MSB、OTE、
  PD Array、FVG Stack、Equal HL、Volume Spread、Killzone。
  当用户说"扫股"、"选股"、"找信号"、"扫描SMC"、"哪个股有FVG"、
  "今天有什么信号"、"扫币"时触发。
user-invocable: true
metadata:
  category: trading
  emoji: 🔍
  tags: [smc, scanner, screening, fvg, order-block, signal-detection, ifvg, choch, volume, pd-array]
  requires_skills: [smc-core-concepts, hubble-skill-router]
---

# SMC Signal Scanner — SMC 信号扫描器 (v1.1)

## ⚠️ API Status (2026-05-09)

Hubble API 已过期(401 Unauthorized)。**当前所有数据依赖本地缓存** (4800只A股, 300根日K线/只)。

## 实时信号监控 (NEW)

V21引擎 (`live_monitor_v21.py`) 使用这些检测函数+摆动SL策略, 每天扫描2000只A股:
```bash
cd ~/.hermes/scripts && python3 v11/live_monitor_v21.py --top 50
```
或通过cron: `smc-live-monitor` (周一到五9AM, 自动推送Top50信号)
信号输出: `~/.hermes/smc_signals/latest_signals.json`

### 信号序列模式 (V21验证)

信号的发生顺序显著影响胜率:
| 序列模式 | WR | 说明 |
|---------|-----|------|
| OB→FVG | 90% | OB确认→FVG入场 = 最佳 |
| Sweep→FVG | 85% | 流动性抓取后FVG = 强反转 |
| OOOOO | 17% | OB噪声, 跳过 |
| SOOSO | 0% | 双流扫, 跳过 |

详见 `smc-v11-system` skill → `references/signal-sequence-patterns.md`

## 概述

通过 Hubble 数据服务获取 K线数据，实时计算 15 种 SMC 信号，扫描多个标的物并筛选出符合 SMC 入场条件的品种。

## ⚠️ 重要发现 — API数据倒序

Hubble API 返回的 K线数据是**倒序的（最新在前）**。回测和检测函数需要先反转：
```python
raw = fetch_data(...)  # 最新在前
data = raw['data'] if isinstance(raw, dict) else raw
data.reverse()  # ← 必须反转！变成最早→最新
```

## 可用检测函数（15个）

| # | 函数 | 说明 | 实测信号频次(500根K线) |
|---|------|------|----------------------|
| 1 | `detect_fvg(klines)` | FVG (3根K线缺口) | ~46次/50根 |
| 2 | `detect_ifvg(klines)` | 反向FVG | ~197次触发 |
| 3 | `detect_liquidity_sweep(klines, lb=15)` | 流动性猎杀 (长影线突破) | ~2次/50根 |
| 4 | `detect_order_blocks(klines)` | 订单块 | ~146次 |
| 5 | `detect_market_structure(klines, lb=15)` | 市场结构 + CHOCH V1 + BOS | CHOCH仅17次 |
| 6 | `detect_choch_v2(klines, lb=15)` | CHOCH V2 (宽松: 趋势+反转法) | ~79次 (NEW) |
| 7 | `calculate_ote(klines)` | 斐波那契折扣/溢价区 | 辅助指标 |
| 8 | `detect_pd_array(klines)` | PD Array (OB+FVG+OTE优先级排序) | NEW |
| 9 | `detect_fvg_stack(klines)` | FVG堆叠 (多个重叠=强区域) | NEW |
| 10 | `detect_equal_hl(klines, tol=0.02)` | 双顶/双底 (流动性池) | NEW |
| 11 | `detect_volume_spread(klines)` | 量价背离/确认 | NEW |
| 12 | `detect_killzone()` | 美东交易时间段 | NEW |
| 13 | `find_pivots(klines, l=3, r=3)` | Pivot高/低点 | 辅助 |
| 14 | `score_signal(fvg, ob, sweep, struct, price)` | 综合评分(0-100) | 旧版 |
| 15 | `combo_score(fvg, sweep, ob, choch, ote, vol)` | 新版组合评分(含方向一致性) | NEW |

## 核心检测算法

### FVG

使用 `{o, h, l, c, v, t}` 格式，最新的K线在列表末尾。计算最近30根K线的平均范围，三根连续K线之间出现缺口（gap_top > gap_bottom 且 gap > avg_range * 0.15）即算有效。

强度判定：
- 强度1: 基础缺口
- 强度2: 实体 > 缺口宽度 × 2
- 强度3: 缺口宽度 > avg_range × 0.5

### Sweep

使用 `lookback=15` 前高/前低做参考，突破后收盘回到突破水平以内，影线比 ≥ 1.5 即触发。影线比 = 影线长度 / 实体长度。

### CHOCH V2

宽松版解决V1信号太少（V1只有17次/500K线）：
1. 前5根下跌 + 后3根突破前5H = Bullish CHOCH
2. 前5根上涨 + 后3根跌破前5L = Bearish CHOCH

## 完整信号组合评分

```python
def combo_score(fvg, sweep, ob, choch, ote, volume):
    """新版组合评分器"""
    score = 0; dirs = []
    if fvg: score += 25; dirs.append(fvg['direction'])
    if sweep: score += 20; dirs.append(sweep['direction'])
    if ob: score += 15; dirs.append(ob['direction'])
    if choch and choch.get('detected'): score += 20; dirs.append(choch['direction'])
    if ote and ote.get('in_discount'): score += 10
    if volume and volume.get('confirmation'): score += 10
    if dirs and all(d == dirs[0] for d in dirs): score += 10
    return min(100, score), dirs[-1] if dirs else None
```

## 市场 API 对应关系

| 市场 | K线端点 | 代码格式 | 代码示例 |
|------|---------|----------|----------|
| A股 | `GET /api/v2/cnstock/stocks` | `600519.SH` / `000001.SZ` | 带交易所后缀 |
| 美股 | `GET /api/v2/usstock/stocks` | `AAPL` / `TSLA` | 纯 Ticker |
| 加密货币 | `GET /api/v2/crypto/klines` | `BTCUSDT` | 需要 `exchange` |

## 扫描工作流

### Step 1: 确定范围
市场 → 标的列表 → 时间框架 → 信号类型

### Step 2: 获取数据
```bash
curl -sS "${AUTH[@]}" "$BASE/api/v2/cnstock/stocks?symbol=000001.SZ&interval=daily&limit=500"
```
**注意**: 数据顺序是倒序(最新在前)，必须 `.reverse()`！

### Step 3: 运行检测
```python
fvg = detect_fvg(klines)
swp = detect_liquidity_sweep(klines)
ob = detect_order_blocks(klines)
choch = detect_choch_v2(klines)
ote = calculate_ote(klines)
vol = detect_volume_spread(klines)
score, direction = combo_score(fvg[-1] if fvg else None, ..., ..., ...)
```

### Step 4: 筛选排序
| 评分 | 信号质量 | 行动 |
|------|----------|------|
| 80-100 | ⭐⭐⭐⭐⭐ | 优先关注 |
| 60-79 | ⭐⭐⭐⭐ | 可入场 |
| 40-59 | ⭐⭐⭐ | 等确认 |
| <40 | ⭐⭐ | 观察/跳过 |