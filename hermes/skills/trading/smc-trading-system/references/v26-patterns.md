# V26 过滤平衡方法论

## 核心原则: 分层过滤 + 数据驱动迭代

过滤不能一蹴而就 — 必须先验证每层过滤的实际WR影响，再决定松紧。

## 2026-05-19 迭代实录

### 第1轮: 激进过滤 (WR=96.4%, 仅28笔)
- 问题: zone_age≥2 + weekly硬过滤 + MTF REJECT → 交易太少
- 用户反馈: "回测数据有些偏少，总交易笔数也少"

### 第2轮: 全面放松 (WR=76.3%, 76笔)
- 移除weekly过滤、放宽zone_age、MTF不REJECT
- 问题: ALIGNED MTF(59笔/WR=69.5%) 和 TREND_DOWN(44笔/WR=63.6%) 拖累WR

### 第3轮: 精准切割 (WR=87.8%, 41笔)  
- MTF REJECT + ALIGNED门槛放宽(≥3)
- 问题: ALIGNED(24笔/WR=79.2%)仍拖累

### 第4轮: ALIGNED×TREND_DOWN过滤 (WR=94.3%, 35笔) ✅
- STRONG MTF全保留 + ALIGNED排除TREND_DOWN
- 最佳平衡: WR=94.3%, 35笔, 仅2亏损

## 教训

1. **Silent filter trap**: MTF REJECT没有计数器时，交易被静默吞掉。每个continue必须有对应的跳过计数器
2. **分层验证**: 每层过滤必须先跑全量回测看WR，再决定是否保留
3. **组合过滤优于独立过滤**: 单独过滤ALIGNED或TREND_DOWN都不够，必须组合过滤 ALIGNED+TREND_DOWN
4. **BPR zone需MTF加分**: BPR占61%的选股，不给MTF质量加分导致MTF评分过低

## 已知弱组合 (回测验证)

| 组合 | WR | 原因 |
|------|-----|------|
| FVG_Bull + CHOCH_ENTRY | 75% | CHOCH在FVG上确认质量差 |
| BPR + CHOCH_ENTRY + HIGH_VOL | 60% | 高波动下CHOCH不稳定 |
| ALIGNED + TREND_DOWN | 63-69% | 下跌趋势中ALIGNED信号不可靠 |
| IFVG_Bull (任何confirm) | 42-46% | 反向FVG不可靠 |
| BreakerBlock_Bull (任何confirm) | 41-50% | 假突破多 |
| OTE_ENTRY (任何zone) | 52% | OTE确认质量差 |

## MTF评分校准

```
conf_bonus: PINBAR=3, BOS=2, CHOCH=2, SWEEP=2, IDM=3, TURTLE=4
zone_bonus: OB_Bull=1, FVG_Bull=1, BPR=1 (2026-05-19: BPR新增)
weekly: price>MA20=+1, near_60D_high=+1
阈值: STRONG≥6, ALIGNED≥3, else REJECT
```

## TREND_DOWN参数

sl_atr_mult: 1.0 (必须比TREND_UP宽50%+)
trail_activate: 0.6 (更早激活跟踪保护)
min_rr: 0.35 (下跌趋势中接受更低RR)
