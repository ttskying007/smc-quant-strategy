# SMC Trading System — 整体架构蓝图

## ═══════════════════════════════════════════
## 一、系统架构全景
## ═══════════════════════════════════════════

```
┌──────────────────────────────────────────────────────────┐
│              SMC 交易系统 (smc-trading-system)              │
│                    总路由 + 编排层                          │
└──────────────────────┬───────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  🛜 数据层     │ │  📐 检测层    │ │  🎯 应用层    │
│  Hubble API   │ │  SMC 指标     │ │  策略+信号    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ K线数据       │ │ FVG 检测     │ │ 🔍 信号扫描   │
│ 实时行情      │ │ Sweep 检测   │ │ 📊 策略回测   │
│ 技术指标API   │ │ OB 检测      │ │ ✅ 信号验证   │
│ OI/爆仓/费率  │ │ CHOCH 检测   │ │ 📈 可视化     │
│ CVD/买卖量    │ │ IFVG 检测    │ │ ⏰ Cron监控   │
│ 订单簿        │ │ MSB/BOS 检测  │ │ 🎯 信号组合   │
└──────────────┘ │ OTE 检测      │ └──────────────┘
                  │ PD Array 检测 │
                  │ Volume 检测   │
                  │ Killzone 检测 │
                  │ CVD Flow 检测 │
                  └──────────────┘
```

## ═══════════════════════════════════════════
## 二、数据层 (Data Layer)
## ═══════════════════════════════════════════

| 数据源 | Hubble API | 用途 | 市场 |
|--------|-----------|------|------|
| K线 (OHLCV) | `/v2/cnstock/stocks`, `/v2/usstock/stocks`, `/v2/crypto/klines` | 所有SMC检测 | cn/us/crypto |
| 实时行情 | `/v2/cnstock/securities` | 当前价格 + Killzone | cn |
| 技术指标(27种) | `/v2/indicators/batch` | RSI/MACD/BOLL/Volume | cn/hk/us |
| 持仓量(OI) | `/v2/crypto/open-interest/*` | 判断多空方向 | crypto |
| 爆仓 | `/v2/crypto/liquidation/*` | 流动性猎杀确认 | crypto |
| 资金费率 | `/v2/crypto/funding-rate/*` | 市场情绪 | crypto |
| 多空比 | `/v2/crypto/long-short/*` | 散户vs大户 | crypto |
| 订单簿 | `/v2/crypto/order-book/*` | 流动性池识别 | crypto |
| CVD/买卖 | `/v2/crypto/cvd/*`, `/v2/crypto/buy-sell/*` | Order Flow | crypto |
| 鲸鱼追踪 | `/v2/crypto/whale/*` | 大单信号 | crypto |
| ETF流入 | `/v2/crypto/etf/*` | 机构资金 | crypto |
| 恐惧贪婪 | `/v2/crypto/indicator/fear-greed` | 市场情绪 | crypto |

### 数据统一接口

```python
class MarketData:
    """统一的数据获取接口"""
    BASE = "http://43.167.234.49:3101"
    
    def klines(self, market, symbol, interval='daily', limit=500):
        """统一K线: 自动处理不同API的参数/格式/反转"""
    
    def indicators(self, market, symbol, ind_list, interval='1d', limit=200):
        """批量指标: 自动使用 batch 接口"""
    
    def realtime(self, market, symbol):
        """实时行情: 统一返回 {price, change, volume}"""
    
    def multi_timeframe(self, market, symbol, tfs=None):
        """多TF: 默认 [1w, 1d, 4h, 1h]"""
```

## ═══════════════════════════════════════════
## 三、检测层 (Detection Layer) — 所有SMC指标
## ═══════════════════════════════════════════

### 已实现的7个核心检测

| # | 检测器 | 状态 | 回测Sharpe(仅多) | 备注 |
|---|--------|------|-----------------|------|
| 1 | `detect_fvg()` | ✅ | **1.80** | 比亚迪上最佳单指标 |
| 2 | `detect_ifvg()` | ✅ | -0.31 | 低频, 需改进 |
| 3 | `detect_sweep()` | ✅ | -0.56 | 需配合FVG使用 |
| 4 | `detect_ob()` | ✅ | **0.60** | 中规中矩 |
| 5 | `detect_choch()` | ✅ | -15.17 | 🚨 CHOCH检测需重写! |
| 6 | `detect_msb()` | ✅ | - | 信号太少 |
| 7 | `calc_ote()` | ✅ | - | 辅助指标 |

