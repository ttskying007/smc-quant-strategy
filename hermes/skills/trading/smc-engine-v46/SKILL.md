---
name: smc-engine-v46
version: 6.0.0
description: >-
  SMC引擎进化: V46→V477(60min历史)→V8(SL/TP修复)→V9(多周期)→V10.2(SMC上下文,WR=84%)→V11(高级SMC+分批止盈+自适应,WR=95%)。
  关键发现: 60min入场WR=59.7%远低于日线99.4%, SMC上下文是WR第一决定因素(ctx_0=42%→ctx_4=92%), FVG/BOS/CHOCH在A股日线不可靠。
  当前主力: V11 Complete Engine (smc_opt_v11) + V10.2 Smart Money (smc_opt_v10).
user-invocable: true
metadata:
  category: trading
  emoji: 🔄
  tags: [smc, v46, v467, v468, v469, v470, v475, v476, v477, t1-enforcement, adaptive-sl, sl-optimization, structural-defect, system-diagnosis]
  supersedes: []
  requires: v11 signals_v11
  see-also:
    - smc-engine-v45 (V463/V464 — daily optimal)
    - smc-unified-frontend (V7/V8/V9/V10 K-line viewer)
    - references/v468-diagnosis-methodology.md
    - references/reversal-ob-correct-but-retest-entry-failed.md
    - references/poi-activation-decorative.md
    - references/v469-graded-trailing-revelations.md
    - references/v475-v476-sl-optimization-breakthrough.md
    - references/v477-t1-enforcement.md
    - references/v477-structural-defect-analysis.md
    - references/v9-mtf-architecture.md
    - references/v8-daily-backtest.md
---

# V46 SMC引擎 — 反转OB → 60min多bar持仓进化

> 原始多周期缓存的可恢复增量运行与验证方法见 `references/resumable-raw-mtf-cache.md`。当采用 cron 增量构建时，必须传递精确缺口符号清单、隔离已确认的永久无数据标的，并以独立进程组执行有界 provider 子任务；不得用 `resume-from + limit` 代替精确批次，否则一个空历史代码会令后续批次反复重审已完成标的。执行合同与验证清单见 `references/resumable-raw-cache-scheduler.md`。

## 版本演进

| 版本 | 数据 | WR | RR | P&L | avgHold | 核心改动 |
|:----|:---|:--:|:--:|:---:|:-------:|:---------|
| V465 | 60min | 81.9% | 16.49x | +4.52% | 2.6b | MIN_RR=8.0 + 硬BE锁hold>=2 |
| V466 | 日线 | 98.5% | 12.37x | +4.78% | 1.0b | MIN_RR=8.0 + 硬BE锁(日线最优) |
| V467 | 60min | 82.7% | 16.72x | +4.58% | 2.3b | 渐进BE + TP距离感知 |
| V468 | 60min | 68.6% | 6.77x | +2.54% | 2.4b | POI回调入场+真实价+宽松trailing |
| V469 | 60min | 58.3% | 5.66x | +2.42% | 2.9b | 序列方向匹配+分级trailing(G系数) |
| V470 | 60min | 67.8% | 6.90x | +3.36% | 3.1b | Pine-quality信号引擎+OB位移1.0x+入口过滤0.5+MIN_RR=6.0+紧BE |
| V475 | 60min | 83.0% | 19.79x | +4.59% | 1.5b | 强制adaptive SL(跳过OB边界SL) |
| V476 | 60min | 86.3% | 23.32x | +4.18% | 1.8b | 100% ATR-adaptive SL(跳过所有边界/摆动点SL) |
| **V477** | **60min** | **89.0%** | **24.59x** | **+4.48%** | **3.4b** | **T+1强制(跳过同日exit) + 100% adaptive SL (当前最优)** |

V468的RR和P&L看似更低但**是真实的**: V467的RR被0.5%虚假入场折扣高估了2-3倍, 且V467存储数据有32%价格损坏。
V469的WR看似更低但**交易量翻倍**(28st/64t vs 16st/35t), 序列方向匹配修复是关键改进。

## V468 — 4项根本修复

### A: Swing skip 8→3 (TP可达)
`find_swing_high_forward`: skip从8缩减到3, 摆动检测窗口从8→5, 提前返回阈值从5%→4%
- 效果: 摆动TP距离更近, 理论可达
- 仍无TP被命中(0/35), 但等待时间减少

### D: 虚假0.995入场折扣移除
```python
# 旧: zone_entry = max(lower, entry_price * 0.995)  # 0.5%系统性虚构折扣
# 新: if lower < close < upper: return lower; else: return close
```
- 当价格在FVG/OB区域内: 用区域下沿(真实支撑位)
- 当价格在区域外: 用收盘价(不制造折扣)
- SL距离不再被虚高, RR变真实

### C: POI回调入场 (首次实现ICT概念)
扫描确认信号后最多50根60min K线(6个交易日), 等待价格从外部折返到信号区域才入场。
- 77.8%的POI等待只有0-2b的延迟
- 真正实现了"价格回到兴趣点才入场"的ICT核心理念
- 代价: 交易数量降低(8%→4%的股票转化率)

### F+E: 60min参数规模修正
- TP近距检测: `extreme >= max(tp*0.90, entry*1.02)` (至少2%涨幅才收紧)
- SL最小值: 0.15%→0.30% (60min ATR 1.5-3.7%需要)
- SL边界范围: 0.08-1.5%→0.15-3.0%
- Trailing BE: 3%→8%, 锁利0.5%→2%

## V469 — 序列方向匹配 + 分级Trailing

### 序列方向匹配修复 (Core Bug Fix)

`analyze_sequence_v11()` 返回的 `best_sequence` 可能是空方向的序列(如 SHORT_BRONZE_D)但当前信号是多头OB。旧代码 `if 'SCOUT' not in seq_name: return None` 直接拒绝了所有非SCOUT序列——包括方向不匹配的。

**修复**: 检查 `seq_dir != sig_dir`, 如果方向不匹配则在 `sequences_found` 中找同方向的序列。

### 过滤器堆叠陷阱 (重要架构教训)

V469的前两轮迭代(v2/v3)添加了信号强度评分(calc_signal_strength)作为额外入场过滤器, 导致:
- 交易量从V468的35笔降到20笔
- WR从68.6%降到55.0%

**教训**: 信号强度评分应该**只用于分级trailing, 不做入场过滤**。V468的序列+共振+反转OB+POI过滤已经足够严格。

### G系数方向 (60min vs 日线差异)

| Grade | G | Trades | WR | RR | P&L |
|:-----|:-:|:-----:|:--:|:--:|:---:|
| A (G=1.5, 最松) | 1.5 | 23 | 52.2% | 5.41x | +2.04% |
| B (G=1.2) | 1.2 | 19 | 57.9% | 3.95x | +1.73% |
| C (G=1.0, 基线) | 1.0 | 22 | **72.7%** | **8.07x** | **+3.03%** |

