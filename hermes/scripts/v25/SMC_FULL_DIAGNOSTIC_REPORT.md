# SMC 系统全面诊断报告
## 2026-05-25 — 信号不准确性根因分析

---

## 一、系统架构混论：5套信号检测引擎并行运行

这是最根本的问题 — 整个系统中有**5套不同的信号检测实现**，互不兼容：

| 编号 | 文件 | 信号引擎 | 何处在用 |
|:---:|:---|:---------|:--------|
| 1 | `signals_v11.py` | detect_ob_v11() + detect_fvg_v11() + ... | v44_engine.py (主力引擎), v7_module.py (K线/前端) |
| 2 | `signals_v22.py` | detect_all_signals_v22() | **smc_unified.py** (主看板入口, line 16) |
| 3 | `v44_engine.py` | detect_ob_v14() (内置) + signals_v11其余信号 | v44全量回测 |
| 4 | `smc_core_pine_like.py` | 独立信号引擎 | v41_final_engine → v46_1_layered_3y (当前活动) |
| 5 | `signals_vPine.py` | Pine-quality信号引擎 (best) | **无人使用！** |

### 关键是：smc_unified.py / K线图表 用 signals_v22，而回测引擎用不同的套

这就导致：
- **K线图上标记的信号 ≠ 回测实际使用的信号**
- **选股列表基于不同信号集**
- **用户肉眼验证的信号在K线图上看到的 vs 回测输出的 不一致**

---

## 二、OB检测：与Pine Script的根本性差异（最严重问题）

### 2.1 signals_v11 detect_ob_v11() — 当前主力

```python
# signals_v11.py L754-755
for i in range(5, n - 3):           # ← 扫描每根K线！！！
    bar = ohlcv[i]
    ...
    if bar['c'] < bar['o']:          # 阴线
        impulse_bars = _is_strong_impulse(i+1, 'bull', min_bars=2)
        if impulse_bars >= 2:        # 只有2根阳线跟进 = OB
```

**根本问题**：扫描每根K线，只要后面有2根阳线就跟进去算OB。

- 🔴 **没有 displacement 过滤器**（Pine Script SMC2026: `displacement > preceding_range * 1.3`）
- 🔴 **没有反向蜡烛的实体最小门槛**，doji也能算OB
- 🔴 **不检查是否在摆动点附近**，趋势中间的错误K线也标记OB
- 🔴 **从swing向前扫描(forward)而不是从swing向后扫描(backward)** — 这是最严重的Pine差异

### 2.2 detect_ob_v14() — v44引擎内置

```python
# v44_engine.py L422
for i in range(8, n - 10):
    ...
    if body_pct < atr * 0.3:        # 有实体门槛，好一点
        continue
    ...
    impulse_bars = _is_strong_impulse_v14(i + 1, 'bull', min_bars=3)  # ← 要求3根
```

虽然有实体门槛，但**仍然是扫描每根K线**，不是从摆动点向后扫描。
- 🔴 **依然没有 displacement 过滤器**
- 🔴 **requires 3-bar impulse 太严格**，会漏掉许多真正的OB
- 🔴 **仍然是从前向后扫描**，不是Pine Script的方式

### 2.3 Pine Script 的正确方式

Pine Script SMC 2026、LuxAlgo的OB检测：

```
1. 等待 swing_point (摆动点) 形成
2. 从摆动点向回扫描
3. 找到最近的同方向K线（Bull OB = 阴线，Bear OB = 阳线）
4. 计算 displacement = OB极值到突破价位的距离
5. 如果 displacement > preceding_candle_range * 1.3 → 确认OB
6. 如果 displacement不足 → 继续往回找
```

**关键差异**：
- **我们的代码**：扫描每根K线，有阳线跟随就算
- **Pine Script**：从结构点往回找，检查位移是否足够大

### 2.4 signals_vPine.py 存在但没人用

