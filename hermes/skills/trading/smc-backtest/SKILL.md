---
name: smc-backtest
version: 36.0.0
description: >-
  SMC 回测系统 — V28清洁基线 + V34 POI/价格上下文系统。
  V28: FVG Bull-only + confirmed_at入场 + 摆动SL + 追踪止盈。
  V34: 三层时序(POI检测+价格行为上下文+链模式匹配)。
  全量4800验证: WR=77.1%, RR=7.24x, PF=35, 3291只可交易。
  POI回调场景 WR=87.0%(193笔)。
  NEW: 6种新增SMC信号(IFVG/EQL/OTE/MSS/PO3/BreakerBlock)
  NEW: SMC结构SL/TP引擎(swing/FVG/OB/sweep/ATR多级)
  NEW: 前端v2全面信号可视化
user-invocable: true
metadata:
  category: trading
  emoji: 📊
  tags: [smc, backtest, v28, v34, v35, po, price-context, signal-timing, structure-sl-tp, smc-signals]
  supersedes:
    - smc-v84-engine
    - smc-v10-system
  requires: v11 signals_v11, adaptive_params, signal_timing_sequencer_v34, structure_sl_tp
---

# SMC Backtest — V28/V34 回测系统 (2026-05-09)

## ⚠️ 历史数据不可信

**V23-V25 全部因前视偏差无效。** 详见 `smc-v11-system` 的已知陷阱#13。

核心bug: `entry_price = dec.get('entry_price')` 返回信号bar价而非当前模拟bar的close。
修正: `entry_price = ohlcv[i]['c']`。

## ⚠️ A股日线关键限制（必须理解）

**99.6%的交易在1根K线退出。这不是bug，是A股日线的本质属性。**

根因：
- SL=0.3% = 日均波幅(2-4%)的1/10
- 入场在bar i的收盘，bar i+1的gap决定一切
- V35(固定SL/TP=0.5-1.0%)实验WR=36.1% → 证实固定SL在日线不可行
- V35.1(延迟trailing到+2%)实验WR=37.4% → 延迟锁利让更多交易变亏

V28紧trailing(0.2% breakeven)把很多-0.3%的亏损变成0.2%的微赢，总P&L为正(+1.59%)。
"假赢"微利(40%在0-0.5%P&L)比真实-0.3%亏损好。

## 当前推荐引擎

| 版本 | 用途 | 架构 | 交易数 | WR | avgPnL | cumPnL |
|------|------|------|--------|-----|--------|--------|
| **V7.5** | **Trailing Stop + Pinbar纠正** | V7.3核心 + 严格Pinbar + OB过滤+15 | 1,309 | **88.4%** | **+9.11%** | **+11,931%** |
| V7.4 | Trailing Stop + 蜡烛形态 | V7.3核心 + 6种蜡烛形态 | 1,874 | 82.4% | +6.84% | +12,827% |
| V7.3 | Trailing Stop (延迟bar检查) | V7.0核心 + prev_trail_sl | 618 | 77.7% | +4.51% | +2,789% |
| V7.2 | 固定TP 5% | 同上但固定TP | 119 | 82.4% | +3.25% | +387% |
| V28 | 清洁基线 | 信号驱动+confirmed_at+SL0.3%+trailing | 3291只 | 77.1% | — | — |

### V7.3 — Trailing Stop 引擎 (2026-05-15)

**核心创新**: 固定TP% → 动态Trailing Stop，解决A股日线强势拉升中过早止盈。

机制:
- Hard SL: zone_low × 0.95 (保底)
- Trail激活: 价格 > entry × 1.03 (+3%)
- Trail退出: 从最高点回落2%
- 参数: MW=[3,5] SL=[0.95,0.96] ACT=[1.03] DIST=[0.02]

关键发现:
- 交易数暴增419% (119→618)，因为trailing不再因TP过近而丢弃信号
- avgPnL +15.7%，累计PnL +500%
- BOS_Bull→FVG_Bull 是最佳信号: 117笔 WR=81.2% avg=+7.25%
- 对比固定TP: OB_Bull +63.8% (5.00%→8.19%), BOS→FVG +75.5% (4.13%→7.25%)
- 案例000070: 固定TP +5% → trailing +63.5%

```bash
cd ~/.hermes/scripts && python3 v11/backtest_v63_full.py
# 结果: /root/.hermes/smc_opt_v21/detailed_trades_v63.json
```

### V37 — 流动性区域检测 (实验)

