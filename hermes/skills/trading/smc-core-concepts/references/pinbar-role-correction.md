# Pinbar 在SMC中的正确角色 (V7.5修正)

## 核心纠正

Pinbar (锤子线/流星线) 在SMC中是**入场确认工具**，不是独立信号。

### 错误用法 (V7.4及之前)
- Pinbar_Bull、Engulf_Bull、Harami_Bull、Pierce_Bull 均作为独立zone类型
- 它们被当作POI (Point of Interest)，与OB/FVG同级别
- 结果: 1,385个蜡烛形态combo信号，但大多数不准确

### 正确用法 (V7.5起)
- **Pinbar_Bull (Hammer)**: 保留为zone类型(SMC标准concept)
- **Engulf/Harami/Pierce**: 移除独立zone，仅作OB/FVG处的入场确认
- Pinbar应出现在已建立的PD Array(OB/FVG/Breaker Block)处

## 检测标准 (V7.5严格)

```python
# 严格Hammer检测
is_bull = c > o
lower_wick = o - l
upper_wick = h - c
if lower_wick > body * 2.5 and lower_wick > range_hl * 0.6 \
   and upper_wick < range_hl * 0.15 and c > (o + l) / 2:
    # Valid Pinbar (Hammer)
```

条件:
- 下影 > 实体 × 2.5 (原2.0)
- 下影 > 振幅 × 0.6 (原0.5)
- 上影 < 振幅 × 0.15 (原0.2-0.25)
- 收在上半部 (新增)

## 抽样验证 (2026-05-15)

000070: 3个pinbar, 2/3正收益(+5.9%, +7.2%)
600519: 3个pinbar, 2/3正收益(+3.4%, +2.2%)
总计: 4/6正 (67%)

## 与OB/FVG的关系

正确的SMC入场流程:
1. 识别PD Array: OB_Bull 或 FVG_Bull
2. 等待价格回调到zone
3. **在zone处出现Pinbar** → 入场确认
4. Pinbar低点 = zone_low → retrace entry

## 文件修改

- `scan_LD_v6.py`: ZONE_TYPES移除Engulf/Harami/Pierce
- `smc_unified.py`: 前端的信号家族简化
- `backtest_v63_full.py`: RETRACE_SIGNALS只保留OB_Bull+Pinbar_Bull
