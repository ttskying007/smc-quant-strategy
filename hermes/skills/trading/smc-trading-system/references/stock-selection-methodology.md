# V7.6 选股方法论

## 筛选流程
1. 全量扫描: scan_LD_v6.py → LD_picks_v6.json (~13,000 picks)
2. 回测过滤: backtest_v63_full.py (future function + weekly + ATR)
3. 质量评分: gap + distance + signal_type + weekly → score
4. 监控同步: active_positions.json → smc_unified.py /monitor

## 质量标准 (当前)
```python
# Signal type priority
if 'OB_Bull' in signal: base_score = 50, max_gap = 3
elif 'BOS_Bull→FVG' in signal: base_score = 40, max_gap = 2
elif 'CHOCH_Bull→FVG' in signal: base_score = 35, max_gap = 2

# Distance bonus (closer to zone = better)
dist_pct = (last_close - zone_low) / zone_low * 100
if retrace: dist_pct must be 0-6%
if immediate: dist_pct must be -1 to 4%

# Weekly filter
last_close > MA20_weekly * 1.02

# Final score
score = base_score - gap * 5 - abs(dist_pct) * 3 + (5 if weekly_ok else 0)
```

## 结果分布 (2026-05-15)
扫描13,106 picks → 过滤后53只精品
- OB_Bull: 46只
- BOS_Bull→FVG: 4只
- EQL→FVG: 2只
- CHOCH→FVG: 1只

过滤统计: gap=36, dist=11,593, state=294, weekly=694, score=436

## Pinbar角色
Pinbar_Bull仅作为SMC入场确认工具，不作为独立信号。
Engulf/Harami/Pierce已从ZONE_TYPES移除。
严格锤子线条件: 下影>实体×2.5, 下影>振幅×0.6, 上影<振幅×0.15, 收在上半部。
