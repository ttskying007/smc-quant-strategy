# V6 OB上下文矩阵 — 架构详解

## 组件架构图

```
K线缓存 (KLINE_CACHE: 4905只日线)
    │
    ├─ scan_LD_v6.py (扫描器, 工作日9:00 cron)
    │     │
    │     ├─ detect_all_signals_v20() → V20信号 (Sweep/BOS/CHOCH/MSS/EQL/OB/FVG)
    │     ├─ detect_pinbars() → Pinbar_Bull (长下影+收阳)
    │     ├─ detect_fvg_fills() → FVG回补率
    │     ├─ weekly_trend() → HTF趋势过滤
    │     ├─ 逐bar: L1 OB_Bull(独立+ctx标签) + L2 CTX→POI(全窗口)
    │     ├─ Dedup: (sym, entry_bar) L1优先
    │     └─ → LD_picks_v6.json (12886 picks)
    │
    ├─ monitor_check.py (监控, 每30min cron)
    │     ├─ 读LD_picks_v6.json
    │     ├─ Tencent ifzq API实时价格
    │     ├─ 逐bar遍历TP/SL
    │     └─ → live_monitor_v5/{positions,pnl_log}.json
    │
    └─ smc_unified.py + monitor_page.py (前端, 8890端口)
          └─ /monitor → V6 Dashboard (60s刷新)
```

## CTX × POI 矩阵设计

### POI类型 (3种)
```
OB_Bull:      摆动点前最近反向蜡烛 — 最强POI
FVG_Bull:     连续3根K线间的价格缺口 — 中等POI  
Pinbar_Bull:  长下影(影>实体×2, 影>幅度×50%)+收阳+小上影 — 新增POI
```

### CTX类型 (5种)
```
LIQ:
  Sweep_SSL:  价格扫过前低后收回 — 流动性捕获
  EQL:        相等低点 — 流动性堆积

STRUCT:
  CHOCH_Bull: 结构转变(LL→HH) — 趋势反转确认
  BOS_Bull:   突破前高 — 趋势延续确认
  MSS_Bull:   市场结构转变 — 趋势转换信号
```

### 矩阵 (CTX → POI)
总计15种可能组合(5×3)，实际V6有10种:
```
               OB_Bull     FVG_Bull    Pinbar_Bull
Sweep_SSL      L1(ctx)     L2(106)     L2(103)
EQL            L1(ctx)     L2(28)      L2(32)
BOS_Bull       L1(ctx)     L2(80)      L2(24)
CHOCH_Bull     L1(ctx)     L2(33)      L2(13)
MSS_Bull       L1(ctx)     L2(17)      L2(12)
```
注: CTX→OB_Bull不产生独立L2信号，而是作为L1 OB_Bull的上下文标签(ctx_count/ctx_types)。

## Pinbar检测算法

```python
def detect_pinbars(daily):
    for i in range(20, len(daily)):
        b = daily[i]
        body = c - o            # 阳线实体
        range_hl = h - l        # 全振幅
        lower_wick = o - l      # 下影线
        upper_wick = h - c      # 上影线
        
        if lower_wick > body * 2 and lower_wick > range_hl * 0.5:
            if upper_wick < range_hl * 0.2:
                # Pinbar_Bull: 长下影 + 小上影 + 收阳
```

## ZONE scoring (L2组合)
```python
z_score = (gap * -1.5) + bonus
bonus: OB_Bull=3, Pinbar_Bull=2, FVG_Bull=1
```
OB在gap=5时(score=-1.5) vs FVG在gap=1时(score=+0) → FVG仍胜
OB在gap=3时(score=+1.5) vs FVG在gap=1时(score=+0) → OB胜

## 4个已知Bug及修复

1. **break bug** (V5): 第一个ZONE bar就break → 修复: 全窗口扫描, best_zone打分
2. **L1/L2冲突**: 同一entry_bar去重, L1优先 → 架构设计, OB独立不序列化
3. **Pinbar缺失** (V5): POI只有OB/FVG → V6新增Pinbar_Bull
4. **scoring权重** (V5): gap×1+bonus, Pinbar=0 → V6 gap×1.5+bonus, PB=2

## 数据文件格式

### LD_picks_v6.json
```json
{
  "meta": {"version": "V6 Context-Matrix", ...},
  "market_states": {"000001.SZ": {"state": "mean_reversion", "fill_rate": 0.85}},
  "combo_summary": {"OB_Bull": 12438, "Sweep_SSL→FVG_Bull": 106, ...},
  "picks": [
    {
      "symbol": "000001.SZ",
      "tier": "L1",
      "signal": "OB_Bull",
      "score": 0.6,
      "entry_price": 12.51,
      "sl": 12.31,
      "tp": 12.78,
      "ctx_count": 2,          // L1专属: 前序信号数量
      "ctx_types": ["BOS_Bull","Sweep_SSL"],  // L1专属
      "signal_date": "20260514",
      ...
    },
    {
      "tier": "L2",
      "signal": "Sweep_SSL→Pinbar_Bull",
      "start_type": "Sweep_SSL",  // L2专属
      "start_bar": 36,            // L2专属
      ...
    }
  ]
}
```