在V36核心上叠加流动性上下文:
- BSL/SSL流动性池聚类 (8.1次猎杀/股票)
- ATR自适应序列窗口 [3/4/6] 到 [5/8/12]
- 每周线多周期对齐

结论: A股日线gap特性(99.6%交易1-bar退出)使流动性猎杀在日线层面无法有效利用。
猎杀→FVG比率仅27%, 有/无猎杀WR无显著差异。

```bash
cd ~/.hermes/scripts && python3 v11/backtest_v37_core.py
cd ~/.hermes/scripts && python3 v11/scan_full_market_v37.py
```

### V28 — 清洁基线 (通用扫描)

```bash
# 200只快速测试
cd ~/.hermes/scripts && python3 v11/rolling_backtest_v28.py

# 全量4800扫描
cd ~/.hermes/scripts && python3 v11/scan_full_market_v28.py

# 结果摘要
cat ~/.hermes/smc_opt_v28/v28_full_merged.json | python3 -c \
"import json,sys;d=json.load(sys.stdin);s=d['summary'];print(f'WR={s[\"win_rate\"]}% RR={s[\"avg_rr\"]}x PF={s[\"profit_factor\"]}')"
```

## V34 POI/价格上下文系统详解

### 三层架构

```
Layer 1: POI检测
  FVG lower边界 = 自动POI(支撑位)
  追踪后续K线是否测试POI
  检测反弹(close>low && close>POI)

Layer 2: 价格行为上下文分类
  poi_pullback:    价格回测POI+反弹 → WR=87.0% (黄金)
  trend_continuation: 多周期趋势向上 → WR=77.9% (优秀)
  fresh:     FVG出现后无价格行为 → WR=66.8% (一般)

Layer 3: 信号链模式匹配 (V33延续)
  链码 → PATTERN_DB匹配 → bonus
```

### V34 200只验证关键数据

| 上下文 | 交易 | WR | P&L | 判断 |
|--------|------|----|-----|------|
| POI回调 | 193 | **87.0%** | +1.53% | 黄金 — 优先入场 |
| 趋势延续 | 298 | **77.9%** | +1.54% | 强烈推荐 |
| 新鲜(无回测) | 915 | 66.8% | +1.54% | 严格过滤 |

| 模式 | 代码 | 交易 | WR | P&L |
|------|------|------|----|-----|
| OB→FVG→CHOCH | OFC | 8 | **88%** | +3.25% |
| Sweep→FVG | SF | 18 | **78%** | +1.87% |
| 孤立FVG(新鲜) | — | 738 | 73% | +1.53% |
| FVG→FVG | FF | 384 | 73% | +1.19% |

## 全面SMC信号体系 (已实现14种)

### V11信号检测 (`v11/signals_v11.py`)

| 信号 | 类型 | 函数 | 可视化 | V34时序代码 |
|------|------|------|--------|------------|
| **FVG** | 公允价值缺口(3同色=质量分级) | `detect_fvg_v11` | 绿色矩形 | F |
| **Sweep** | 流动性猎杀(BSL/SSL标注) | `detect_sweep_v11` | 三角形 | S/s |
| **OB** | 订单块(ICT last opposite candle) | `detect_ob_v11` | 橙色矩形 | O/o |
| **CHOCH** | 结构转换(ICT位置约束) | `detect_choch_v11` | 菱形 | C/c |
| **BPR** | 平衡价格区间(反向FVG重叠) | `detect_bpr_v11` | 黄色菱形 | (neutral) |
| **LiquidityVoid** | 流动性真空(跳空缺口) | `detect_liquidity_void_v11` | — | L/l |
| **RejectionBlock** | 拒绝块 | `detect_rejection_block_v11` | — | R/r |
| **IFVG** | 隐含FVG(影线中点, 1.5%阈值) | `detect_ifvg_v11` | 紫色虚线矩形 | (V11.3新增) |
| **FVG_Mitigated** | 已填充FVG变反向(原Inversion改名) | `detect_mitigated_fvg_v11` | — | (V11.3新增) |
| **BreakerBlock** | 破坏块(FVG重叠=一击必中) | `detect_breaker_block_v11` | 蓝色虚线矩形 | (V11.3增强) |
| **BreakerBlock** | 破坏块(CHOCH后OB变反向) | `detect_breaker_block_v11` | 蓝色虚线矩形 | (V34新增) |
| **EQL** | 等高点/等低点 | `detect_eql_v11` | 红色/绿色水平虚线 | (V34新增) |
| **OTE** | 最优交易区域(61.8%斐波那契) | `detect_ote_v11` | 紫色圆点 | (V34新增) |
| **MSS** | 微观结构转换 | `detect_mss_v11` | 绿/橙色小三角 | (V34新增) |
| **PO3** | Power of 3 (ACC/MAN/DIS) | `detect_po3_v11` | 灰色/橙色/绿色矩形 | (V34新增) |

