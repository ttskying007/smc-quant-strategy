# V48 出场修复候选：在不改信号的前提下修 RR/卖早

## 触发场景

当 SMC 系统出现：

- 胜率尚可，但平均盈亏比/avgPnL 偏低；
- 逐笔复盘显示信号后 MFE 空间明显大于实际收益；
- `sold_early_rate` 高、runner 吃肉不足；
- 用户要求“保证胜率和盈亏比”，不能用牺牲胜率换 RR；
- 当前信号合同已经通过，不能先动 OB/FVG/组合定义。

应优先做“出场分诊 + runner 修复候选”，不要直接改信号定义或表面调参。

## 本次可复用结论

V47.2 当前生产信号合同通过后，RR 偏低的深层原因不是 OB/FVG 全错，而是出场吃不到趋势：

- V47.2：334 笔，WR 87.43%，SL 12.28%，avgPnL 9.642%，avgWin 11.739%。
- 逐笔复盘显示：avg MFE 约 21%，实际捕获率低，sold_early_rate 约 83%。
- ZONE_MID_EXECUTABLE 是较弱入场桶，但本轮不应先动信号/入场；先隔离出场问题。

V48 候选保持 V47.2 的同一批交易和信号，只重新模拟出场：

```text
max_hold = 240
tp1_frac = 0.10
tp2_frac = 0.10
trail_trigger_r = 12.0
trail_lock_r = 1.2
breakeven_r = 1.0
breakeven_bars = 3
```

结果：

```text
V47.2: WR 87.43 / SL 12.28 / avgPnL 9.642 / totalPnL 3220.33
V48:   WR 89.22 / SL  9.58 / avgPnL 12.179 / totalPnL 4067.79
```

这说明出场修复可以同时提高胜率和 avgPnL，不必牺牲胜率换 RR。

## 必须做的验证

每次生成出场修复候选后，必须逐笔检查：

1. `entry_index` / `exit_index` 合法，且 `exit_index >= entry_index`。
2. `entry_price` 在入场 K 线 high/low 内。
3. 每个 `exit_legs[]` 的成交价在对应 K 线 high/low 内。
4. `exit_weight_sum == 1`。
5. `pnl_pct == sum(exit_leg.weight * ((exit_leg.price - entry_price) / entry_price * 100))`。
6. `exit_price_effective == entry_price * (1 + pnl_pct/100)`。
7. OB/FVG 信号合同仍通过：OB 需有 wave-turn provenance；FVG 需匹配 Pine-like gap；entry 不得早于 zone。

## 关键坑：跳空越过 TP 的成交价

发现 32 个 `LEG_PRICE_OUTSIDE` 后定位到：

```text
如果股票跳空高开越过 TP1/TP2，不能仍按 TP 目标价成交；
因为当日 low 可能已经高于 TP，导致 exit leg price 不在当日 K 线范围内。
```

修复：

```python
if high >= tp1:
    exec_price = max(tp1, open_price) if open_price > tp1 else tp1
    reason = 'TP1_GAP_HIT' if open_price > tp1 else 'TP1_HIT'

if high >= tp2:
    exec_price = max(tp2, open_price) if open_price > tp2 else tp2
    reason = 'TP2_GAP_HIT' if open_price > tp2 else 'TP2_HIT'
```

修复后逐笔验证应达到：

```json
{
  "missing": {},
  "p0_fail_counts": {},
  "pass": true
}
```

## 前端同步规则

V48 这类候选不能直接覆盖 production。必须先并行接入：

- `/api/summary?ver=V48`
- `/api/picks?ver=V48`
- `/api/picks/contract?ver=V48`
- `/api/kline_full?symbol=...&ver=V48`
- K线版本下拉增加 V48
- 回测页、选股页、分析页、复盘页均支持 V48

浏览器验证通过后，才可以考虑提升为默认 `ACTIVE_VERSION`。

## 文件参考

本轮实现文件：

```text
/root/.hermes/scripts/v25/v48_exit_repair.py
/root/.hermes/smc_opt_v48_exit_candidate/v48_trades.json
/root/.hermes/smc_opt_v48_exit_candidate/v48_picks.json
/root/.hermes/smc_opt_v48_exit_candidate/v48_report.json
/root/.hermes/smc_opt_v48_exit_candidate/v48_trade_autopsy.json
/root/.hermes/smc_audit/v48_exit_repair_validation.json
/root/.hermes/smc_audit/v48_signal_contract_validation.json
```

这些是会话产物路径，不应作为永久真理；未来使用时以当前系统路径为准，但验证维度和跳空 TP 修复规则可复用。