### 需要新增/重写的8个检测

| # | 检测器 | 优先级 | 算法说明 | 数据依赖 |
|---|--------|--------|----------|----------|
| 8 | `detect_pd_array()` | 🔴 P0 | 整合OB+FVG+OTE=PD Array | K线 |
| 9 | `detect_killzone()` | 🔴 P0 | 时间窗口判断 | datetime |
| 10 | `detect_volume_spread()` | 🔴 P0 | 量价背离: 价格新高+成交量萎缩 | K线 |
| 11 | `detect_liquidity_void()` | 🟡 P1 | 价格快速穿越无OB/FVG区域 | K线 |
| 12 | `detect_fvg_stack()` | 🟡 P1 | 3+连续FVG重叠=强区域 | K线 |
| 13 | `detect_equal_hl()` | 🟡 P1 | 双顶/双底=流动性池 | K线 |
| 14 | `detect_order_flow()` | 🟡 P1 | CVD+买卖量=真假推动 | Hubble CVD |
| 15 | `detect_whale()` | 🟢 P2 | 鲸鱼大单->Smart Money | Hubble whale |

### 🔴 需要重写: CHOCH

```python
# CHOCH 检测算法 — V2 (宽松版)
def detect_choch_v2(klines, lookback=15):
    """
    问题(V1): pivot太少(需要3+2=5点), 比亚迪2年只找到17次
    
    V2方案: 
    1. 简单趋势: 前5根下跌/上涨 → 最后3根反转
    2. 宽松pivot: left=2, right=1 (只需2K确认)
    3. 多框架: 看前10根的HH/HL/LH/LL + 最后1根
    
    目标: 检测频次提升10x, 从17次→170次
    """
```

## ═══════════════════════════════════════════
## 四、信号组合层 (Signal Combination)
## ═══════════════════════════════════════════

### 参数敏感性测试 (比亚迪 FVG-Only)

```
参数         笔数  胜率   收益    Sharpe
SL1.0×ATR TP2R 135  35.6%  -18.8%  -0.53
SL1.5×ATR TP2R 135  43.0%  +90.9%   1.80  ← 最佳
SL2.0×ATR TP2R 135  37.8%   -5.6%  -0.09
SL1.5×ATR TP3R 135  29.6%  +22.8%   0.38
```

### 组合策略评分矩阵

```
            │ FVG │ Sweep │ OB | CHOCH │ MSB │ PDArray │
────────────┼─────┼───────┼────┼────────┼─────┼─────────┤
FVG+        │  ●  │       │    │        │     │         │ → Sharpe 1.80 (仅多)
FVG+Sweep   │  ●  │   ●   │    │        │     │         │ → Sharpe 1.88 (更好!)
FVG+OB      │  ●  │       │ ●  │        │     │         │ → Sharpe 0.60
FVG+Sweep+OB│  ●  │   ●   │ ●  │        │     │         │ → Sharpe ?
+SMC Full   │  ●  │   ●   │ ●  │   ●    │     │         │ → CHOCH待修
```

### 信号组合计分器 (Combo Scorer)

```python
def combo_score(fvg, sweep, ob, choch, msb, ote, volume):
    """组合评分: 每个信号 + 权重 + 方向一致性"""
    score = 0
    directions = [s['direction'] for s in [fvg, sweep, ob, choch] if s]
    
    if fvg: score += 25
    if sweep: score += 20
    if ob: score += 15
    if choch: score += 20
    if ote['in_discount']: score += 10
    if volume['divergence']: score += 10
    
    # 方向一致性加分
    if directions and all(d == directions[0] for d in directions):
        score += 10  # 所有信号方向一致
    
    return min(100, score), directions[-1] if directions else None
```

## ═══════════════════════════════════════════
## 五、可视化 (Visualization)
## ═══════════════════════════════════════════

