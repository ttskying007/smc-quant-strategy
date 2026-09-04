# SMC 信号准确性诊断方法论 (V20→V22)

## 诊断流程

当用户报告"信号不准确 / 识别不对"时，**禁止表面调参**。执行:

1. 选取1-2只代表性股票(高波动+蓝筹)
2. 逐bar输出完整K线(OHLC) + 每个bar上的所有信号 + zone/penetration
3. 对照Pine标准逐信号验证: bar位置是否正确、是否重复、是否遗漏
4. 根因定位到代码行级别，而非调ATR倍数

## V20→V22 逐信号修复清单

### Swing检测
- **V21 bug**: 简化的静态窗口(`range(leg_size, n-leg_size)`)遗漏大量摆动点
- **修复(V22)**: 恢复V20 LuxAlgo leg()状态机 → `pivot_high > max(recent_highs)` 确认swing

### CHOCH/BOS
- **V20 bug**: `prev_close <= sh.price and close > sh.price` → 微小穿刺误触发, 同区域重复触发
- **V21 bug**: 穿透深度不够(ATR×0.3), 无未来swing检查
- **修复(V22)**: ATR×0.2穿透确认 + 同方向3bar去重 + `sh.bar_idx >= i`防未来swing

### OB (LuxAlgo)
- **V20 bug**: 从swing bar向break bar **向前**搜索 → OB偏移到远处的swing high
- **修复(V22)**: 从break bar **向后**搜索最近的反向K线(阳线→看涨OB, 阴线→看跌OB)
- **SMC2026 OB**: confidence=0.65, 仅渲染不交易; LuxAlgo OB confidence=0.75, 用于交易

### Sweep
- **V20 bug**: 同事件重复4-6次, 扫60bar外旧摆动点
- **V21 bug**: ATR×0.15+20bar窗口太严 → 0 sweeps
- **修复(V22)**: ATR×0.05 + 30bar窗口 + 3bar cooldown per direction + 取最深穿刺

### MSS
- **V20 bug**: 与CHOCH重复触发, 无区分度
- **修复(V22)**: ATR×0.5强穿透(比CHOCH严格2.5倍) + 8bar cooldown

### EQL/EQH
- **V20 bug**: 类型名为`EQL`/`EQH`而非`EQL_Low`/`EQL_High` → SIG_STYLE查找失败
- **V21 bug**: O(n²)全对检测, 无bar间距限制
- **修复(V22)**: 类型名修复 + 每pivot只取最近匹配对 + 至少5bar间距

### FVG
- **V21 bug**: 错误的K线比较(b1 vs b0而非b2 vs b0)
- **修复(V22)**: 恢复V20逻辑 `ohlcv[i]['l'] > ohlcv[i-2]['h']` (Bull FVG)

### 缺失信号实现(V22新增)
- **IFVG**: FVG被回补后反转
- **Breaker Block**: 失败OB变成反向支撑/阻力
- **Liquidity Void**: 连续K线跳空区域
- **Rejection Block**: 价格接近摆动点后强烈反转
- **OTE**: 最近摆动leg的61.8%-79%斐波那契回撤区
- **PO3**: 5bar窗口Accumulation→Manipulation→Distribution

## 验证方法

```python
# 逐bar诊断脚本示例
for i in range(n):
    sigs_here = [s for s in all_sigs if s.idx == i]
    sw_here = [sw for sw in swings if sw.bar_idx == i]
    # 输出: bar编号 + OHLC + swing标记 + 信号详情
```

对比Pine参考:
- SMC 2026: OB从swing点向后扫描, displacement_mult=1.3
- LuxAlgo: state machine BOS/CHOCH via crossover, parsed highs(ATR filter)
- Waves Ultimate: swings with right_bars=2+ATR filter

## V32A+ 系统架构发现：5套并行信号引擎 (2026-05-25)

经过全面代码审查发现系统存在 **5套并行不兼容的信号检测引擎**，这是信号不准的深层架构原因：

| 引擎 | 文件 | OB算法 | 摆动点 | 何处使用 |
|:----|:-----|:-------|:-------|:---------|
| **V11 classic** | `signals_v11.py` | 向前扫描每根K线，2+同向K线=OB，无位移过滤 | 对称窗口lookback | v7_module.py (旧前端K线) |
| **V22 leg** | `signals_v22.py` | LuxAlgo：从break向←搜5bar + SMC2026：从swing向←搜5bar | leg_size=20 | smc_unified.py旧import（死代码） |
| **V44 internal** | `v44_engine.py` detect_ob_v14() | 向前扫描+3bar impulse+实体门槛ATR*0.3，无位移过滤 | sw_lookback=8 | v44_engine.py（历史回测） |
| **Pine-like (V32A)** | `smc_core_pine_like.py` | 从结构事件向←搜（正确方向）→新增位移1.3x+body最小ATR*0.3 | Pine pivots left=right | K线前端+部分引擎信号 |
| **LuxAlgo V34** | `smc_core_luxalgo_v34.py` | min(parsedLows)在pivot与break之间=最强位移OB | lux_pivots | **V46.1引擎主力OB/结构** |

**关键发现**：V46.1引擎(v46_1_layered_3y.py)实际使用的是LuxAlgo V34的OB/结构检测+ Pine-like的FVG/EQL/OTE。两个引擎产生不同的OB信号集。

## 修复：Pine-like OB添加位移过滤器 (2026-05-25)

在`smc_core_pine_like.py:ob_signals_pine_like()`中实施了以下修复：

### 位移过滤器（Pine Script SMC2026标准）
```python
# 新增：扫描从结构事件向后，检查displacement > preceding_range * 1.3
preceding_range = b['h'] - b['l']
displacement = break_price - b['l']  # Bull OB
displacement_ratio = displacement / max(preceding_range, 0.001)
if displacement_ratio < displacement_mult:  # 默认1.3x
    continue  # 太弱的位移=不是真正的OB
```

### Body最小门槛（过滤doji噪声）
```python
body_pct = body / max(b['o'], 0.001) * 100
min_body_atr = profile.get('ob_min_body_atr', 0.3)
if body_pct < atr[j] * min_body_atr:
    continue
```

### Backscan范围扩展
- 旧：max_back=10（固定）
- 新：max_back=15（可配置，profile.ob_backscan）

### OB Mitigation修正
- 旧：要求`close < zone_low`（close跌破zone下沿才标记——漏报）
- 新：只有`low <= zone_high`（wick触到zone就算回补——正确）

## 修复：Sweep 3-bar cooldown (2026-05-25)

```python
# 新增：在emitted_dir中预填最近3根bar的sweep方向
for prev in out[-3:]:
    if prev.get('direction') == d:
        emitted_dir.add(d)
        break
```

## 前端信号类型名统一 (2026-05-25)

| 旧名 | 新名 | 说明 |
|:----|:-----|:-----|
| Sweep_Bull | Sweep_SSL | 向下清扫（多头止损） |
| Sweep_Bear | Sweep_BSL | 向上清扫（空头止损） |
| Sweep_CBL | 删除 | 死代码 |
| Sweep_SSL（重复） | 删除 | 保留一个定义 |

SIG_FAMILY和SIG_STYLE中的重复/过期条目已全部清理。`Sweep_SSL`和`Sweep_BSL`现在是标准命名。

## 前端死代码清理

`smc_unified.py`中`from v11.signals_v22 import detect_all_signals_v22 as detect_sigs`从未被调用（K线视图已改用smc_core_pine_like）。已移除。
