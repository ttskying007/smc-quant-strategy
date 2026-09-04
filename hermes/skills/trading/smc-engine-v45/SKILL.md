---
name: smc-engine-v45
version: 5.0.0
description: >-
  V46.3 策略C — OB反转检测 + V45立即入场 + V38.4 trailing。
  OB-only: 反转OB过滤消除54%误报。200只: WR=98.0%, RR=10.05x, PF=1394。
  FVG门槛提高到0.70, OB门槛0.50+反转过滤。
  三线全量对比: A) RR5日线WR=98.1%/RR=11.03x B) RR7日线WR=97.9%/RR=11.65x C) 60min WR=71.2%/RR=11.34x(均持2.6bar)。
user-invocable: true
triggers:
  - "v45引擎"
  - "smc v45"
  - "v45 engine"
  - "v45交易"
  - "v45回测"
  - "策略C"
  - "反转OB"
  - "v465"
  - "60min"
metadata:
  category: trading
  emoji: "🏆"
  tags: [smc, v45, v463, strategy-c, ob-reversal, poi-activation, v38-trailing, bull-only, zone-entry]
  supersedes:
    - smc-engine-v44
    - smc-engine-v46
  requires: v11 signals_v11, v11 resonance_v11, v11 sequencer_v11
---

# V46.3 策略C — OB反转过滤 + V45立即入场

## 最终结果 (200只)

| 指标 | **V463 策略C** | V45 OB-only | V46 回踩 |
|------|:-------------:|:--------:|:-------:|
| WR | **98.0%** | 98.0% | 81.5% |
| RR | **10.05x** | 9.58x | 2.44x |
| PF | **1,394** | 753 | 30 |
| P&L/笔 | **+3.67%** | +3.81% | +1.86% |
| W/L比率 | **28.8x** | 15.4x | 6.8x |
| 交易数 | 247 | 946 | 1,429 |
| 可交易(200只) | 88 | 157 | 173 |
| 反转OB SL WR | **100%** | — | — |
| 扫描时间 | 5s | ~15s | 10s |

全量4800 FVG+OB基线 (完整文档留存):
  WR=100%: 2,721只(66.5%), avgWin=+3.864%, avgLoss=-0.257%
  W/L ratio=15.0x, 296s扫描, 4,092/4,800可交易
  SL: adaptive(74.6%), ob_lower(12.0%), fvg_lower(9.5%), swing_low(3.9%)
  入口: FVG(52.5%), OB(45.3%), Sweep->FVG(2.2%)
  POI激活: 99.1%
  PF>=100: 3,708只(90.6%)

## 策略C架构 — 当前最优

```
signals_v11 (14种全检测)
  ↓
OB-only过滤: 'OB' not in sig_type → skip
  ↓
is_reversal_ob() — 3项检查:
  1. 20-bar趋势 < +1% (否则=uptrend pullback, 跳过)
  2. 10bar内SweepDown (流动性猎杀)
  3. 15bar内CHOCH_Bull (结构转换)
  at_structure → 摆动点位置
  score≥1 或 trend<-1% → 反转OB
  trend>+1% → 非反转(除非sweep+choch豁免)
  ↓
质量门限: OB≥0.50, FVG≥0.70 (禁用FVG入口)
  ↓
V45标准过滤: 成交量>0.6x均值 / 趋势非逆2+ / 序列SCOUT / 共振≥0.50
  ↓
V38.4 3-profile trailing (loose/bear/tight)
  - 方向感知TP检测 (bull: ≥0.98, bear: ≤1.02)
  - ATR自适应BE/LK (低/中/高)
  ↓
SL: ob_lower(31.2%, WR=100%) + adaptive(58.3%, WR=97.2%) + swing_low(10.5%)
TP: swing_high(93.5%) + none(5%) + choch(1.5%)
```

## 反转OB检测方法 (is_reversal_ob)

```
Bull OB判定:
  20bar趋势 > +1% → 上升趋势pullback → 非反转 (除非有sweep+choch)
  20bar趋势 < -1% → 明显下降 → score+=1
  SweepDown within 10bar → score+=1
  CHOCH_Bull within 15bar前 → score+=1
  At swing structure → score+=1
  score≥1 → 反转OB

效果: OB_Bull误报从54%降到0% (趋势延续pullback全跳过)
      WR从V45 OB-only的98.0%提升到100%(反转OB SL)
```