**发现**: 60min数据上, 紧trailing(C级)表现最好。建议V470反转G系数:
- A级: G=0.8 (最紧 — 快速锁利)
- B级: G=1.0 (标准)
- C级: G=1.2 (最松 — 给单信号更多空间)

根因: 60min噪声更多, 松trailing让利润回吐。

## V469 200只结果

| 指标 | V468 (SCOUT-only) | V469 (all sequences) |
|:----|:-----:|:-----:|
| 股票数 | 16 | **28** |
| 交易数 | 35 | **64** |
| WR | 68.6% | 60.9% |
| RR | 6.77x | 5.89x |
| P&L | +2.54% | +2.29% |

V469找到几乎2倍的交易, WR/RR略有下降但可接受。序列方向匹配修复是关键——SCOUT-only过滤拒绝了大量有效交易。

## V469 Full 4552 Results

| 指标 | 值 |
|:----|:--:|
| 可交易/4552 | 759 (16.7%) |
| 总交易 | 1823 |
| WR | 58.3% |
| Avg RR | 5.66x |
| P&L/笔 | +2.42% |
| 总P&L | +4413.79% |
| Avg Hold | 2.9b |
| W:L ratio | 7.0x |
| PF | 10 |
| 低RR(<=1.5x)占比 | 41.7% |
| 高RR(>10x)占比 | 18.0% |

Grade Breakdown (全量):
| Grade | Trades | WR | RR | P&L |
|:-----|:-----:|:--:|:--:|:---:|
| A (G=1.5) | 635 | 56.7% | 5.25x | +2.25% |
| B (G=1.2) | 538 | 58.9% | 5.85x | +2.53% |
| C (G=1.0) | 650 | **59.4%** | **5.90x** | **+2.50%** |

**Grade inversion confirmed at scale**: Grade A (supposed strongest) has worst performance. The 8-bar cluster scoring is negatively correlated with actual forward performance. Stock-level grade is NOT computed (all 759 stocks show grade 'C').

## Grade Inversion Analysis

Three hypotheses for why cluster-density scoring is anti-correlated:

1. **Congestion not strength**: Dense signal clusters (FVG+OB+Sweep+CHOCH within 8 bars) indicate chop/indecision, not directional conviction.
2. **Retracement artifact**: Multi-signal clusters are more likely on retracement bars where price revisits old zones — precisely where breakouts fail.
3. **Look-ahead contamination**: The 8-bar window extends forward from the signal bar, potentially pulling in post-entry signals.

**Viable alternatives for V470**:
- Use signal-inherent quality (gap ratio, trend alignment, confidence) instead of cluster density
- Skip grading entirely, just use V468 trailing
- Reverse G coefficients: A=G=0.8 (tightest), B=1.0, C=1.2 (loosest)

## V468 200只结果

| 指标 | 值 |
|:----|:--:|
| 可交易/200 | 16 (8%) |
| 总交易 | 35 |
| WR | 68.6% |
| RR | 6.77x |
| PF | 20 |
| P&L/笔 | +2.54% |
| avgHold | 2.4b (max 8b) |
| W/L ratio | 9.0x |
| POI激活 | 77.8% |
| avgPOI等待 | 1.2b |
| 0 TP命中 | 全部trailing退出 |

Hold分布:
| hold | 数量 | WR | RR | P&L |
|:----|:---:|:--:|:--:|:---:|
| 1b | 16 | 81.2% | 7.94x | +2.68% |
| 2b | 8 | 62.5% | 8.70x | +3.15% |
| 3b | 3 | 33.3% | 1.87x | +1.63% |
| 4+ | 8 | 62.5% | 4.11x | +1.79% |

## V9 Multi-Timeframe (2026-05-15)

V9引擎整合日线+周线+60min多周期，5种信号类型全量回测。

| 指标 | 值 |
|------|-----|
| 交易 | 17,008 (1,399只股票) |
| 信号 | OB_Bull / FVG_Bull / CHOCH_Bull / BOS_Bull / Sweep_SSL |
| WR | 64.1% (真实, 非幻觉) |
| 入场 | 日线50.6% / 60min 49.4% |
| 数据 | 2024-12 ~ 2026-05 (18月) |

引擎: `v9_mtf_engine.py`, 结果: `smc_opt_v9/v9_mtf_full.json`

## V10.2 Smart Money (2026-05-15) — Current Production Engine

V10.2 is the **recommended production engine**. It uses SMC context filtering to achieve WR=84.2% with ONLY two validated signals.

### Architecture
```
detect_all_signals_v20 → SMC context check → LIQ/CHOCH→OB sequence
  → zone retest entry (daily, no 60min)
  → structural SL (OB lower + swing low, 3-8%) or ATR adaptive (0.5-2%)
  → smart trailing (+7% activation, delay 2 bars)
  → TP: forward swing_high within 20 bars, min 5%
```

### Key Results (4,905 stocks, 24 months)
| Metric | Value |
|:---|:---|
| Stocks with trades | 878 |
| Total trades | 1,839 |
| **WR** | **84.2%** |
| **avg PnL** | **+9.81%** |
| avg SL | 2.45% |
| avg Hold | 5.1 bars |
| **TP exits** | **63.5%** |

### Signal Performance
| Signal | Trades | WR | PnL |
|:---|:---|:---|:---|
| OB_Bull | 1,220 | 82.5% | +9.73% |
| Sweep_SSL | 619 | 87.4% | +9.97% |

### SMC Context Distribution
| Context | Trades | WR |
|:---|:---|:---|
| Sweep_SSL→OB (zone_OB_Bull) | 619 | 87.4% |
| LIQ Sweep→OB (Sweep_SSL_ctx) | 654 | 86.7% |
| BSL→OB (Sweep_BSL_ctx) | 469 | 78.7% |
| CHOCH→OB (CHOCH_Bull_ctx) | 97 | 73.2% |

### Engine file
`/root/.hermes/scripts/v11/v10_smart_money_engine.py`
Results: `/root/.hermes/smc_opt_v10/v10_smart_money.json`

---

## V11 Complete Engine (2026-05-15) — Advanced SMC + Batch TP + Per-Stock Adaptive

V11 extends V10.2 with: Breaker Block (advanced SMC), batch take-profit (TP1@2xATR + TP2@4xATR + trailing remainder), per-stock adaptive parameters (market state × volatility), and resonance scoring.

### Architecture
```
V10.2 core +:
  → Breaker Block detection (failed OB → reverse signal)
  → Batch exit: 50% @ TP1, 30% @ TP2, 20% trailing
  → Smart money cost line SL (OB lower boundary as anchor)
  → Market state detection: trending_up/down/ranging/volatile
  → Per-state adaptive params (SL multiplier, trail activation, trail distance)
  → Resonance scoring: daily + weekly alignment (score 1-2)
```

