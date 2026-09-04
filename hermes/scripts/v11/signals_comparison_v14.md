# V11 vs Pine Script 信号引擎对比分析 (2026-05-12)

## 量化验证 (4只股票, 300 bars daily)

| 信号类型 | V11 均值 | vPine(Pine参考) 均值 | 差异 | 问题等级 |
|---------|:-------:|:-------------------:|:----:|:-------:|
| OB | 29 | 12 | V11多141% | 🔴严重 — 假信号 |
| EQL | 30 | 3 | V11多900% | 🔴严重 — 过度检测 |
| CHOCH | 1 | 1 | 相同 | 🟡两者太少 |
| FVG | 28 | 43 | vPine多54% | 🟢FVG不是问题 |
| MSS | 54 | 54 | 相同 | 🟢可信(共用代码) |
| Sweep | 2.5 | 2.5 | 相同 | 🟢可信 |
| OTE/PO3/IFVG | 相同 | 相同 | 相同 | 🟢可信 |

## 根因分析

### 1. OB: 扫描方向错误 (V11 line 755)
V11: `for i in range(5, n-3):` 逐根K线向前扫描，找bearish candle+后续impulse
Pine: 从摆动点向后扫描，找impulse之前的最后反方向K线
→ V11检测到所有"下跌后又上涨"的K线对，不管位置。真正的ICT OB应该只在摆动点附近。
修复: 向后扫描 + 位移过滤器 (range displacement >= 1.3x)

### 2. EQL: O(n²)暴力扫描 (V11 line 1621)
V11: `for i in range(...): for j in range(i+2, i+15+1):` 所有K线对比较
Pine: 只检查摆动高/低点之间的相近水平
→ V11在300根K线中做了~4000次比较，0.3%容差必然匹配。任何震荡区域都会触发。
修复: 只对摆动点做EQH/EQL检测（摆动点+摆动点对比，不是K线+K线）

### 3. CHOCH: 摆动点检测无右确认 (V11 line 951)
V11: `for i in range(lookback, n-lookback):` 手动比较前后lookback根K线
Pine: `ta.pivothigh(high, left, right)` 内置右确认
→ V11的摆动点=任何局部极值。CHOCH需要找"最后被突破的摆动点"——摆点不准CHOCH就不准。
修复: 右确认摆动点 + 状态机结构检测

## 重构策略 (signals_v14.py)

1. 统一swing: Pine-style pivothigh/pivotlow (left=8, right=3 for 60min; left=10, right=5 for daily)
2. OB: backward scan from swings + displacement >= 1.3x + volume confirmation
3. CHOCH: state machine (track trend via swing HH/HL, detect BOS/CHOCH on crossover)
4. EQL: pivot-based (only compare swing highs/lows, tolerance based on price range)
5. FVG/Sweep/MSS/IFVG/OTE/PO3/BPR: reuse V11 logic (verified)