## 迭代方法论 — SMC引擎优化流程

1. 诊断: 识别问题(OB误报/入场时机/退出逻辑)
2. 验证假设: 单只股票深度分析(000001.SZ的13个OB信号)
3. 设计修复: 单一改动+测试(不要同时改3个)
4. 200只验证: ~10s可完成, 每次改动必须跑
5. 全量4800: ~5min, 最终验收
6. 存档: 更新skill + 保存结果到smc_opt_vXX

关键: 每次只改一个变量, 否则无法确定哪个改动产生效果。
     V46踩坑: 同时改了3个(反转检测+回踩入场+新trailing) → 无法定位问题。

## 前端

| 路由 | 说明 | 端口 |
|------|------|------|
| `/v5` | V45 Dashboard (WR分布/SL/TP/入口图 + KPI卡片 + 搜索框) | 8890 |
| `/v5_stock?s=SYMBOL` | 个股K线+信号查看器(V2风格+V45实时回测) | 8890 |

个股查看器功能 (对标V2风格, 2026-05-10重写):
- V45实时回测(约50ms/只), 按需计算不必全量
- 14种信号全检测 + 编号圆圈标记 (1FVG, 2OB, 3SWP...)
- FVG/OB/BPR/OTE 信号区域填充(半透明色块)
- Sweep黄色虚线/CHOCH青色实线/MSS白色虚线
- 入场三角形(绿赢红输) + 出场菱形 + SL橙色虚线
- 组合信号标签 (入场时附近信号→组合序列FVG→OB)
- 13种信号过滤开关 (FVG/IFVG/OB/BPR/Sweep/CHOCH/MSS/OTE/EQL/PO3/LV/RB/BRK)
- 交易明细表格含信号组合列
- 搜索框+下拉快速切换股票
- 使用本地 echarts.min.js (/echarts.min.js 在8890服务器内)

## 文件

| 文件 | 说明 |
|------|------|
| /root/.hermes/scripts/v11/v45_engine.py | V45引擎(基线版本) |
| /root/.hermes/scripts/v11/v463_engine.py | **V46.3策略C — 当前最优** |
| /root/.hermes/scripts/v11/v45_200_test.py | 200只测试 |
| /root/.hermes/scripts/v11/v45_full_scan.py | 全量4800扫描 |
| /root/.hermes/scripts/v11/v463_200_test.py | 策略C 200只测试 |
| /root/.hermes/scripts/v11/v463_full_scan.py | 策略C 全量4800扫描 |
| /root/.hermes/scripts/v11/v46_engine.py | V46回踩入场引擎(实验) |
| /root/.hermes/smc_opt_v45/v45_full.json | V45全量结果 |
| /root/.hermes/smc_opt_v45/v45_ob_full.json | V45 OB-only全量结果 |
| /root/.hermes/smc_opt_v46/v46_full.json | V46全量结果 |
| /root/.hermes/smc_opt_v463/v463_full.json | 策略C全量结果 |
| /root/.hermes/scripts/v11/v464_engine_a.py | V464 RR5引擎 |
| /root/.hermes/scripts/v11/v464_engine_b.py | V464 RR7引擎 |
| /root/.hermes/scripts/v11/v465_engine.py | V465 60min引擎 |
| /root/.hermes/scripts/v11/v465_full_scan.py | V465 60min全量扫描 |
| /root/.hermes/smc_opt_v464_rr5/v464_rr5_full.json | RR5全量结果 |
| /root/.hermes/smc_opt_v464_rr7/v464_rr7_full.json | RR7全量结果 |
| /root/.hermes/smc_opt_v465/v465_full.json | 60min全量结果 |
| references/v45-signal-combo-test.md | 7种组合测试方法+结果 |
- references/strategy-c-ob-reversal.md | 策略C: OB反转过滤方案详解
- references/v465-60min-adaptation.md | V465 60min全量结果+适配技术

## 运行

```bash
cd /root/.hermes/scripts/v11 && python3 v45_200_test.py   # 200只~15s
cd /root/.hermes/scripts/v11 && python3 v45_full_scan.py   # 4800只~5min
cd /root/.hermes/scripts/v11 && python3 v45_smoke_v2.py    # 3只~3s
cd /root/.hermes/scripts/v11 && python3 v45_report.py      # 生成报告
```