### Key Results (4,905 stocks)
| Metric | Value |
|:---|:---|
| Stocks | 2,477 |
| Trades | 5,459 |
| **WR** | **95.0%** |
| avg PnL | +3.90% |
| avg SL | 7.20% |
| **Batch TP1 hit** | **80.7%** |
| Batch TP2 hit | 27.5% |

### Signal Performance
| Signal | Trades | WR | PnL |
|:---|:---|:---|:---|
| OB_Bull | 3,162 | 99.0% | +4.14% |
| Sweep_SSL | 1,841 | 95.8% | +3.93% |
| **Breaker_Bull (NEW)** | 456 | 64.7% | +2.07% |

### Market State Performance (Per-Stock Adaptive)
| State | Trades | WR | PnL |
|:---|:---|:---|:---|
| trending_up | 645 | 93.8% | **+6.13%** |
| trending_down | 649 | 96.5% | +4.13% |
| ranging | 1,842 | 94.7% | +4.05% |
| volatile | 2,323 | 95.2% | +3.09% |

### Engine file
`/root/.hermes/scripts/v11/v11_complete_engine.py`
Results: `/root/.hermes/smc_opt_v11/v11_complete.json`

### Key Learnings
1. **60min entry LOWERS WR** (59.7% vs 99.4% daily) — do NOT use 60min for entry timing
2. **SMC context is the #1 WR factor** (ctx_0=42% → ctx_4=92%)
3. **FVG/BOS/CHOCH unreliable on A-stock daily** — only OB_Bull + Sweep_SSL work
4. **Batch TP at 80.7%** is the biggest single improvement over V10.2
5. **Breaker Block works** as supplementary signal (64.7% WR)
6. **Trending markets pay best** (PnL=+6.13% vs ranging=+4.05%)

> See: `references/smc-context-analysis.md` — AI engine findings

---

## 已知风险和Bug

### V467存储数据损坏
`v467_full_trades.json` 中~32%的入场价与OHLCV差值比值<0.1或>2.0。原因是缓存文件在两次扫描之间被刷新。**V467全量结果不可信。**

### TP目标从未命中 (V465/V466/V467/V468)
100%的交易通过trailing退出, 0%通过TP命中。swing_high/CHOCH TP目标在所有版本中都是虚构的(代码中计算但实际退出路径从未使用TP价格)。这不是Bug而是设计缺陷: trailing在价格到达TP之前就退出了。解决方案只能是更宽松的trailing。

### POI激活在V45/V465/V466/V467是装饰性的
`check_poi_activation()`返回值被解包到`_`, 入场时机由`entry_bar = max(sig_idx, confirmed_at)`控制。仅在V468中被正确使用。见 `references/poi-activation-decorative.md`。

### 60min与日线交易集不重叠
只有169/1757(9.6%)的股票同时在两个时间框架有交易。这是SMC信号结构依赖性的正常现象, 不是Bug。

### 低股票转化率 (V468)
只有8%的股票(16/200)通过POI回调+序列共振+反转OB综合过滤。这意味着V468是高质量但低覆盖的策略。

### 过滤器堆叠陷阱 (V469教训)
不要堆叠太多入场过滤器。信号强度评分应该只用于退出分级, 不做入场过滤。每个额外过滤器都线性减少交易量但非线性降低WR。见 `references/v469-graded-trailing-revelations.md`。

### G系数方向 (60min vs 日线)
60min数据的G系数需要反转: 紧trailing表现更好。不要默认假设"强信号=松trailing"。见 `references/v469-graded-trailing-revelations.md`。

### 测试股票选择
前20只字母序股票(000001.SZ-000029.SZ)是深市蓝筹, 几乎没有OB信号。应该用OB信号丰富的股票(688xxx, 002xxx, 300xxx)做测试。

## V46.1 Engine Architecture (2026-05-25 active pipeline)

```
load_sig(kl) → 混合信号引擎:
  res32 = smc_core_pine_like.detect_all_signals_pine_like(kl)  # FVG/EQL/OTE/LV/BPR
  res34 = smc_core_luxalgo_v34.detect_all_signals_lux_v34(kl)   # SWEEPS/OB/STRUCTURE
  sig['sweeps'] = merged(res32 + res34)      # 合并去重
  sig['swing_structure'] = res34              # LuxAlgo结构
  sig['internal_structure'] = res34           # LuxAlgo内部结构
  sig['structure'] = res34                    # LuxAlgo结构（含MSS）
  sig['obs'] = res34['signals']['obs']        # LuxAlgo OB

build_symbol(sym, kl, sig) → 构建交易setup
  → 使用混合信号源创建交易机会
  → v41.backtest_v34_setups(setups, kl) → 回测

classify_layer(a, t) → 三层质量门控:
  L1: 信号定义匹配 + TWO_BAR_REJECTION_HOLD入场确认
  L2: 流动性目标≥8% + 强/弱上下文 + 反转需CHOCH+MSS
  L3: 降仓: 目标5-8%降仓, continuation放宽MSS, OB overlap≥0.35
```

**关键发现**: V46.1不是单一信号源。LuxAlgo V34提供OB/结构，Pine-like提供FVG/EQL/OTE。前端K线渲染也使用这个混合模式。

## 5引擎并行架构陷阱 (2026-05-25发现)

系统存在5套互不兼容的信号引擎，导致回测结果、K线图表、选股列表三方不一致：

| 引擎 | OB算法 | 何处使用 |
|:----|:-------|:---------|
| signals_v11 | 向前扫描每K线，无位移过滤 | v7_module.py (旧前端) |
| signals_v22 | LuxAlgo+向←5bar+SMC2026+向←5bar | 死代码导入 |
| v44 detect_ob_v14 | 向前扫描+3bar impulse | v44历史引擎 |
| smc_core_pine_like v32a | 从结构向←扫描(正确)+位移1.3x | K线前端+FVG/EQL/OTE |
| smc_core_luxalgo_v34 v34 | min(parsedLows)在pivot与break间 | **V46.1引擎主力OB** |

## smc_core_pine_like OB修复 (2026-05-25)

1. **添加位移过滤器**: `displacement > preceding_range * 1.3` (Pine Script SMC2026标准)
2. **添加body最小**: `body_pct < atr[j] * 0.3` 跳过doji
3. **扩展backscan**: 10→15 bars, 添加`ob_displacement_mult`和`ob_min_body_atr`到profile
4. **修正mitigation**: wick touch (not close) 判断

## smc_core_pine_like Sweep修复 (2026-05-25)

添加3-bar cooldown per direction，防止同方向sweep连续触发。

## 修复验证（50只股票扫描）
- 100%股票有OB, avg 3.3/stock
- OB displacement: 1.8x~6.1x (全部≥1.3x)
- Sweep cooldown: 0违规
- OB:Struct = 1:1

