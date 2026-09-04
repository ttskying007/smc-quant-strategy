# SL/TP设计缺陷诊断 (V7.6修复)

## 缺陷列表 (10项, 2026-05-15诊断)

### 1. SL=zone×0.95 无波动率自适应
A-stock daily ATR 2-4%. SL=5%对于高波动股太紧，低波动股太松。
**V7.6修复**: `SL = zone_low × (1 - max(3%, ATR% × 1.5))`

### 2. 无结构性SL  
SMC正解: SL应在摆动低点/前FVG底部/前OB底部，不是固定%。
**状态**: 未完全实现，仍用ATR-based替代

### 3. Trail激活+3%过早
A股日线2-4%波动 → 大多数bar触发激活 → 然后2%回退出场。
**V7.6修复**: `TrailAct = entry × (1 + max(2%, ATR% × 1.0))`

### 4. Trail距离2%固定
高波动股2%是噪音，低波动股2%太宽。
**V7.6修复**: `TrailDist = max(1.5%, min(4%, ATR% × 0.7))`

### 5. 无分批止盈
一次全出 → 错失后续行情。应分2-3批: TP1@+5%, TP2@+10%, 余量trailing。
**状态**: 未实现，架构限制

### 6. 无时间止损
max 20bar EOD 任意设定。应基于信号类型和时间衰减。
**状态**: 未实现

### 7. 无跳空保护
T+1下隔夜跳空可穿透SL。应检测gap_risk并调整仓位。
**状态**: 未实现

### 8. 无成交量确认
高量回落vs低量噪音同等对待。应: 放量跌破trail才退出。
**状态**: 未实现

### 9. 入场bar的高点参与trail (V7.5修复)
Entry bar high直接设prev_trail_sl → 次日low触发。
**V7.5修复**: min_hold=2bar, 前2bar不检查trail

### 10. 未区分信号质量
OB_Bull(WR=97.7%)和Sweep→Pinbar(WR=65%)用同样的SL/TP → 浪费高WR信号。
**状态**: 未实现，架构限制

## V7.6完整参数

```python
MAX_WAIT = 3
SL_ATR_MUL = 1.5       # SL = zone × (1 - max(3%, ATR% × 1.5))
TRAIL_ACT_ATR_MUL = 1.0 # Act = entry × (1 + max(2%, ATR% × 1.0))
TRAIL_DIST_ATR_MUL = 0.7 # Dist = max(1.5%, min(4%, ATR% × 0.7))
MIN_HOLD_BARS = 2
WEEKLY_FILTER = True    # MA20 above by 2%
```

## 效果

V7.5→V7.6: avgPnL +9.11%→+13.11% (+44%), OB_Bull +12.17%→+19.48% (+60%)
