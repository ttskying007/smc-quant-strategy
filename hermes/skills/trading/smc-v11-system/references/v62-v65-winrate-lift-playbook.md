# V62–V65 胜率提升迭代复盘：假突破、REENTRY、CONTINUATION、亏损门禁

## 背景
当用户要求“继续提升胜率”时，不能只做参数调优或只报 WR/RR。应先对上一版本剩余亏损逐笔复盘，再从信号族、zone、confirmation、BQ、trend、出场原因、GAP_SL、日期/股票集中度中找可持续前兆，最后形成新版本门禁并做全链路验证。

## 推荐流程
1. **先拆主要拖累源**
   - 按 `v59_setup_family` 拆：PRIMARY_SETUP / CONTINUATION_SETUP / REENTRY_SETUP。
   - 按 `zone_type + conf_type` 拆：OB/FVG/BPR × BOS/CHOCH/MSS。
   - 按出场拆：SL_HIT / GAP_SL_HIT / TIMEOUT / STRUCT_CONFIRM_BREAK。
   - 检查亏损是否集中在股票、月份、年份；若不集中，优先看信号结构前兆而非个股黑名单。

2. **假突破 / 失败回踩门禁（V62 类）**
   - 适用于 CONTINUATION/REENTRY，不优先改出场。
   - 拒绝 LiquidityVoid_Bull、突破后快速回 range、retest 跌破 raw zone、1–3bar reclaim、3bar 内无跟随。
   - PRIMARY_SETUP 胜率低时可降级观察池而非直接交易。

3. **REENTRY 专项（V63 类）**
   - REENTRY 不应第一次 retest 就进，必须等待二次确认。
   - 实测更稳定组合：`FVG_Bull + BOS_Bull + trend_score>=4 + BQ>=55`。
   - OB reentry、弱 CHOCH/MSS reentry 容易是假二次入场，先拒绝或降级观察。
   - 如继续提升，加入 `range_atr<=5` 与 `body_ratio>=0.3` 过滤追涨末端/弱实体突破。

4. **CONTINUATION 专项（V64 类）**
   - continuation 中 OB 与 FVG 必须分开看，不能混成一桶。
   - OB continuation 往往显著高于 FVG continuation，可作为主直接交易源。
   - FVG continuation 要更严格：只保留强 BOS/MSS、高 BQ、强 trend；弱 FVG+BOS 容易贡献大量 SL。
   - BPR continuation 样本少/弱时直接剔除或观察。

5. **亏损逐笔复盘门禁（V65 类）**
   - 对剩余亏损先问五个问题：是否集中股票、日期、GAP_SL、共同入场前兆、是否需要市场过滤。
   - 若亏损不是股票/日期集中且 GAP_SL 占比低，说明主因不是个股/跳空，而是信号前兆。
   - 可持续门禁示例：CONTINUATION 只直接交易 OB；FVG continuation 降级观察；REENTRY 保留 FVG+BOS 强趋势但增加 `range_atr<=5`、`body_ratio>=0.3`。

## 验证标准
每版必须输出并验证：
- `vXX_trades.json`, `vXX_picks.json`, `vXX_report.json`, rejected/watch_only 明细。
- quality / provenance / sequence / sample-bias / closed-loop-90d / release-gate。
- 前端默认版本、summary、picks、backtest、kline_full、autopsy/closed-loop 同步。
- 交易字段完整：entry/exit date、signal type、zone/conf、entry price、SL/TP、exit_reason、PnL、hold bars、BQ/trend detail。

## 注意
- 用户偏好“胜率提升”时，也不能牺牲机制正确性；高胜率子集应注明样本缩减和生产适用边界。
- 几十笔高质量子集可作为门禁验证，但正式生产结论仍应尽量基于全市场/3年全股票回测。
- 不要把历史交易伪装成当前选股；picks 必须区分 active candidate / expired review / watch only。