`signals_vPine.py` 中的 `detect_ob_vPine()` 有正确的从swing向后扫描算法和displacement过滤，但**没有任何引擎或前端使用它**。

---

## 三、摆动点检测差异

| 实现 | 算法 | Right Confirmation | ATR过滤 |
|:-----|:-----|:------------------:|:--------:|
| signals_v11 _find_swing_highs | lookback对称窗口 | ❌ 无 | ❌ 无 |
| signals_v22 detect_leg_swings | leg_size=20 | ❌ 无 | ❌ 无 |
| signals_vPine detect_swings_vPine | left=10, right=10 | ✅ 有 | ✅ 有 |
| Pine Script pivothigh | left=N, right=N | ✅ 有 | ✅ 有 |

**signals_v11 的摆动点检测问题**：
```python
def _find_swing_highs(ohlcv, lookback):
    for i in range(lookback, n - lookback):
        if all(ohlcv[i]['h'] >= ohlcv[j]['h'] 
               for j in range(i - lookback, i + lookback + 1)):
```
- 使用对称窗口（左右一样长），但Pine的 pivot/pivotlow 要求 `left ≠ right` 来确认
- 没有right confirmation：价格在后续K线突破摆动点后，摆动点不失效
- 没有ATR幅度过滤，很小的波动也会算摆动点
- 导致OB定位在错误的结构点上

---

## 四、CHOCH/BOS 检测差异

### 4.1 signals_v22 detect_choch_bos()
```python
# 使用swing点遍历，需要ATR*0.2穿透+prev_close<=swing_price
```
优点：基于摆动点检测，有穿透过滤
缺点：
- `fired_swings` 去重导致CHOCH只触发一次，后续同方向突破全部忽略
- 同方向3bar去重太激进，会错过真正的趋势延续

### 4.2 signals_v11 detect_choch_v11()
需要去找具体实现，但从框架看使用了摆动点+价格突破逻辑
- 但它的摆动点本身就有问题（没有right confirmation）

---

## 五、前端信号渲染不同步

### 5.1 信号类型命名不一致

| 信号 | signals_v11 | signals_v22 | SIG_STYLE (v7_module) |
|:-----|:-----------|:-----------|:--------------------|
| 流动性清扫(空头) | SweepUp | Sweep_BSL | SweepUp ✅ |
| 流动性清扫(多头) | SweepDown | Sweep_SSL | SweepDown ✅ |
| 订单块(多) | OB_Bull | OB_Bull | OB_Bull ✅ |
| 结构转换 | CHOCH_Bull/Bear | CHOCH_Bull/Bear | ✅ |

信号命名基本一致，但smc_unified.py（主看板）用signals_v22，而v7_module.py（独立K线视图）用signals_v11。如果这两个视图调用不同引擎，信号就会不同。

### 5.2 信号颜色/样式 vs 交易标记分离

`v7_module.py` 中的信号标记（markPoint/markArea/markLine）从 `SIG_STYLE` 读取，但交易标记（entry/exit/SL/TP）从 `TRADE_MAPS` 读取。这两个数据源的信号可能来自不同版本。

---

## 六、入场逻辑问题

### 6.1 回踩入场 (detect_retest_entries)
```python
# v44_engine.py L573
# tolerance_pct=0.3 — 价格进入zone的容忍度
```
- 0.3%的容忍度可能太紧，尤其对低波动A股
- 没有gap保护：如果价格跳空越过zone，会完全错过
- 回踩确认方式 (touch/engulf/pinbar) 可能不够严格

### 6.2 入场价计算
- 部分引擎用zone_low/zone_high
- 部分用收盘价
- 部分用next_open
- 不一致导致信号→入场价映射错误

---

## 七、出场逻辑问题（低RR根因）

