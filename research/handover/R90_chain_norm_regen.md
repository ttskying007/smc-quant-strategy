# R90 — core.structure 自适应重生 + 1858 腿全链重算

日期: 2026-09-24 | Round 2/goal

## 1. 现版本骨病(core.structure.structure_events)
- `pivot=3` 硬编 (同 swing 的翼)
- BOS/CHoCH 穿透 **0 阈线**（任何收盘价刚好往上 1 分都计事件）
- HH/HL/LH/LL 需按相邻摆动排序 — 复与 swing 密度正常化

## 2. 修改（向后兼容)
- `core/structure.py`: 加 `pick_pivot_by_density(...)` (跨股 swings/100bar 收归到 8~14) + `structure_events(..., mode='auto'|'fixed')` 在 auto 下挂自适应 pivot + 穿透缘 `0.15 * ATR%`;
  `mode='fixed'`（默认）为 原行为
- `core/chain.py`: `build_chain(bs, i, mode='fixed')` 加 mode='auto' 透传； _swing_levels 使用自适应 pivot
- 默认入参未变 → **零路上层破坏** (gen_v22_chain.py / paper_sim.py / smc_unified.py 全部是调用而面轮廓同旧）

## 3. 全量重算 (`combo_v22_chain_v2_norm.csv`, 1858 一致， 49s)

### 跨股翻转分布
| 字段 | 翻转 | % |
|---|---|---|
| trend_state | 163 | 8.8% |
| last_event_kind | 516 | 27.8% |
| breakout_kind | 516 | 27.8% |
| retrace_state | 543 | 29.2% |

### 关键语义发现（翻转矩阵净均值）

| 翻转 | n | avg pnl | 叙事 |
|---|---|---|---|
| BOS↑ → CHoCH↑ | 75 | **+6.32%** | 旧版 dense pivot 贴类"延续" 但实为**转市反**(分母大动，比迟疑变我们还䠟了， 单收益还馀富） |
| CHoCH↑ → BOS↓ | 108 | +1.42% | 旧版报"牛反转" 实为**熊延续** → 这类翻转在单低周转快啫 — 是去除噪声的好兆 |
| CHoCH↓ → BOS↓ | 59 | +0.44% | 牛上转出贴为"反转"的种同，是塌右价 安魔带 |
| retrace_ok → no_retrace | 160 | +6.71% | 旧版松门说"回踩成功"但新低敏显著后患得故 |

## 4. 影子手术 S1-S14 受影响量
| 手术 | 依赖字段 | 预计翻转腿数 |
|---|---|---|
| S1 (CHoCH) | last_event_kind | 469 |
| S7 (up_trend) | trend_state | 163 |
| s10-s13 (fvg/ob/ote/lv) | 无受 （未换） | 0 |
| s14 (idx) | 无受 | 0 |

## 5. 下一轮要点
- R91: `gen_v23_shadow.py` 的 paper_real `_v23_of` 用 v2 chain 重打 14 个标签， 对吧， 全品 PF 上书，不怪的， 不能冒天复制里
- R92: 股_CBC 下几异动观察年度东路
- R93: 決定是否三锁到引擎上 (股票套利， 起动迁换 entropy)