### 终端文本可视化 (Phase 1 — CLI report)

```
SMC 图表 | 002594.SZ | 2026.04

  Price
  112 ┤ ═══════════════ [Premium]
  108 ┤ ══════╗══╔════ [OTE Discount~108.8]
  105 ┤═══[●]═╝══╝══   ← Current: 105.4
  102 ┤╔══╗            [Bearish FVG: 99-106.5]
  99  ┤╚══╝═══  [FVG]   [SSL Sweep here] ✅
  96  ┤═══════════════ [Discount bottom~97.5]
  
  Signal:  ★ Sweep ✅  ★ FVG ✅  ★ Bearish
  Score:  65/100 → B+ | Verdict: 观望
```

### HTML 可视化 (Phase 2 — Web UI)

- 使用 p5.js skill 生成交互式图表
- 烛台图 + 叠加SMC标记 (FVG矩形, Sweep箭头, OB线)
- 多TF切换 (1d/4h/1h/15min)
- 信号标记点击查看详情

### 数据接口

```python
def format_smc_chart(bars, signals, width=60, height=20):
    """生成SMC信号的ASCII烛台图"""
    
def generate_smc_html(bars, signals):
    """生成交互式HTML: p5.js + SMC标记"""
```

## ═══════════════════════════════════════════
## 六、Skill 架构重构
## ═══════════════════════════════════════════

### 当前 5 skills → 演化版

```
trading/
├── smc-core-concepts          # 🧠 理论 (不变)
├── smc-engine                # ⚡ 检测引擎 (NEW, 融合scanner+backtest)
│   ├── scripts/smc_detect.py        # 15+ 指标检测
│   ├── scripts/smc_combo.py         # 信号组合/评分
│   ├── scripts/smc_backtest.py      # 回测 (更新)
│   └── scripts/smc_chart.py         # ASCII可视化
├── smc-signal-verify          # ✅ 5维验证 (更新)
├── smc-trading-system         # 🤖 总路由 (更新)
```

### scripts/ 调用关系

```
smc_chart.py ────┐
smc_detect.py ───┤
smc_combo.py ────┤─── smc_trading_system.py (router)
smc_backtest.py ─┤
smc_verify.py ───┘
```

## ═══════════════════════════════════════════
## 七、未来演进 Roadmap
## ═══════════════════════════════════════════

| Phase | 内容 | 依赖 |
|-------|------|------|
| **P0** 当前 | ✅ 7个SMC指标 + 回测 + 验证 | Hubble API |
| **P1** 检测增强 | CHOCH V2 + PD Array + Volume + Killzone | 需要Hubble OI/CVD |
| **P2** 信号组合 | 组合评分 + Weight系统 + 多TF对齐 | P1完成后 |
| **P3** ASCII可视化 | 终端SMC图表 + 信号标记 | P2完成后 |
| **P4** HTML可视化 | p5.js交互图表 + Web UI | p5js skill |
| **P5** 自动盘检 | cronjob定时扫描 + A股/美股/加密 | P2完成后 |
| **P6** Telegram推送 | 实时信号推送到TG/微信 | P5完成后 |
| **P7** ML优化 | 用DSPy自动优化参数 + 信号权重 | P3完成后 |

## ═══════════════════════════════════════════
## 八、总结 — 比亚迪回测发现
## ═══════════════════════════════════════════

```
🏆 当前最佳: Sweep+FVG 仅多单 (Sharpe 1.88)
   
📊 独立指标效果排名:
   1. FVG (Sharpe 1.80) — 单指标冠军
   2. OB (Sharpe 0.60) — 能用
   3. Sweep (Sharpe -0.56) — 不能单独用
  
📌 关键发现:
   • 仅多 >>> 双向 (比亚迪趋势向上, 做空=反向)
   • CHOCH检测过于严格 → 需要V2重写
   • SL 1.5×ATR + TP 2R 是最佳参数
   • 信号组合的Sharpe 1.88 优于任何单指标
    
⚠️ 待修复:
   • CHOCH: pivot left/right=2 太少 → 需V2
   • IFVG: 方向判定需确认
   • OTE: 只有检查, 没有作为入场信号回测
```