# V62-V64 胜率提升门禁复盘（假突破 / REENTRY / CONTINUATION）

## 背景
本轮从 V61 出场层实验转向入场质量门禁，目标不是继续放宽结构止损，而是提升胜率并减少假突破/失败回踩噪音。关键结论：卖早和低 MFE 捕获不能只靠延迟出场解决，很多亏损源自入场前的假突破、失败回踩、低质量 FVG continuation 和弱 REENTRY。

## V62：假突破 / 失败回踩二次门禁
基于 V60/V61 复盘，V62 将 PRIMARY 全部转观察，保留 CONTINUATION/REENTRY，并加入二次门禁：

- PRIMARY_SETUP：不直接交易，只作 watch-only。
- CONTINUATION_SETUP：拒绝 LiquidityVoid_Bull；要求 `breakout_quality_score >= 50`，且通过 no_fast_return_to_range / retest_holds_raw_zone / no_reclaim_1_3。
- REENTRY_SETUP：比 continuation 更严格，要求 `breakout_quality_score >= 55`，同样拒绝 LV 和快速回 range / reclaim。

效果：V60 WR 65.69% → V62 WR 68.18%，avg_pnl 11.696% → 12.089%，avg_R 2.833 → 3.036，90D capture 0.276 → 0.297。

## V63：REENTRY 专项提升
V62 中 REENTRY 是拖累项：REENTRY WR 64.98%，CONTINUATION WR 70.26%。逐桶复盘发现：

- REENTRY OB_Bull 明显弱于 FVG_Bull。
- REENTRY 最优组合是 `FVG_Bull + BOS_Bull`。
- CHOCH/MSS 泛确认在 REENTRY 里容易是假二次入场。

V63 REENTRY 规则：

- `zone_type == FVG_Bull`
- `conf_type == BOS_Bull`
- `trend_score >= 4`
- `breakout_quality_score >= 55`

效果：REENTRY 从 554 笔 / WR 64.98% / avg_pnl 10.49% 提升到 94 笔 / WR 80.85% / avg_pnl 15.39%。整体 V63：948 笔 / WR 71.31% / avg_pnl 13.349% / avg_R 3.274 / 90D capture 0.316。

## V64：CONTINUATION 专项提升
V63 中主要交易源变为 CONTINUATION，复盘发现：

- OB_Bull continuation：107 笔，WR 88.79%，avg_pnl 19.3%。
- FVG_Bull continuation：739 笔，WR 67.79%，avg_pnl 12.31%。
- BPR_Bull continuation：8 笔，WR 50%，样本小且弱。

V64 continuation 规则：

- OB_Bull continuation：保留；若 `BQ >= 55 && trend_score >= 4`，仓位系数 1.0，否则 0.5。
- FVG_Bull continuation：只保留强确认：
  - `FVG + MSS_Bull + trend_score >= 4 + BQ >= 55`，或
  - `FVG + BOS_Bull + trend_score >= 4 + BQ >= 85`。
- BPR_Bull continuation：剔除。
- REENTRY 保持 V63 高胜率规则。

效果：V63 WR 71.31% → V64 WR 83.27%；avg_pnl 13.349% → 18.192%；avg_R 3.274 → 4.448；90D capture 0.316 → 0.379。交易数从 948 降至 269，属于主动收缩到最高质量桶。

## 可持续工作流
未来 SMC 胜率提升不要先改全局参数，应按以下闭环：

1. 先按 family × zone_type × conf_type × trend_score × BQ × exit_reason 透视。
2. 区分“结构本身弱”与“出场卖早”。若 SL/GAP_SL 集中，优先做入场门禁；若 STRUCT_CONFIRM_BREAK 卖早集中，再考虑出场层。
3. 不要把 OB/FVG/BPR 合并评估。OB continuation 与 FVG continuation 性质完全不同。
4. REENTRY 必须有 post-exit 后的新 BOS/强确认，不要把第一次 retest 当成二次确认。
5. 用 90D closed-loop 校验：WR、avg_pnl、avg_R、avg_90d_capture 必须同步改善；只提升 WR 但牺牲 R 或捕获率不是合格晋级。
6. 前端晋级必须同步：ACTIVE_VERSION、version loader、rerun 支持、summary/backtest/picks/autopsy/kline_full 验证。

## 关键坑
- 单纯延迟结构止损在 V61 验证收益有限，容易牺牲胜率和总体收益。
- FVG continuation 的低质量 CHOCH 是噪音大户，不能因为 continuation 总体尚可就全保留。
- PRIMARY_SETUP 在该阶段不适合作为直接交易源，应作为观察池或后续重新设计。
- 高胜率版本交易数会下降；不要为了样本量重新放开低质桶，除非逐桶复盘证明其可持续。
