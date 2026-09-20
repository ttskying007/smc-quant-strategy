# R59: E4'' 迭代候选假设登记(预注册, 未执行 — 需未来数据 frozen OOS)

由 R59 逐年/逐月/逐笔审计 combo_v21_trades.csv 产出。以下均为**假设, 未调参于冻结窗口**。

## A. 过滤/惩罚方向
### A1. trend_state=up 过滤 (STRONG)
- 事实: up 腿 334 腿 avg +1.28%, down 腿 1190 �腿 avg +4.49% → up drag 3.2pp
- 5/5 worst 均为 up 腿 (CHoCH↑/BOS↑)
- 假设: 进入后 rank penalize trend_state=up (或 gate)
- 风险: 上次 shadow gate 被 falsified (trend gate) — 但此时是 *penalize* 而非 gate, +结构特征组合
- 验: 未来数据 WR 是否回升 (frozen oos)

### A2. last_event_kind=反转类回避 (STRONG)
- BOS↓ 964 腿 +5.08 71%WR >> CHoCH+ BOS↑ 0.3-1.98%
- 假设: 反转类最近事件的 rank 降权
- 对应 R53 链审:"仍在破位下跌"是智钱签名

## B. 特征方向
### B1. supply_layers 反向信号 (MODERATE)
- 事实: 亏腿 avg 6.80 vs 全 7.30 — 低 supply 层(1-2) + downtrend 时反而更容易止损
- 假设: supply_layers 单调不是越高越好, 中间值(3-4)最优
- B2: 低 supply + CHoCH↑ = 高风险组合(观测 002722 类)

## C. 宏观/季节方向
### C1. 年初难 / 7-8 旺 (WEAK-REGIME)
- 202601-06 PF 0.6-1.5 (202605 PF 0.06); 202607-08 PF 6.6-20
- 202512 也 PV 0.13
- 假设: 年初季节性 bear-market regime, 7-8 注册制/政策窗口
- 验: 2026 年全年回放 (新数据) — 是否可作 macro filter

## 已执行(禁止在冻结基线调参)
- 以上均未纳入生产/paper_sim; 仅为审计报告。下一次数据周期(2026-09-21 +) frozen OOS 验证。
- 同类"gate"方向(A1,A2)必须做 **shadow 再 backtest**(R54 教训), 绝不可再 binary gate