## 架构

```
signals_v11 (14种全检测)
  → OB-only + reversal_ob过滤
  → 质量/成交量/趋势/序列/共振过滤
  → POI回调扫描 (V468: 扫描50根K线等折返)
  → 价格区间入场 (V468: 真实入场价)
  → calc_v38_trailing (V468: 8% BE/12%锁2%/20%锁5%)
  
V469分支:
  → 同V468入场流程
  → + calc_signal_strength (仅grade信息, 不硬过滤)
  → + 序列方向匹配 (方向不匹配时找对方向替代)
  → + 序列等级提升 (Gold/Silver→升Grade)
  → + calc_v38_trailing(..., signal_grade=grade) (分级G系数)
```

## 引擎文件

| 文件 | 说明 |
|------|------|
| /root/.hermes/scripts/v11/ai_analysis_engine.py | **AI分析引擎** — 信号质量/SMC上下文/入场时机分析 (基于V9 MTF数据) |
| /root/.hermes/scripts/v11/v9_mtf_engine.py | **V9 MTF** — 日线+周线+60min多周期, 5种信号, 18个月数据 |
| /root/.hermes/scripts/v11/v10_smart_money_engine.py | **V10.2 Smart Money** — 当前主力: SMC上下文过滤, OB+Sweep, WR=84%, TP=63% |
| /root/.hermes/scripts/v11/v11_complete_engine.py | **V11 Complete** — 高级SMC+分批止盈+自适应, Breaker Block, WR=95% |
| /root/.hermes/scripts/v11/v46_engine.py | V46引擎(原型) |
| /root/.hermes/scripts/v11/v467_engine.py | V467 — 60min标准版: 反转OB过滤+渐进BE+TP距离感知 |
| /root/.hermes/scripts/v11/v468_engine.py | V468 — POI回调入场+真实价(数据仅历史参考) |
| /root/.hermes/scripts/v11/v469_final.py | V469 — V468入场+分级trailing(数据仅历史参考) |
| /root/.hermes/scripts/v11/v470_engine.py | V470 — 使用signals_vPine.py (Pine-quality信号) |
| /root/.hermes/scripts/v11/v475_engine.py | V475 — 强制adaptive SL, 跳过OB边界SL |
| /root/.hermes/scripts/v11/v476_engine.py | V476 — 100% ATR-adaptive SL |
| /root/.hermes/scripts/v11/v477_engine.py | V477/V8 — T+1强制+SL 0.30%+trailing死区修复+TP接近0.75+500-bar支持 |
| /root/.hermes/scripts/v11/signals_v20.py | **V20.1信号引擎**: +Pinbar检测(Bull/Bear), 集成到detect_all_signals_v20 |
| /root/.hermes/scripts/v11/scan_LD_v6.py | V8扫描器: Pinbar检测4bug修复, Hammer+ShootingStar |
| /root/.hermes/scripts/v11/klines_60min.py | Tencent ifzq 60min下载器, count可设500 |
| /root/.hermes/scripts/v11/v468_20_test.py | V468 20x20测试 |
| /root/.hermes/scripts/v11/v468_full_scan.py | V468全量4552扫描 |
| /root/.hermes/scripts/v11/v469_final_test.py | V469 200只测试 |
| /root/.hermes/scripts/v11/v469_grid_test.py | V469网格搜索 |

## 结果目录

| 目录 | 内容 |
|------|------|
| /root/.hermes/smc_opt_v9/ | **V9 MTF全量**: 17,008笔 + analysis/ai_analysis_report.json |
| /root/.hermes/smc_opt_v10/ | **V10.2 Smart Money**: 898只/1,880笔, WR=84% (当前主力) |
| /root/.hermes/smc_opt_v11/ | **V11 Complete**: 2,477只/5,459笔, WR=95% |
| /root/.hermes/smc_opt_v467/ | V467全量结果(数据损坏,不可信) |
| /root/.hermes/smc_opt_v468/ | V468新鲜全量结果(历史参考) |
| /root/.hermes/smc_opt_v469/ | V469全量4552: 759只/1823笔 + grid_search (历史参考) |
| /root/.hermes/smc_opt_v470/ | V470全量: 180只/394笔 (历史参考) |
| /root/.hermes/smc_opt_v475/ | V475全量: 659只/1536笔, RR=19.79x (SL优化验证) |
| /root/.hermes/smc_opt_v476/ | V476全量: 894只/2124笔, RR=23.32x (100% adaptive SL) |
| /root/.hermes/smc_opt_v477/ | V477全量: 894只/2124笔, RR=24.59x, WR=89.0% (T+1强制, 当前最优) |

## 前端集成

| 路由 | 端口 | 版本 | 说明 |
|:----|:---:|:----|:-----|
| /v7 | 8890 | V467 | 统一K线+13信号+V467存储交易 |
| /v8 | 8890 | V468 | V468新鲜回测: POI入场+多bar持仓+真实价 |
| /v9 | 8890 | V469 | V469分级trailing: pin颜色=Grade(金/银/铜) |
| /v10 | 8890 | V470 | V470 Pine-quality信号+位移过滤+紧BE |

## 运行

```bash
cd /root/.hermes/scripts/v11

# === 当前主力引擎 ===
python3 v10_smart_money_engine.py   # V10.2 Smart Money — 日线SMC上下文入场 (4,905只, ~3min)
python3 v11_complete_engine.py      # V11 Complete — 高级SMC+分批止盈+自适应 (4,905只, ~5min)

# === 分析引擎 ===
python3 ai_analysis_engine.py       # AI分析引擎 — 信号质量/SMC上下文/入场时机分析 (基于V9数据)

# === V9 MTF (18个月多周期) ===
python3 v9_mtf_engine.py            # V9 Multi-Timeframe — 日线+周线+60min, 5种信号

# === 历史引擎 (参考) ===
python3 v477_engine.py              # V477/V8 — T+1强制+adaptive SL 全量4552 (~80s)
python3 v475_engine.py              # V475 — 强制adaptive SL 全量
python3 v476_engine.py              # V476 — 100% ATR-adaptive SL 全量
python3 v468_20_test.py             # V468 200只测试 (~30s)
python3 v469_final_test.py          # V469 200只测试 (~30s)

# === 前端 ===
# Kill old PID, clear pycache, restart:
#   kill $(lsof -i :8890 -t) 2>/dev/null; sleep 1
#   cd /root/.hermes/scripts && python3 smc_unified.py &
#   curl -s -o /dev/null -w "%{http_code}" http://localhost:8890/
```

### Daily Cron Workflow

The standard daily batch runs this sequence:

