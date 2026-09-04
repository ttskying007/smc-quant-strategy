# V17 信号准确性最终修复 (2026-05-12)

本会话的核心教训：逐根K线验证信号位置，通过具体日期定位偏差。

---

## 1. OB: first-match closest to swing (最关键的修复)

### 问题
Pine `disp = swing_low - hist_low` 检测 capitulation 模式（OB wick 低于 swing）。
displacement=1.5 硬过滤把正确近端 OB（bar 25, ratio=0.34）过滤掉，误取远端弱蜡烛（bar 22, ratio=2.94）。

### 根因
displacement 应该是**质量评分**，不是**硬过滤**。OB = swing 前**最近**的反向蜡烛。

### 修复
- 从 swing-1 向后扫描，取**第一个**匹配方向的蜡烛（不检查 displacement）
- displacement 仅用于 strength 评分
- 附加 proximity_bonus：越靠近 swing 的 OB 得分越高

### 验证 (600519.SH)
| 用户指出 | 修复前 | 修复后 |
|---------|--------|--------|
| 20250311 OB | bar 22 (距swing 4bar) | bar 25 (距swing 1bar) |
| 20250509 OB | bar 61 (距swing 3bar) | bar 62 (距swing 2bar) |
| 20250721 OB | bar 111 (距swing 3bar) | bar 113 (距swing 1bar) |

代码位置: `signals_v17.py` → `detect_ob_v17()`, method='first_match'

---

## 2. 共识摆动 (Consensus Swings)

### 问题
单一 lookback 的 pivothigh/pivotlow 产出数学 pivot，其中很多不是真正的 HH/HL/LL/LH 结构点。

### 解决方案
在 6 个 lookback [5,8,10,12,15,20] 中检测摆动，只保留 ≥4 个级别都出现的点。

### 效果 (600519.SH)
| 方法 | Highs | Lows |
|------|:-----:|:----:|
| (5,5) | 14 | 11 |
| (10,10) | 9 | 8 |
| 共识 ≥4/6 | **7** | **6** |

共识摆动用于：CHOCH/BOS, OB, SWEEP — 确保所有信号只出现在真正的结构转折点。

函数: `detect_consensus_swings(ohlcv, min_confirmations=4)` in `signals_v17.py`

---

## 3. SWEEP: 降低阈值

### 问题
`min_wick_ratio=1.2` 过滤了有效 sweep（close 反转但 wick 不够长）。
仅检测到 3 个 sweep (600519.SH)。

### 修复
- `min_wick_ratio`: 1.2 → **0.5**（允许 close 反转模式）
- `min_penetration`: max(atr*0.25, price*0.002) → max(atr***0.2**, price***0.0015**)
- `recent_limit`: 20 → **25** bars

### 效果
600519: 3→9, 000001: 1→10, 002594: 3→10

---

## 4. MSS: 提高阈值减少噪声

### 修复
- `min_spacing`: 15 → **25** bars
- `min_break_pct`: 0.3% → **0.5%**

### 效果
600519: 13→9, 000001: 14→9

---

## 5. 用户偏好（已编码）

- **不让选择** — 测试所有方案，交付最优结果
- **信号准确性优先于 WR/RR** — 宁可信号少但位置对
- **逐根K线验证** — 通过具体日期定位偏差，不是看总体指标
- **HH/HL/LL/LH 结构点** — 信号必须在结构转折点，不是趋势中间
- **多 lookback 验证** — 单一 lookback 的 pivot 不一定是结构
- **displacement 是评分不是过滤** — OB = 最近反向蜡烛

---

## 6. OB displacement 方向修正

标准 SMC: OB 高于 swing（Bull, 价格从 OB 跌至 swing 再反转）
Pine 检测: capitulation 模式（OB wick 低于 swing）

| 方向 | 修复前 (Pine capitulation) | 修复后 (标准 SMC) |
|------|--------------------------|-------------------|
| Bull OB | `disp = sl_price - bar['l']` | `disp = bar['l'] - sl_price` |
| Bear OB | `disp = bar['h'] - sh_price` | `disp = sh_price - bar['h']` |

症状: CMB OB=0 → 修复后 CMB OB=24
