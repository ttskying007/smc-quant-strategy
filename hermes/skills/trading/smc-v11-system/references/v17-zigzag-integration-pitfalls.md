# V17 Zigzag 集成陷阱 — CHOCH/BOS 与 SWEEP

本文件记录 2026-05-12 会话中发现的两个与 zigzag 摆动集成相关的关键陷阱。

---

## 1. CHOCH/BOS: zigzag 摆动翻转过快 → 全判 CHOCH

### 症状

使用 zigzag 摆动后，所有结构突破都被判为 CHOCH，BOS=0。

### 根因

zigzag 摆动在 bar_idx（极端 bar）即时出现，不像 pivothigh 有 right-bars 延迟确认。
当 old swing high 被突破之前，一个 zigzag swing low 可能已在新位置出现，
使得 `in_uptrend = last_high_bar > last_low_bar` 变为 False。
此时再突破 old high → 被判为 CHOCH（trend reversal），而非 BOS（continuation）。

```
时间线:
  bar 26: zigzag swing HIGH @ 1658  → in_uptrend = True
  bar 40: zigzag swing LOW @ 1462   → in_uptrend = False (过早翻转!)
  bar 48: close > 1658              → CHOCH_Bull ❌ (应判 BOS_Bull)
```

### 修复

不要用 zigzag 摆动的新旧来判断趋势方向。改为 **label-based 趋势状态机**：

```python
# 1. 从 zigzag 最新摆动初始化趋势
sh_newest = max(h['bar_idx'] for h in swing_highs)
sl_newest = max(l['bar_idx'] for l in swing_lows)
swing_trend = 1 if sh_newest > sl_newest else -1

# 2. 突破检测时用 swing_trend 判断，而非 zigzag 摆动新旧
if close > last_swing_high:
    if swing_trend == -1: → CHOCH_Bull; swing_trend = 1
    else:                 → BOS_Bull

# 3. 趋势状态只在 label 产生时更新（不在每个 zigzag 摆动更新）
```

### 效果

| 股票 | 修复前 (zigzag trend) | 修复后 (label-based trend) |
|------|:---------------------:|:--------------------------:|
| 600519 | CHOCH=9 BOS=0 | CHOCH=3 BOS=6 |
| 002594 | CHOCH=12 BOS=0 | CHOCH=4 BOS=8 |

---

## 2. SWEEP: zigzag idx (确认 bar) 错过实时扫荡

### 症状

SWEEP 信号过少（5-8/股票），即使降低穿透阈值也无效。

### 根因

zigzag 摆动有两个 bar 索引:
- `bar_idx`: 极端发生的实际 bar（如 bar 26 是高点）
- `idx`: 确认 bar（bar_idx + right，如 bar 33 才确认）

原 SWEEP 检测用 `hs_by_bar[h['idx']]` — 摆动在 bar 33 时才可用。
但扫荡可能发生在 bar 30-32（极端 bar 之后、确认 bar 之前），此时 swing level 还不可用 → 错过。

### 修复

用 `h['bar_idx']` 代替 `h['idx']` 做 lookup：

```python
# 错误: 延迟确认错过实时扫荡
hs_by_bar.setdefault(h['idx'], []).append(h)

# 正确: 极端 bar 立即可用
hs_by_bar.setdefault(h['bar_idx'], []).append(h)
```

同时放宽保留窗口从 25→30 bars（补偿无确认延迟的摆动存活期）。

### 效果

| 股票 | 修复前 (idx) | 修复后 (bar_idx) + 阈值放宽 |
|------|:-----------:|:--------------------------:|
| 600519 | 8 | 14 |
| 600036 | 21 | 42 |
| 000001 | 9 | 20 |

---

## 当前参数 (2026-05-12 会话后)

| 参数 | 旧值 | 新值 | 理由 |
|------|------|------|------|
| CHOCH/BOS break_pct | 0.3% | 0.15% | zigzag 摆动间距大，小突破即有效 |
| structure_spacing | 20 | 12 | 配合 zigzag 更密集 |
| SWEEP min_penetration | ATR×0.25, 0.2% | ATR×0.15, 0.1% | bar_idx 提前可用，放宽阈值平衡 |
| SWEEP wick_ratio | 0.5 | 移除 | 扫荡关键是穿透+收盘回，非影线比 |
| SWEEP swing_window | 25 | 30 | 补偿无确认延迟 |
| SWEEP lookup | h['idx'] | h['bar_idx'] | 实时可用 |