```
1. ai_analysis_engine.py   →  analyze signal quality / SMC context / entry timing
2. v10_smart_money_engine.py → refresh V10.2 backtest (current production)
3. Frontend restart        →  kill old PID, restart smc_unified.py on :8890
4. Top picks extraction    →  aggregate by symbol, rank by total PnL (min 2 trades)
5. Report: WR, PnL, signal breakdown, context gradient, top 10 picks
```

Key reporting thresholds:
- **WR >= 80%** → nominal. Below 80% → flag prominently.
- **FVG_Bull consistently <50% WR** in all analysis passes — permanently excluded from production.
- **BOS_Bull <42% WR** — not standalone, context-only.

### References

- `references/v468-diagnosis-methodology.md`: 8-bug systematic diagnosis methodology
- `references/v477-structural-defect-analysis.md`: V477 6 structural defects (SL/ATR, RR illusion, system identity, trailing over-operation, position sizing, TP fiction)
- `references/v477-extended-defects.md`: **追加7缺陷** (单信号类型, 无市场识别, 无分批止盈, 无成交量, 无时间止损, 无跳空保护, Pinbar检测4bug)
- `references/v8-case-study-300097.md`: **300097.SZ逐bar追踪** — SL死区/trailing机制/TP装饰性 的完整图解
- `references/v46-post-mortem.md`: Why V46 retest entry failed
- `references/poi-activation-decorative.md`: POI zone entry — decorative vs functional
- `references/v469-graded-trailing-revelations.md`: V469 core lessons
- `references/v475-v476-sl-optimization-breakthrough.md`: SL optimization methodology
- `references/v477-t1-enforcement.md`: A股T+1强制技术实现
- `references/smc-context-analysis.md`: **AI分析 — SMC上下文WR梯度(ctx_0=42%→ctx_4=92%), 60min vs 日线入场数据**
- `references/sltp-complete-design.md`: **完整SL/TP方案 — 成本线+ATR自适应+3级分批+动态跟踪+市场状态参数表**
- `references/v11-final-results.md`: **V11最终结果 — 5,459笔/WR=95%/TP1=80.7%/信号/市场状态/淘汰信号**
- `references/signal-validation-data.md`: **信号验证数据 — 哪些有效(OB/Sweep)/哪些淘汰(FVG/BOS/CHOCH/Mitigation)**

## V470 Parameter Tuning (2026-05-11)

### Changes Applied (A+B+C)

| # | Change | Old | New | Rationale |
|:-:|--------|:---:|:---:|:----------|
| A | displacement_mult (signals_vPine.py) | 1.3 | 1.0 | Lower detection threshold to increase OB coverage |
| B | Entry displacement filter (v470_engine.py) | — | >= 0.5 | Catch marginal OBs that pass detection-level 1.0x filter |
| C1 | MIN_PROJECTED_RR | 8.0 | 6.0 | Lower RR threshold to increase trade count |
| C2 | PROGRESSIVE_BE | [(5,0),(8,0.3),...] | [(3,0),(6,0.3),...] | Faster profit locking for 60min data |

### Premium/Discount Filter FAILED (removed same session)
Attempted: skip bull OB if entry_bar close > OB zone midpoint.
**Result**: 17/4552 stocks (vs 452/4552 baseline) — filter too aggressive for 60min.
**Root cause**: Price doesn't retrace deep enough into OB zones on 60min. Zone lower entry via `_calc_entry_price_at_zone` is already the optimal discount entry. Adding a close > midpoint check on entry_bar rejects valid trades where price briefly touched the OB zone.

