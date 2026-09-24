# R89 — SMC 检测器"跨股票/跨周期自适应" 实证一期

日期: 2026-09-24 | Round 1/goal: "SMC 指标识别跨股/周期/时间段自动适应深度迭代"

## 1. 解剖 (当前 detector 的症)
`hermes/scripts/v25/smc_detector.py`(229 行） 全部硬编参数：
- `find_swings(min_bars=3)` — swing 翼固定
- BOS/CHoCH 穿透阈值 0.1% — 与个股波动无关
- 突破窗口 40bar、sweep 触发区 ±0.2% — 全部固定

**跨股 ATR% 分布采样 40 只： 1.36% ~ 7.36% 5.4x** 跨度 — 一把尺子量所有股票 = 逻辑断裂.

## 2. 三种参数化对比 （同一40股 × 800bar)

| detector | 信号量/100bar | min | max | 跨度比 | 判 |
|---|---|---|---|---|---|
| FIXED （现版） | **22.7** | 15.8 | 34.2 | 2.2x | 明显过密， 噪声为主 |
| ADAPT (ATR% 硬映射 wing=round(ATR%×1.7), cap 2-6) | **7.6** | 2.4 | 20.6 | 8.6x | 矫枉过正： 高波股饿死， 低波股仍厚 |
| **NORM （密度收归： wing 从 2-8 浅层搜 索， 命中 swings/100bar ∈ [8, 14] 区间）** | **7.9** | 4.3 | **13.2** | 3x | **动接同一个节奏语义** |

**核心领悟**: 我们不需要"波动→参数的确定性映射". 更稳的画法是 **先把 swing 形状度跨股扫度归一** (就像一个"结构事件" 最好对应在 A 股任何一个标的地图上都有可交互的意义）, 然后再做 BOS/CHoCH 之类识别， 否则逐股票的 密度本身就已给了第二维交差点.

## 3. v22 腿链翻转深度 (80 腿样本， 800bar 上下文）
用 NORM detector 重新计算 lag 识到的 "最近结构事件" (BOS/CHoCH):
- **翻转率 59.1%**(39/66) — 骨头里换了个思维， 不是一个表面修补

意味： 如果 v24 影子深整权重有的单腿趋势都依托于 `last_event`:
- 一棗重算下来 60% 股児"最新趋势"需要 重写
- 这是从头埖代得起的事情 — 因为决策性跨联格式（rank components, s7 s9) 都走 SM chain
- **v22 chain_json 需要重算**： 1858 腿， 中途重算显著事件会转变

## 4. 下阶段画脚
- (R90) NORM 包装入 smc_detector: `find_swings_adaptive(klines, target_density=(8,14))` + `detect_smc_signals(klines, mode='norm')` 保向后并行
- (R90) 1858 腿链路重复，`combo_v22_chain_v2_norm.csv`, 以 影子权重重计算总
- (R91) 量化影响： 腿级的 PnL 预测力 — voxel pattern (BOS kind × trend) 用两种 detector 叙 Gini
- (R92) 图页 / K线也切换看上去 （及跳到 v22 chain_v2)

## 5. 决策点
- 继续： 包到 smc_detector + 重选型 1858 落 → 再做形态重估量 → 判定午门
- 难度预估： 每腿 200bar 上下文 × engine ~50ms → 1858×0.05 ≈ 90s 一次重算， 开放式易决