### 信号检测入口 (统一调用)

```python
from v11.signals_v11 import detect_all_signals_v11

params = calc_stock_params(ohlcv, symbol, phase, tf='daily')
result = detect_all_signals_v11(ohlcv, params=params, tf='daily')

# result 包含:
result['fvg']        # FVG信号列表
result['sweep']      # Sweep信号列表
result['ob']         # OB信号列表
result['choch']      # CHOCH信号列表
result['bpr']        # BPR信号列表
result['liquidity_void']  # LiquidityVoid信号
result['rejection_block'] # RejectionBlock信号
result['ifvg']       # IFVG信号 (新增)
result['breaker_block']   # BreakerBlock信号 (新增)
result['eql']        # EQL信号 (新增)
result['ote']        # OTE信号 (新增)
result['mss']        # MSS信号 (新增)
result['po3']        # PO3信号 (新增)
result['all']        # 全部信号合并排序
result['stats']      # 各类型统计
```

## SMC结构SL/TP引擎 (代替固定0.3%)

**文件: `v11/structure_sl_tp.py`**

### 5级SL优先级

```python
from v11.structure_sl_tp import calc_structure_sl_tp

result = calc_structure_sl_tp(ohlcv, entry_price, entry_idx, all_signals)

result['sl'] = {
    'price': 止损价格,
    'pct': 止损百分比(相对于入场价),
    'type': 'swing' | 'fvg' | 'ob' | 'sweep' | 'atr',
    'structure_price': 原始结构价格(未加缓冲),
}
result['tp'] = {
    'price': 止盈价格,
    'pct': 止盈百分比,
    'type': 'swing_high' | 'fvg_upper' | 'rr_target',
    'rr': 盈亏比,
}
```

### SL选择逻辑

| 优先级 | 类型 | 依据 | 特点 |
|--------|------|------|------|
| 1 | **swing** | 最近摆动低点下方+0.1% | 最可靠, 结构支撑 |
| 2 | **fvg** | FVG下边界下方+0.1% | 次可靠, 自然支撑 |
| 3 | **ob** | OB下边界下方+0.1% | 较可靠 |
| 4 | **sweep** | 扫荡低点下方+0.1% | 最紧但易触发 |
| 5 | **atr** | 基于ATR% (最后备选) | 仅当无结构可用 |

### TP选择逻辑

| 优先级 | 类型 | 依据 |
|--------|------|------|
| 1 | **swing_high** | 入场后的下一个摆动高点 |
| 2 | **fvg_upper** | 下一个FVG上边界 |
| 3 | **rr_target** | 2R固定目标(保底) |

## 前端查看器 v2 (全面SMC可视化)

**版本2: `smc_trade_viewer_v2.py` | 端口8896**

```bash
cd ~/.hermes/scripts && python3 smc_trade_viewer_v2.py
# 访问 http://localhost:8896
# V1保留: http://localhost:8897 (原始K线+出入点)
```

### ⚠️ CDN注意事项
- ECharts CDN(jsdelivr.net)在服务器上被墙
- 两个服务器都已改为本地serve `/echarts.min.js`
- 首次访问需从CDN下载至 `/tmp/echarts.min.js`
- 如果图表不显示, 检查network面板确认echarts.min.js加载成功

### 功能与v1区别

| 功能 | v1 (已废弃) | v2 (当前) |
|------|-------------|-----------|
| K线 | 红涨绿跌 | ✓ | ✓ |
| 信号可视化 | ❌ 无 | ✓ 14种全部 | 
| FVG矩形 | ❌ | ✓ 绿色半透明 |
| IFVG矩形 | ❌ | ✓ 紫色虚线 |
| OB矩形 | ❌ | ✓ 橙色半透明 |
| Sweep三角 | ❌ | ✓ BSL/SSL标记 |
| CHOCH菱形 | ❌ | ✓ BOS/CHOCH标记 |
| BPR标记 | ❌ | ✓ 黄色菱形 |
| EQL虚线 | ❌ | ✓ 红/绿水平线 |
| OTE标记 | ❌ | ✓ 紫色圆点 |
| PO3三阶段 | ❌ | ✓ ACC灰/MAN橙/DIS绿 |
| MSS标记 | ❌ | ✓ 小三角 |
| BreakerBlock | ❌ | ✓ 蓝色虚线矩形 |
| 结构SL | ❌ | ✓ 橙色虚线标明SL类型+百分比 |
| 结构TP | ❌ | ✓ 蓝色线标明TP类型+RR |
| 信号组合标签 | E1/E2/E3(混淆) | 1/2/3数字圆圈 |
| legend切换 | ❌ | ✓ 点击legend隐藏/显示信号层 |
| 信号统计 | ❌ | ✓ 全部信号类型计数 |
| 信号时序评分 | ❌ | ✓ V34 grade+chain+context |
| 交易明细表 | ✓ | ✓ (含时序评分列) |