## RR Optimization: MIN_PROJECTED_RR Filter

V463 achieved WR=98.0%, RR=10.05x. RR bottleneck analysis revealed 4 factors. The only effective optimizer was `MIN_PROJECTED_RR` — pre-filter trades where the swing_high target gives insufficient projected RR relative to SL distance.

4-threshold scan (200 stocks):

| Threshold | WR | RR | Trades | P&L |
|-----------|:--:|:--:|:-----:|:---:|
| None (V463) | 98.0% | 9.64x | 247 | +3.67% |
| 3.0x | 97.5% | **11.32x** | 202 | +3.97% |
| **5.0x** | **97.1%** | **12.39x** (+29%) | **174** | **+4.24%** |
| 7.0x | 96.6% | **13.47x** | 145 | +4.32% |
| 10.0x | 95.7% | **14.42x** | 115 | +4.38% |

**Key discovery**: Tight trailing (BE=0.2%) is actually BETTER for A-stock daily than loose trailing — immediate BE protection prevents gap losses. Relaxing trailing thresholds reduced both WR and RR.

**Fundamental constraint**: avg hold=1.0 bar, 84.5% trades exit within 3 bars. The max realistic RR for A-share daily is ~14-15x. Per-stock outliers reach 30-40x but are <5% of trades.

**Recommendation**: MIN_PROJECTED_RR=5.0 as the optimal balance. To break 20x, need 60-min data (multi-bar holds enable multi-level TP).

## Full 4800 Results: RR5 vs RR7 vs Baseline

Full 4800 scan comparison (2026-05-10):

| Metric | V463 (baseline) | V464 @RR5 | V464 @RR7 |
|--------|:-------------:|:---------:|:---------:|
| Tradable stocks | 1,837 | 1,503 (-18%) | 1,340 (-27%) |
| Total trades | 5,222 | 3,987 (-24%) | 3,454 (-34%) |
| **Win Rate** | **98.8%** | **98.1%** | **97.9%** |
| **Avg RR** | **9.64x** | **11.03x (+14%)** | **11.65x (+21%)** |
| Profit Factor | 1,254 | 955 | 950 |
| P&L per trade | +4.02% | +4.39% (+9%) | +4.53% (+13%) |
| avgWin | 4.076% | 4.479% | 4.636% |
| avgLoss | 0.262% | 0.248% | 0.229% |
| W/L ratio | 15.6x | 18.1x | 20.2x |
| TP hit RR | 9.51x | 13.43x (+41%) | 15.58x (+64%) |
| Trailing RR | 9.74x | 9.89x | 10.16x |
| TP hit count | 2,189 (42%) | 1,278 (32%) | 950 (28%) |
| Scan time | 130s | 127s | 128s |

**Key observations:**
- TP hit count drops from 42% to 28-32%, but TP hit RR surges 41-64%
- Trailing RR barely changes (9.74x→9.89x) — trailing performance is independent of RR filter
- avgLoss decreases with higher threshold (fewer bad trades)
- avgWin increases (higher quality targets selected)
- Scan time identical (127s vs 130s) — filter is O(1) per signal

**Tradeoff**: Every 1.0x increase in MIN_RR threshold eliminates ~10% of trades while adding ~5% to RR. The user should pick the threshold by acceptable trade count reduction.

## V465: 60-Minute Data Path — Full Results

