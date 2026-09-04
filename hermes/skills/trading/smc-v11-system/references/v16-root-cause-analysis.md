# V16 Signal Diagnosis Methodology — 可复用诊断框架

本会话成功定位并修复了V15中的6个code-level缺陷。诊断方法值得复用。

## 诊断流程 (5步)

### 1. 单股票完整trace
不要对比指标, 直接从检测引擎输出原始数据:
```python
from signals_vXX import detect_all_signals_vXX
result = detect_all_signals_vXX(ohlcv)
# 逐个信号打印: idx, metadata, 关联的摆动点
```

### 2. 逐摆动点验证
打印所有摆动点: `detect_swings(ohlcv)` → 输出 `{highs: [...], lows: [...]}`。检查:
- 确认的摆动点是否在正确的结构位置
- 摆动点密度是否足够(Pine vs 300bar的差异)

### 3. 逐信号类型trace
对每个信号类型独立运行检测函数, 打印metadata中的关键字段:
- OB: `swing_bar, displacement_ratio, impulse_bars`
- CHOCH/BOS: `break_level, break_pct, prior_trend`
- Sweep: `swept_bar, wick_pct` — 检查穿透幅度是否合理
- EQL: `threshold vs actual diff` — 检查阈值是否可达

### 4. 数值对比Pine逻辑
逐行对比Python实现与Pine参考的赋值语义:
- Pine `:=` = Python `=` (直接赋值/overwrite)
- Pine `>`/`>=` 检查是否有方向性差异
- Pine `ta.atr(200)` vs Python `ATR(15)` — 周期差异导致阈值偏差

### 5. 修复后重trace
修复后立即运行同样的trace脚本, 确认数值变化是否合理:
- CHOCH 1→5 说明修复有效
- EQL 0→5 说明双模式可行
- BPR 55→5 说明过滤正确

## 关键教训

### Pine赋值 vs Python更新
最常见的bug不是"算法不对", 而是**赋值语义差异**:
- Pine: `last_swing_high := swing_high_ms` → 用最新值替换
- Python(错误): `if sw['price'] > last_swing_high: last_swing_high = sw['price']` → 取最大值, 造成极值追踪
- Python(正确): `last_swing_high = sw['price']` → 直接赋值(overwrite)

### 300bar密度问题
Pine在完整图表(数千bar)上运行, Python只用300bar:
- EQL: 连续pivot阈值 ATR*0.1 在300bar上极少触发 → 需要dual-mode
- OB: 300bar确认摆动点数量有限 → 需要合理设置left/right参数

### 信号数量≠质量
- BPR=55不代表"覆盖好", 而是O(n²)噪声
- Sweep=6不代表"检测灵敏", 而是0.08%噪音也被计入
- 减少信号数如果来自**正确的过滤**, 是好结果(BPR 55→5)