### Legend交互
```
点击任意图例项 → 切换该信号层的可见性
FVG / IFVG / OB / BSL/SSL / BOS/CHOCH / BPR / EQL / OTE / BB / PO3 / MSS / SL/TP
```

## 核心引擎架构

```
          信号检测 (detect_all_signals_v11 → 14种信号)
                    │
                    ▼
          信号确认 (confirmed_at: FVG idx+1)
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    V28标准过滤           V34评分过滤
    Bull-only            POI检测(可选)
    趋势+量+周期          context分类
    Swing SL优先          chain pattern
    trailing exit         multi-TF resonance
                    │
                    ▼
         统一退出逻辑 (两种可选)
     ┌─────────────────────────────┐
     ▼                              ▼
  固定0.3% trailing           SMC结构SL/TP
  (V28默认)                   (structure_sl_tp.py)
  breakeven at +0.2%          swing/fvg/ob/sweep/atr
  profit trail at +0.5%       摆动高点TP/FVG upper TP
  secure trail at +1.5%       2R目标保底
```

## 信号时序评分 (V34/V33共享)

### 评分公式
```
score = 0.50(base) + pattern_bonus + resonance_bonus + phase_bonus
grade: A(>=0.75) / B(>=0.60) / C(>=0.50) / D / F
```

### PATTERN_DB (完整)

```
GOLD:
  'CF': CHOCH→FVG        bonus+0.35  (WR~85%)
  'FO': FVG→OB           bonus+0.30  (WR~82%)
  'SF': Sweep→FVG        bonus+0.30  (WR~78%,实测)

SILVER:
  'FF': FVG→FVG          bonus+0.20  (WR~72%,实测)
  'OFC': OB→FVG→CHOCH    bonus+0.45  (WR~88%,实测)
  'CSF': CHOCH→Sweep→FVG bonus+0.50  (WR~90%)
  'SFF': Sweep→FVG→FVG   bonus+0.40

BRONZE:
  'OO': OB→OB            bonus+0.05
  'SS': Sweep→Sweep      bonus-0.10 (跳过)
```

## 结果文件

| 版本 | 路径 | 状态 |
|------|------|------|
| V28 200只 | `~/.hermes/smc_opt_v28/backtest_v28.json` | 保留 |
| V28 全量 | `~/.hermes/smc_opt_v28/v28_full_merged.json` | 保留 |
| V34 200只 | `~/.hermes/smc_opt_v34/backtest_v34.json` | 保留 |
| V35 200只 | `~/.hermes/smc_opt_v35/backtest_v35.json` | 保留 |
| V35.1 200只 | `~/.hermes/smc_opt_v35/backtest_v351.json` | 保留 |
| 其他 (V12-V27, V29-V33) | 已清理 | 废弃/删除 |

### 清理记录 (2026-05-09)
- 删除: V12-V27, V29-V33 全部结果目录 + checkpoint目录
- 释放: 25GB 磁盘空间
- 保留: K线缓存(~/.hermes/kline_cache/), V28结果, V35实验, V34结果

## 版本对比总结

| 版本 | 架构变化 | WR | RR | PF | P&L |
|------|---------|-----|-----|-----|------|
| V28 | 清洁基线(最优) | 76.6% | 5.94x | 27 | +1.59% |
| V34 | POI+上下文 | 71.9% | 5.10x | 26 | +1.54% |
| V35 | 固定SL/TP(不宜) | 36.1% | 2.12x | 2 | +0.50% |
| **V36 (V11.2旧bug)** | 结构性SL/TP (旧NORMALIZE_MAP) | **84.3%** | **2.80x** | **22.6** | **+1.86%** |
| **V36 (V11.3修正)** | 结构性SL/TP + bug修复 + 窗口收紧 | **83.1%** | **2.95x** | **20.4** | **+1.97%** |
| V37 | 流动性区域(实验) | 38-55% | 可变 | 可变 | 不显著 |

