# V11.3 信号类型迁移指南

## 为什么要改

V11.2的信号定义存在概念混淆：
- FVG与IFVG检测同一类gap (无方向约束), 实际等效
- BPR被实现为"FVG回测"而非真正的Balanced Price Range
- CHOCH缺少ICT关键的位置约束 (MSS必须在流动性猎杀之上/下)
- BreakerBlock没有利用FVG重叠增强

V11.3基于ICT 4个交易模型 (标准反转/一击必中/超级模型/AMD) 做了全面修正。

## 信号类型变更表

| 旧类型 (V11.2) | 新类型 (V11.3) | 变化 |
|---------------|---------------|------|
| FVG_Bull | FVG_Bull | 同类型, 新增连续3阴线质量分级 |
| FVG_Bear | FVG_Bear | 同类型, 新增连续3阳线质量分级 |
| IFVG_Bull | **IFVG_Bull** (全新含义) | 从Inversion改为Implied, 影线中点法 |
| IFVG_Bear | **IFVG_Bear** (全新含义) | 同上 |
| (不存在) | **FVG_Mitigated_Bull** | 原Inversion逻辑改名 |
| (不存在) | **FVG_Mitigated_Bear** | 原Inversion逻辑改名 |
| BPR_Bull | **BPR** (direction='neutral') | 从FVG回测改为反向FVG重叠 |
| BPR_Bear | **BPR** (direction='neutral') | 同上 |
| CHOCH_Bull | CHOCH_Bull | +位置约束 (必须高于SSL sweep) |
| CHOCH_Bear | CHOCH_Bear | +位置约束 (必须低于BSL sweep) |
| BreakerBlock_Bull | BreakerBlock_Bull | +FVG重叠增强 |
| BreakerBlock_Bear | BreakerBlock_Bear | +FVG重叠增强 |
| SweepUp | SweepUp | +liquidity_type='BSL' |
| SweepDown | SweepDown | +liquidity_type='SSL' |
| OB_Bull/OB_Bear | OB_Bull/OB_Bear | 保持, -swing结构标注增强 |

## 代码迁移检查清单

搜索以下旧引用并更新:
```
BPR_Bull  →  BPR (check direction)
BPR_Bear  →  BPR (check direction)
IFVG (Inversion)  →  FVG_Mitigated  (if used as "filled FVG inversion")
```

## 直接影响

- **BPR不再有方向**: 新BPR是中性支撑/阻力区, direction='neutral'
  - 任何对BPR做方向过滤的地方需要修改: `sig_type == 'BPR'` 取代 `sig_type == 'BPR_Bull'`
  - BPR count不再区分bull/bear, 统一计数

- **IFVG不再依赖FVG**: 新IFVG独立检测(不依赖FVG_signals参数)
  - 调用签名从 `detect_ifvg_v11(ohlcv, fvg_signals, tf)` 改为 `detect_ifvg_v11(ohlcv, adaptive=adaptive, tf=tf)`

- **FVG不再需要C2 body >=60% ATR**: 改为C2 body_ok OR 3-consecutive-color
  - 任意gap + c2_body_ok = 标准FVG
  - 3连续同色 + gap = 高置信FVG (confidence+0.15)

## 已知限制

- CHOCH位置约束依赖sweep_signals参数: 无sweep数据时放行(兼容旧模式)
- BPR只检测Bull→Bear顺序: 每Bull FVG取其后30K线内的最近Bear FVG
- IFVG的1.5%中点差阈值在低波动股票上可能还是太宽松, 需观察