### V10 Frontend Integration
- Pattern: V7 `build_v7(symbol, NAV, version='V470')` — same function, new version string
- Files: `smc_unified.py` (/v10 route + nav button), `v7_module.py` (DIRS + TRADE_MAPS + build_v7 V470 case)
- Port: 8890 + V10 🎯 nav button (cyan: #00e5ff)

### Engine File
`/root/.hermes/scripts/v11/v470_engine.py` (1112 lines)
- Uses `signals_vPine.py` for signal detection (Pine-quality swings + OB displacement + state machine structure)
- Reuses V468 proven entry/trailing logic unchanged
- Entry: POI retrace + zone entry + reversal OB + displacement filter + resonance/sequence
- TP: swing_high > CHOCH > none
- Trailing: V38.4 3-profile (loose/bear/tight) + progressive BE

### Key Pitfalls
1. **Don't stack entry filters**: Each additional filter linearly reduces trade count but non-linearly reduces WR. V470 has 5 filters (sequence + resonance + reversal OB + displacement >= 0.5 + trend alignment).
2. **Premium/discount is redundant**: `_calc_entry_price_at_zone` already gives the best entry (zone lower for bull). Close-based premium check is harmful in 60min.
3. **60min needs different tuning from daily**: Trailing thresholds 5-10x wider, BE/hold parameters more aggressive, MIN_PROJECTED_RR lower.
4. **V7 build_v7 pattern**: version='V470' parameter, on-demand backtest execution (not cached trades like V465-V467).

## V9 Multi-Timeframe Engine (2026-05-15)

### Architecture
- **Daily** signals: OB_Bull, FVG_Bull, CHOCH_Bull, BOS_Bull, Sweep_SSL via `signals_v20`
- **Weekly** trend filter: MA20, close > MA20 × 1.02 for bullish only
- **60min** precise entry: within daily signal zones, up to 12 bars retrace
- **SL**: entry-based ATR adaptive, 3-8% range (`atr * 2.0`)
- **TP**: forward swing_high within 30 bars, min 5%
- **Trailing**: +5% activation, trail distance = `ATR * 0.8`
- **T+1**: skip same-day exit

### Key Results (4905 stocks, 18 months)
| Signal | Trades | WR | avg PnL | Notes |
|--------|--------|-----|---------|-------|
| OB_Bull | 4,848 | 85.3% | +8.39% | Still the king |
| Sweep_SSL | 3,771 | 70.6% | +4.27% | Unexpectedly strong |
| FVG_Bull | 4,175 | 49.6% | +1.91% | Weak — high fill rate |
| CHOCH_Bull | 1,558 | 59.4% | +3.31% | Moderate |
| BOS_Bull | 2,656 | 41.9% | +0.53% | Not standalone |

Entry sources: daily 50.6% / 60min 49.4%. TP exits: 22.6%.

### Engine file
`/root/.hermes/scripts/v11/v9_mtf_engine.py`

### V8 SL/TP Fixes (applied to v477_engine.py)
1. **SL floor 0.15%→0.30%**: `atr * sl_mult * 0.3` → `atr * sl_mult * 0.8`
2. **Trailing dead zone fixed**: gain>=5% was `entry*0.985` (looser than initial SL) → now `entry*1.01` (lock 1%)
3. **TP proximity**: `extreme >= tp_price * 0.90` → `0.75` so TP can actually influence exits
4. **Load function**: now tries `_60min_500.json` first, falls back to `_60min_200.json`

### Pinbar Detection (V8 fix, signals_v20.py + scan_LD_v6.py)
4 bugs fixed:
1. Removed `c <= o` filter (valid hammers can have bearish body)
2. Close position: must be near HIGH (top 30% of range), not just above midpoint
3. Added Shooting Star (bearish pinbar) detection
4. Added `detect_pinbars_v20()` to `signals_v20.py`, integrated into `detect_all_signals_v20`

### Daily Full Backtest (V8)
`/root/.hermes/smc_opt_v8_daily/v8_daily_v2.json`: 1,596 stocks, 3,420 trades, WR=99.8%, SL=3-8%, TP=56.2%, 23 months data.

### Pitfalls
- **FVG_Bull daily unreliable** (49.6% WR) — daily FVG gaps fill too often. Only use on 60min or with strict unfilled-gap filter.
- **BOS_Bull not standalone** (41.9% WR) — use only as context/confirmation, not entry signal.
- **60min data limited to 6-7 months** — Tencent ifzq API max ~500 bars. Consider Hubble API for longer history.
- **No market regime adaptation** — same parameters in bull/bear/range markets. Next priority.

`signals_v12.py` is now available as an alternative to `signals_v11.py` for the V467+ engine pipeline. Key differences:

| Aspect | V11 | V12 |
|--------|:---:|:---:|
| OB detection | Per-candle forward scan (position offset 2-5 bars) | Swing-backward scan (correct ICT position) |
| OB body filter | >= 0.15% | >= 0.3% (constrained forward: >= 0.3%) |
| Swing detection | _find_swing_highs (lookback=10, no right confirm) | detect_swings_v12 (left=8, right=3, ATR inversion) |
| V12 unique features | — | Walrus bug fix, dojo impulse fix, constrained forward fallback |

## V475/V476 — SL优化突破 (2026-05-12)

### 根因发现

V467全量分析发现: **SL类型是RR的唯一决定因素**, 不是trailing也不是TP。

| SL类型 | V467占比 | SL中位 | RR中位 | 说明 |
|--------|---------|--------|-------|------|
| adaptive | 50.6% | 0.19% | 21.33x | ATR自适应, 极紧 |
| ob_lower | 39.3% | 0.56% | 8.41x | OB区域下沿, 2.9x宽 |
| swing_low | 10.1% | 0.68% | 7.19x | 摆动点, 3.6x宽 |

RR = PnL / SL — 分子(TP收益)不变时, SL越宽RR越低。

关键洞察: **所有SL类型在V467都有100%胜率**(trailing保本锁生效前从未触发SL)。这意味着收紧SL几乎无风险——交易要么在1根bar内到达TP方向, 要么被BE锁住。

### V475: 跳过OB边界SL

**修改**: `calc_v45_sl()` 中删除 `if 'OB' in sig_type: return lower, 'ob_lower'...` 检查, OB交易直接使用ATR自适应SL。

**全量4552结果**:
- 股票: 659 (vs V467 630, +4.6%)
- 交易: 1536 (vs V467 1472, +4.3%)
- WR: 83.0% (vs V467 82.7%, +0.3pp)
- RR: **19.79x** (vs V467 16.49x, **+20%**)
- P&L: +4.59% (vs V467 +4.58%)
- SL类型: adaptive 78.6% + swing_low 21.4%

### V476: 跳过所有非adaptive SL

**修改**: 在V475基础上, 同时删除摆动点SL检查(`swing_low/swing_high`), 100%使用ATR自适应SL。

**全量4552结果**:
- 股票: **894** (vs V467 630, **+42%**)
- 交易: **2124** (vs V467 1472, **+44%**)
- WR: **86.3%** (vs V467 82.7%, **+3.6pp**)
- RR: **23.32x** (vs V467 16.49x, **+41%**)
- P&L: +4.18% (vs V467 +4.52%)
- SL类型: adaptive 100%
- 1bar退出: 83.0% (vs V467 76.1%)
- 平均亏损: -0.15% | 平均盈利: +4.31% | W/L比率: 26.9x

### ATR自适应SL机制

```python
def calc_adaptive_sl(ohlcv, entry_idx, entry_price, params):
    atr = calc_atr_v45(ohlcv, entry_idx)  # 14期ATR
    sl_mult = params.get('sl_mult', 0.3)
    base_sl = max(0.15, min(1.5, atr * sl_mult * 0.3))
    # 结果: 低波股票 ~0.15-0.19%, 高波股票 ~0.3-0.5%
    return entry_price * (1 - base_sl/100)
```

SL中位0.19% = 60min bar的ATR的~10%。对于滤波后的高质量交易, 这个距离足以容忍正常bar波动, 但不会浪费RR在宽SL上。

### 性能汇总

| 指标 | V467 | V475 | V476 |
|------|------|------|------|
| 可交易股票 | 630 | 659 | **894 (+42%)** |
| 交易数 | 1472 | 1536 | **2124 (+44%)** |
| WR | 82.7% | 83.0% | **86.3%** |
| RR均值 | 16.49x | 19.79x | **23.32x (+41%)** |
| RR中位 | 12.84x | 18.11x | **22.03x (+72%)** |
| PF | 194 | 122 | **206** |
| 平均PnL | +4.52% | +4.43% | +4.18% |
| 1bar退出 | 76.1% | 77.4% | **83.0%** |
| SL 100% adaptive | No | 78.6% | **100%** |
| 平均盈利 | — | — | **+4.31%** |
| 平均亏损 | — | — | **-0.15%** |

### V477 — A股T+1强制 (2026-05-12)

A股T+1规则: 当日买入的股票当日无法卖出。V476有71.8%的交易是同日exit (entry和exit在同一交易日), 实际不可执行。

**修复方法**: 在 `calc_v38_trailing()` 函数中, 在每次exit检查时跳过同日的return:

```python
entry_date = ohlcv[entry_idx].get('date', '')[:10]  # '2026-02-24'
for j in range(entry_idx + 1, ...):
    bar_date = bar.get('date', '')[:10]
    is_same_day = (bar_date == entry_date and bar_date != '')
    
    # [更新extreme和gain — 始终执行]
    # [更新trailing SL阈值 — 始终执行]
    
    # T+1: 跳过同日exit (继续更新SL但不退出)
    if bar['l'] <= sl:
        if is_same_day:
            continue
        return j, max(sl, bar['l']), ...
```

关键: **同日K线上仍然更新extreme价格和trailing SL阈值**, 使下一交易日的SL已经收紧至合理水平。

**全量4552结果对比 (V476 vs V477):**

| 指标 | V476 (可当日卖) | V477 (T+1强制) | 变化 |
|------|:------------:|:-------------:|:----:|
| 股票 | 894 | 894 | = |
| 交易 | 2124 | 2124 | = |
| WR | 86.3% | **89.0%** | **+2.7pp** |
| RR均值 | 23.32x | **24.59x** | **+1.27x** |
| RR中位 | 22.04x | 22.77x | +0.73x |
| PnL | +4.18% | **+4.48%** | **+0.29%** |
| Hold中位 | 1.0bar | **3.0bars** | +2.0bars |
| Hold均值 | 1.8bars | 3.4bars | +1.6bars |
| 1bar退出 | 83.0% | **13.7%** | -69.3pp |
| SL 100% adaptive | 100% | 100% | = |
| 平均亏损 | -0.15% | -0.13% | 更小 |
| W/L比率 | 26.9x | **39.6x** | +47% |

**反直觉结论: T+1强制同时提升了WR和RR。** 强行多持有一天让趋势跑得更充分, 而0.13%的平均亏损显示隔夜风险可控。初期担心T+1会降低RR, 实际相反。

**未解决问题:**
- 同日exit trade占71.8%, 其中83%是hold=1bar。T+1强制后大部分hold=3bar(1.5天)。

### V8 修复 (2026-05-15) — SL/Trailing/TP 真实化 + Pinbar 检测

基于 V477 结构性缺陷的7步诊断，实施了以下修复：

### 1. Pinbar 检测 — 4个代码级Bug修复

**位置**: `signals_v20.py` + `scan_LD_v6.py`

| Bug | 旧代码 | 修复 |
|-----|--------|------|
| `c <= o` 跳过有效 Hammer | 阴线实体(close<open)直接跳过 | 改用 `abs(c-o)` 判断实体大小 |
| 收盘位置判断错误 | `c > (o+l)/2` (上半部) | `c > (h - range*0.3)` (顶部30%) |
| 缺 Shooting Star | 只有 Hammer (看涨) | 新增 Pinbar_Bear (看跌) |
| 无 PD Array 上下文 | 孤立的 pinbar 也接受 | 在注释中标注，由调用方验证 |

**集成**: `detect_pinbars_v20()` 已加入 `detect_all_signals_v20()`，V477 引擎可直接获取 pinbar 信号。

### 2. SL 下限 → 0.30% (was 0.15%)

```python
# V477: base_sl = max(0.15, min(1.5, atr * 0.3 * 0.3))  # atr * 0.09
# V8:   base_sl = max(0.30, min(2.0, atr * sl_mult * 0.8))  # atr * 0.25
```

效果: SL 从 0.15-0.56% → 0.30-1.2%，与 ATR 有结构关系 (~25-60% ATR)。

### 3. Trailing 死区修复

```python
# V477 (loose) gain>=5%: sl = max(sl, entry * 0.985)  # BUG: 0.985 比初始SL还松
# V8   (loose) gain>=5%: sl = max(sl, entry * 1.01)   # lock 1% 盈利
#              gain>=8%: sl = max(sl, extreme * 0.96)   # 4% trail
```

消除 24bar SL 完全静止的死区 (300097.SZ Trade 1 实测)。

### 4. TP 接近检测 → 0.75 (was 0.90)

```python
# V477: extreme >= tp_price * 0.90  # TP=40%时须涨36%才触发 — 不可达
# V8:   extreme >= tp_price * 0.75  # TP=40%时涨30%触发 → 有TP参与机会
```

### 5. 日线全量回测 V2 (SL=3-8%)

| 指标 | 值 |
|------|-----|
| 股票 | 1596/4905 (32.5%) |
| 交易 | 3420 |
| WR | 99.8% (6 笔亏损) |
| avg PnL | +9.00% |
| avg SL | 7.78% (日线合理) |
| avg RR | 1.2 (真实, 非幻觉) |
| avg Hold | 4.4 bars |
| TP exits | 56.2% (TP 在日线上可达!) |
| 数据周期 | 2024-06-26 ~ 2026-05-06 (23月) |

### 6. 60min 数据扩展

- Tencent ifzq API 支持 500bar (URL: `param=sh600519,m60,,500`)
- 已扩展 500 只, 日期覆盖 2025-11 ~ 2026-05 (6.5月)
- `load_ohlcv()` 改为优先尝试 `_60min_500.json`，回退到 `_60min_200.json`

### 修改的文件

| 文件 | 修改 |
|------|------|
| `v477_engine.py` | SL公式 + trailing阈值 + TP接近 + load_ohlcv(500bar) |
| `signals_v20.py` | +detect_pinbars_v20() + 集成到 detect_all_signals_v20 |
| `scan_LD_v6.py` | detect_pinbars() 4 Bug修复 |

## V477结构性缺陷 — 2026-05-12

**触发**: 用户Lei在看到WR=89%/RR=24.59x的"改善"数据后提出质疑: "止盈止损方法是有问题的, 位置是不合理的, 说明我们的计算方法, 设计逻辑, 方案有较大问题"。这是正确的系统架构级质疑。

**7层分析发现6个结构性缺陷** (完整文档见 `references/v477-structural-defect-analysis.md`):
[1-6 unchanged]

**2026-05-15追加7个缺陷** (见 `references/v477-extended-defects.md`):
7. 单信号类型(全量仅OB_Bull), 8. 无市场状态识别, 9. 无分批止盈, 10. 无成交量确认, 11. 无时间止损, 12. 无跳空保护, 13. Pinbar检测4个代码级bug

1. **SL位置设计错误**: SL=0.17% = ATR(0.86%)的20%, 和OB结构无关。更紧SL不产生更高WR(SL/ATR<10%时WR=73.6%, 20-50%时WR=93.8%)
2. **RR=24.59x是数学幻觉**: 真实风险调整回报 = PnL/ATR = 3.04x。
3. **系统身份矛盾**: 声称60min swing trading, 实际93%交易在1个交易日内退出。
4. **Trailing过度**: 100% trailing退出, 从未命中TP。T+1强制后WR反而提升, 证明trailing过早。
5. **仓位策略为零**: 所有交易等权, 信号质量分数无效(与WR/RR无相关)。
6. **TP目标虚构**: swing_high TP中位7.92%但从未作为退出触发。

**关键方法论更新**:

| 旧思维 | 新思维 |
|--------|--------|
| SL越紧RR越高 → SL好 | SL必须和信号结构有关系, SL/ATR不可<0.3 |
| RR = PnL/SL | 真实RR = PnL/ATR |
| WR=89%说明信号好 | WR高可能只是SL太紧碰不到 |
| 数据"改善" = 系统进步 | 必须验证系统身份是否一致 |

**未来任何引擎改动必须先过这7步检查** (见 `references/v477-structural-defect-analysis.md` 完整方法论):

1. SL/ATR比率检查 (需在0.3-1.0x范围)
2. PnL/ATR真实RR计算
3. 持仓时间分布验证系统身份
4. Bar-by-bar入场跟踪
5. RR成分解耦
6. 系统身份一致性验证
7. 信号质量-性能相关性检查

### 未解决问题

- **hold=2/3交易**: 185笔(8.7%)交易hold>=3, WR=44.6%, RR=1.09x。这些是被BE锁定的停滞交易, 拖累整体RR。可能的改进方向: 更早的BE退出(hold>=2), 或增加一个"价格必须在N bar内移动X%"条件。
- **V476单笔PnL略降**: +4.18% vs V467 +4.52%。原因是V476接受了更多边际交易(894只 vs 630只), 增加了小盈利交易的比例。
- **系统身份矛盾未解决**: 当前系统本质是60min scalping, 不是swing trading。如果目标是swing, 需要SL放大到ATR的0.5-1.0x且trailing需要大幅放宽, 接受WR降到50-65%。

### 关键教训 (用户偏好)
- **不要提供选项让用户选择**: 用户明确拒绝开放性问题("不要给我选择, 我没有相关数据参考")。必须自己测试所有方案, 交付数据驱动的结果。
- **测试驱动**: 每个假设都要运行全量扫描验证。200只验证后立刻全量4552。
- **数据优先**: 结论必须有全量数据支撑, 不能只看200只结果。

### 引擎文件

| 文件 | 说明 |
|------|------|
| `/root/.hermes/scripts/v11/v475_engine.py` | V475: 跳过OB边界SL, 强制adaptive SL (FVG保留信号边界) |
| `/root/.hermes/scripts/v11/v476_engine.py` | V476: 100% ATR-adaptive SL, 跳过所有边界/摆动点 |
| `/root/.hermes/scripts/v11/v477_engine.py` | V477: T+1强制 + 100% ATR-adaptive SL |

### 结果目录

| 目录 | 内容 |
|------|------|
| `/root/.hermes/smc_opt_v475/` | V475全量结果: 659只/1536笔, RR=19.79x |
| `/root/.hermes/smc_opt_v476/` | V476全量结果: 894只/2124笔, RR=23.32x |
| `/root/.hermes/smc_opt_v477/` | V477全量结果: 894只/2124笔, RR=24.59x, WR=89.0% |

### References

- `references/v475-v476-sl-optimization-breakthrough.md`: SL类型→RR关系详细分析, ATR自适应SL机制, 三步验证方法论
- `references/v477-t1-enforcement.md`: A股T+1强制技术实现 — 在trailing函数中跳过同日exit

**Direct comparison (200 stocks 60min, same exit logic)**:
| | V11 | V12 |
|---|---|---|
| Trades | 1429 | 1147 (-20%) |
| WR | 9.7% | 27.2% (+17.5pp) |
| P&L | +1371% | +1510% (+10%) |

V12 eliminates 20% of noise trades while improving WR 3x. Signal quality is genuinely better despite fewer total signals. The `backtest_compare.py` script (SWITCH toggle at line 13) can run either engine with identical entry/exit for side-by-side comparison.

*Note: V12 was only validated through the simplified backtest_compare.py, not through the full V467 pipeline (no sequence/resonance/reversal_OB/POI filters). Additional filtering would likely further improve its effective WR.*

- smc-engine-v45: V463/V464 daily optimal
- smc-unified-frontend: V7/V8 K-line viewer

## V8 — SL/TP架构修复 (2026-05-15)

### 触发背景

用户Lei要求全面分析SL/TP设计的完整性，并逐bar验证300097.SZ真实交易案例。分析发现V477的12个缺陷（6个已知+6个新发现），致命问题包括SL无结构意义、trailing死区、TP完全装饰性。

### V8三项修复 (均保持架构不变)

#### 修复1: SL宽度 — 赋予结构意义

```python
# V477 (旧): base_sl = max(0.15, min(1.5, atr * 0.3 * 0.3))  # atr*0.09
# V8   (新): base_sl = max(0.30, min(2.0, atr * 0.3 * 0.8))  # atr*0.24
# 效果: SL下限0.15%→0.30%, 约等于ATR的25-60%
# 原因: 旧SL=ATR的9% — 与K线结构零关系, 纯数学假象
```

#### 修复2: Trailing死区消除

V477的'loose' profile中gain>=5%档位有Bug: `sl = max(sl, entry*(1-1.5%))` 收紧到7.56但初始SL=7.66，`max(7.66, 7.56)=7.66` — 完全无效！导致24根bar的SL死区。

```python
# V8 新阈值 (loose profile):
gain>=18%  → SL = extreme * 0.92
gain>=12%  → SL = extreme * 0.94
gain>=8%   → SL = extreme * 0.96
gain>=5%   → SL = entry * 1.01  (lock 1%, was entry*0.985=bug)
gain>=3%   → SL = entry * 1.003 (tiny lock)
gain>=2%   → SL = entry (BE)
```

#### 修复3: TP接近检测阈值

`tp_price * 0.90` → `tp_price * 0.75`。旧值要求价格达到TP的90%（对swing_high TP=40%意味着要涨36%才触发），实际从未触发。

### V8 200只验证结果

```
         V477(SL=0.15%)     V8(SL=0.30%)
Stocks:  27/200             27/200
Trades:  65                 65
WR:      89.0%              100%
RR:      24.59x(虚假)       13.62x(真实)
PnL:     +4.48%             +5.79%(↑29%)
SL中位:  0.17%              0.30%
TP命中:  0%                 0%(仍0,参见下方)
```

### TP零命中的根本原因

所有版本(V465~V8) TP命中率均为0%。swing_high TP中位30-80%在60min scalping中不可达——trailing总是在TP之前触发退出。

**待解决方向**: 引入ATR-based TP (如TP1=ATR×2=~1.7%, TP2=ATR×4=~3.4%)替代远距离swing_high。

### Pinbar集成到V477信号引擎

V477使用 `signals_v20.py` (而非 `signals_v11.py`)。本session将Pinbar检测加入V20引擎:

- 新增 `detect_pinbars_v20()` 函数到 `signals_v20.py`
- 集成到 `detect_all_signals_v20()` 主检测函数中
- Pinbar作为 `confidence=0.55` 的低权重信号出现，不被单独交易（仅OB_Bull生成交易）
- 前端K线图上Pinbar会渲染为信号标记

### 真实案例: 300097.SZ 逐bar追踪

详见 `references/v8-case-study-300097.md`

关键发现:
- bars 117-139(24根): SL完全静止在7.66，gain从2%→9%无任何trailing收紧
- bar[140]: gain=12.37% → SL跳到8.20
- bar[141]: extreme=10.04(+30.73%) → SL跳到9.04, low=8.51触发退出
- TP=10.80(+40.63%)从未接近, 100% trailing退出

### 前后端状态

- SMC前端: http://localhost:8890/ (smc_unified.py, 信号+回测+监控)
- Hermes Web UI: http://localhost:18648/ (端口8648被oh-my-hermes CTO profiles占用)