注意: V36(V11.2)显示WR=84.3%但有4个bug(BPR误当FVG, IFVG方向错误, BPR双族, 死代码等)。
V36(V11.3)修正后WR=83.1%(-1.2%), 但交易数从5065降至2890(-43%), 过滤掉了大量低质量交易。
RR从2.80x提升至2.95x(+5%) — 每笔交易实际质量更高。

## V11.3 系统Bug修复与序列窗口收紧 (2026-05-09)

### 发现的4个Bug

| Bug | 模块 | 问题 | 修复 |
|-----|------|------|------|
| 1 | sequencer_v11 NORMALIZE_MAP | BPR方向=neutral但映射到FVG_Bull | 移除BPR; IFVG→IFVG_Bull/IFVG_Bear |
| 2 | sequencer_v11 NORMALIZE_MAP | 'IFVG':'FVG_Bull'忽略IFVG_Bear方向 | 按方向分别映射 |
| 3 | sequencer_v11 _same_family_v11 | BPR在FVG_Bull和FVG_Bear两个族(逻辑矛盾) | 移除BPR; 添加FVG_Mitigated |
| 4 | resonance_v11 make_entry_decision | sigs_before变量未定义(死代码) | 移除整个代码块 |

### 序列窗口收紧

| 序列等级 | 旧窗口 | 新窗口 | 效果 |
|---------|--------|--------|------|
| Gold (Sweep→CHOCH→FVG→OB) | [4,5,4] | [3,4,3] | 交易数-43%, WR仅-1.2% |
| Silver (CHOCH→FVG→OB) | [5,4] | [4,3] | 过滤低质量 |
| Silver (Sweep→CHOCH→FVG) | [4,5] | [3,4] | 过滤低质量 |
| Bronze (2-step) | [3] | [2] | 过滤低质量 |

### BreakerBlock入场信号增强

BreakerBlock_Bull/Bear已加入NORMALIZE_MAP(→OB_Bull/OB_Bear), 可参与序列匹配。
evaluate_signal_entry新增BreakerBlock类型:
- 仅has_fvg_overlap=True时允许入场
- SL回退到swing/adaptive
- 预期极佳但非常罕见

## 关键限制

1. **99.6%交易1根K线退出** — A股日线gap属性导致，不可改变
2. **Swing SL覆盖率14-50%** — 日线摆动点周期短
3. **V34 POI提升有限** — 日线POI回测场景仅35%的交易
4. **无60min/4H数据** — Hubble API key过期(401)
5. **V34评分过于宽松** — 1288笔中915笔(71%)为"新鲜"场景(WR=66.8%)

## 避免的陷阱

1. **不要信任dec.get('entry_price')**: 总是用 `ohlcv[i]['c']`
2. **不要追求WR>80%+RR>10x**: 那是前视偏差的假数字
3. **不要用固定SL/TP替代trailing**: V35实验证实日线固定SL不可行
4. **tight SL(0.3%)是日线最优**: 5个版本对比确认
5. **POI回调场景(87%WR)优先交易**: 不是所有FVG都该入场

## 核心文件

```
~/.hermes/scripts/v11/
├── rolling_backtest_v28.py        # V28引擎 (清洁基线)
├── rolling_backtest_v36.py        # V36引擎 (结构性SL/TP, 当前最优)
├── backtest_v37_core.py           # V37引擎 (流动性区域过滤实验)
├── scan_full_market_v37.py        # V37全量扫描
├── rolling_backtest_v34.py        # V34引擎 (POI+上下文)
├── rolling_backtest_v35.py        # V35引擎 (实验)
├── rolling_backtest_v351.py       # V35.1引擎 (实验)
├── signal_timing_sequencer_v11.py # V33评分引擎
├── signal_timing_sequencer_v34.py # V34评分引擎 (POI+上下文)
├── signals_v11.py                 # 信号检测(V11.3, 14种SMC信号) 2295行
├── adaptive_params.py             # 阶段自适应参数
├── structure_sl_tp.py             # SMC结构SL/TP引擎
├── liquidity_v37.py               # V37流动性区域检测+自适应窗口
├── sequencer_v11.py               # V11信号序列引擎 (715行)
├── resonance_v11.py               # V11四维共振引擎 (584行)
├── weekly_trend.py                # 周线趋势合成
~/.hermes/scripts/
├── smc_trade_viewer_v2.py         # 前端查看器v2 (port 8896)
├── smc_trade_viewer.py            # V1前端 (port 8897)
```
