# 5套并行信号引擎 — 系统架构根因

## 发现时间
2026-05-25 全面代码审查

## 问题
系统有5套互不兼容的信号检测引擎，K线图表信号 ≠ 回测引擎使用的信号 ≠ 选股列表信号。

## 引擎清单

| # | 引擎 | 文件 | OB算法 | 摆动点 | 何处使用 |
|:-:|:----|:-----|:-------|:-------|:---------|
| 1 | V11 classic | `scripts/v11/signals_v11.py` | 向前扫描每K线，2+同向K线=OB，无位移过滤 | 对称窗口lookback | v7_module.py旧前端K线 |
| 2 | V22 leg | `scripts/v11/signals_v22.py` | LuxAlgo从break←5bar + SMC2026从swing←5bar | leg_size=20 | smc_unified.py旧import（死代码） |
| 3 | V44 internal | `scripts/v11/v44_engine.py` detect_ob_v14() | 向前扫描+3bar impulse+body ATR*0.3，无位移 | sw_lookback=8 | v44_engine.py历史回测 |
| 4 | Pine-like V32A | `scripts/v25/smc_core_pine_like.py` | 从结构事件←扫描（正确方向）+位移1.3x+body ATR*0.3 | Pine pivots left=right=10 | K线前端+FVG/EQL/OTE |
| 5 | LuxAlgo V34 | `scripts/v25/smc_core_luxalgo_v34.py` | min(parsedLows)在pivot-break间（LuxAlgo标准） | lux_pivots | **V46.1引擎OB/结构主力** |

## 影响

1. **K线信号 ≠ 回测信号**: 前端用引擎3+4，v46_1引擎用4+5。OB集不同，导致用户肉眼验证的信号和引擎使用的信号不匹配。
2. **选股列表偏差**: 选股基于引擎回测输出，但K线显示不同信号集，用户无法在K线上验证选股理由。
3. **结果不可复现**: 同一只股票在不同引擎产生不同OB/结构信合，聚合指标无法反映信号正确性。

## V46.1引擎实际管道

```
load_sig(kl):
  res32 = smc_core_pine_like(kl)        # → FVG, EQL, OTE, LV, BPR
  res34 = smc_core_luxalgo_v34(kl)      # → sweeps (合并+去重)
                                          # → swing_structure, internal_structure
                                          # → structure (swing + MSS内构)
                                          # → obs ← 使用LuxAlgo的OB！！！

build_symbol():
  → 使用混合信号源构建setup（来自两个引擎不同的信号集）
  → 通过backtest_v34_setups回测
```

这意味着V46.1引擎的OB来自LuxAlgo V34（引擎5），而FVG/EQL来自Pine-like（引擎4）。

## 修复建议

1. **统一为单一引擎**: 将LuxAlgo V34的OB/结构检测迁移到Pine-like引擎中，或将Pine-like的FVG/EQL迁移到LuxAlgo V34中
2. **或**: 在两者之间建立明确的信号合并规则（如: OB以LuxAlgo为准，FVG以Pine-like为准，统一信号命名和强度评分）
3. **清理死代码**: signals_v11, signals_v22, v44_engine.py 中已不再使用的代码

## 相关文件
- `smc-core-concepts` → `references/signal-accuracy-diagnostic.md` (详细修复记录)
- `smc-engine-v46` → SKILL.md (V46.1架构描述)
- `smc-v11-system` → SKILL.md (全局架构)