### 7.1 SL 设计错误（V477已知缺陷）
```python
# v44_engine.py L247-252
sl_pct = max(0.15, min(0.35, avg_atr * 0.3))
```
- SL = ATR*0.3% = 对低波动股票仅0.15%
- **SL没有结构意义**：不是基于OB下沿、摆动低点等
- RR = PnL/SL = PnL/0.15 → **数学幻觉**
- 真实RR = PnL/ATR

### 7.2 TP 装饰性（V477已知缺陷）
- swing_high TP目标中位5-8%
- 但所有退出都由trailing触发，TP从未作为退出条件
- 即使降低了TP接近检测阈值(0.90→0.75)，TP命中率仍然为0%

### 7.3 Trailing 过早
```python
# v44_engine.py TRAILING_PROFILES L76-93
# thresholds = [(6.0, 3.0), (3.0, 1.5), (1.5, 0.3), ...]
```
- 在盈利0.3%时就开始收紧trailing到0.3%
- 对于60min的scalping可能合适，但对日线swing trading过早
- 导致100%的退出由trailing触发

---

## 八、回测与选股不同步

### 8.1 回测输出
- v46_1输出：`v46_1_trades.json`（交易详情）
- v44输出：`v44_full.json`
- 两个版本使用不同的信号引擎和参数

### 8.2 选股列表
- smc_unified.py 读取 `v46_1_picks.json`
- 但选股过滤逻辑可能和回测不一致
- 选股评分基于的信号集 vs 交易信号集可能不同

### 8.3 当前版本混乱
smc_unified.py 检测V46_1存在就启用V46_1，否则fallback到V44→V24→V41→V40...→V27
这意味着用户看到的版本取决于哪个目录有数据，而不是明确的配置。

---

## 九、低 RR 根因分析

### 立即原因
1. **SL太紧（ATR*0.3%）** → 分母太小 → RR虚高（24.59x是幻觉）
2. **真实RR = PnL/ATR** 才是真实的（约3-4x）
3. **小盈利交易占比过高**：83%的盈利在1-3%之间
4. **无分批止盈**：要么all-in trailing，要么all-in SL

### 深层原因
1. **信号不准导致入场点不对** → 入场后无法快速脱离成本区
2. **OB位置不正确**（不是从摆动点检测）→ 支撑/阻力位不准
3. **CHOCH/BOS在错误位置** → 趋势判断错误
4. **多个信号引擎混用** → 无法系统性地优化单一信号集

---

## 十、修复路线图

### 阶段1：统一信号引擎（优先级最高）
1. 将 `signals_vPine.py` 作为唯一信号引擎
2. 修改 `smc_unified.py` line 16: `from v11.signals_vPine import detect_all_signals_vPine as detect_sigs`
3. 修改 `v7_module.py`: 同样切换到vPine
4. 修改 `v44_engine.py`: 移除内建 detect_ob_v14，统一用vPine

### 阶段2：修复OB检测（对标Pine Script）
1. 从swing点向后扫描（不是forward扫描所有K线）
2. 添加 displacement_mult 过滤器（Pine: 1.3x）
3. 添加实体最小门槛（body_pct > ATR*0.3）
4. Pine Swing检测：left=10, right=10 + ATR过滤

### 阶段3：修复CHOCH/BOS
1. 状态机方式（Pine Script LuxAlgo风格）
2. 不预设方向，用swing_trend跟踪
3. ATR穿透确认（>= ATR*0.2）

### 阶段4：统一信号命名
- SweepDown/SweepUp → 统一用 Sweep_SSL/Sweep_BSL
- 确保SIG_STYLE覆盖所有信号类型

### 阶段5：修复入场/出场
1. SL基于结构（OB下沿/摆动低点），不只用ATR
2. 分批止盈（30% TP1 + 30% TP2 + 40% trailing）
3. Trailing放松到5-10%才激活

### 阶段6：全量回测验证
1. 用统一引擎重新跑全量4905只
2. 逐笔对比vPine vs v22的信号差异
3. 验证K线图表信号与实际交易信号一致

现在开始执行修复。