### Mass Download
- Script: `/root/.hermes/scripts/v11/download_60min_all.py`
- 10-worker ThreadPoolExecutor parallel download
- 4,552/4,800 stocks cached (~3 min)
- Missing: 248 BJ stocks (Tencent API doesn't support), 1 SZ delisted (002450.SZ)
- Each stock has 200 bars of 60min data

### Engine Adaptation (V463 → V465)
- CACHE_DIR: `/root/.hermes/kline_cache_60min/`
- MIN_BARS: 120 → 60, MAX_HOLD: 60 → 80
- Swing detection: skip first 8 bars (vs 2) to avoid immediate exit
- Trailing thresholds: 5x wider (BE at 2% vs 0.2%, locks at 3.5-12% vs 0.7-3%)
- TP min pct: 3% → 2% (60min bars have smaller % moves)
- Bug fix: won logic in trailing was inverted (exit_price > entry_price for bull)

### Full 4,552 Stock Results

| Metric | Value |
|--------|:-----:|
| Tradable stocks | 1,252/4,552 (27.5%) |
| Total trades | 3,092 |
| WR | **71.2%** |
| Avg RR | **11.34x** |
| PF | 36 |
| P&L/trade | +3.36% |
| Avg hold | 2.6 bars (max 36) |
| Avg win | 4.85% |
| Avg loss | -0.33% |
| W/L ratio | 14.7x |

### Subset Analysis

| TP Type | Trades | WR | Avg RR |
|:-------:|:-----:|:--:|:------:|
| swing_high | 2,210 | **87.1%** | **14.19x** |
| none (no target) | 679 | 12.1% | 2.22x |
| choch | 203 | 97.0% | 10.78x |

### 3-Path Comparison (2026-05-10)

| Metric | A: RR5 Daily | B: RR7 Daily | C: 60min |
|:-------|:----------:|:----------:|:-------:|
| WR | **98.1%** | **97.9%** | 71.2% |
| RR | 11.03x | 11.65x | 11.34x |
| PF | 955 | 950 | 36 |
| P&L | +4.39% | +4.53% | +3.36% |
| Tradable | 1,503 | 1,340 | 1,252 |
| Trades | 3,987 | 3,454 | 3,092 |
| Avg hold | 1.0 bar | 1.0 bar | **2.6 bars** |
| Avg win | 4.48% | 4.64% | 4.85% |

### Insight
60min achieves multi-bar holds (2.6 vs 1.0) and swing_high subset hits 87.1% WR + 14.19x RR (best RR record). But overall WR (71.2%) is much lower than daily (98%). The 679 NoTP trades without viable swing targets drag down performance. Adding a MIN_PROJECTED_RR filter (like V464) could eliminate these and push WR to ~87%, RR to ~14x on 60min.

See `references/v465-60min-adaptation.md` for full details, iteration log, and future optimization ideas.

## 已知陷阱

1. **OB vs FVG 信号质量有结构性差异** — OB检测的"last opposite before impulse"天然比FVG(三根K线缺口)更可靠。200只测试: OB-only WR=98%, FVG-only WR=94.8%。全量4800: OB入口WR=97.4% vs FVG入口WR=89%。策略C只取OB入口, FVG质量门槛0.70 (已被事实禁用)。
2. **54%的OB_Bull在趋势延续处而非反转** — detect_ob_v11()只检查阴线+2阳线+成交量, 无趋势约束。使用is_reversal_ob()过滤后消除uptrend pullback误报。
3. **每次只改一个变量** — V46踩坑: 同时改3个(反转检测+回踩入场+新trailing)导致无法定位root cause。正确流程: 单改动→200只→分析→迭代。
4. **A股日线回踩=无效** — 99.6%交易1bar退出。V46的回踩入场方案RR从9.58x降到2.44x。立即入场+区间边界入场是A股日线最优。
5. **W/L比率比计算RR更准确** — V463计算RR=10.05x但W/L比率=28.8x。因为初始SL宽但实际退出用trailing紧锁。RR = |exit-price|/|entry-SL| 低估了真实表现。
6. **硬门限阻塞**: evaluate_v45_entry() 硬编码 `if not (is_fvg or is_ob): return None`。修改ENTRY_SIGNAL_TYPES不会自动让其他信号(Sweep/CHOCH/MSS/BPR)生效。所有组合测试(D/E/F/G)与C完全相同的原因在此。
7. **Bear方向P&L为负**(-2.41%/笔), 做多模式默认关闭。如需启用: ENABLE_BEAR=True
8. **POI激活是装饰性的**: `check_poi_activation()`的返回值(entry_price, sl_price, sl_type)被解包到`_`, 只用`poi_activated`布尔值做元数据记录。入场时机完全由`entry_bar = max(sig_idx, confirmed_at)`控制, 不等待价格回踩POI区域。见`smc-engine-v46`的`references/poi-activation-decorative.md`有修复代码。
9. **60min数据存储结果可能损坏**: V467 full scan结果中~32%的入场价与OHLCV不一致(比值<0.1或>2.0)。原因是缓存文件在两次扫描之间被刷新。重跑全量扫描前先确认缓存一致性。
10. **69%的60min持仓hold=1**: 5x宽松trailing阈值仍未解决A股60min单根K线即达到止盈的问题。需要更激进的调整(be_gain>=8%, lk_gain>=15%)或强制最小持仓周期。
