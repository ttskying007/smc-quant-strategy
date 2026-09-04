# V60→V61 出场层修复教训：结构止损卖早不能整体延迟

## 触发场景

用户要求针对：

- `SOLD_EARLY_BY_STRUCTURE_STOP`
- `LOW_90D_MFE_CAPTURE`
- `BAD_EXIT_LOST_BUT_90D_RECOVERED`
- `SL_HIT 后未来恢复`

做下一版 SMC 出场层修复时使用。

## 已验证结论

V60 的剩余问题中，`SOLD_EARLY_BY_STRUCTURE_STOP` 和 `LOW_90D_MFE_CAPTURE` 不能简单通过“延迟所有结构止损 / 放宽 runner”解决。

V61 实验显示：

1. 对 continuation/reentry 的结构止损全局延迟，整体表现变差。
2. continuation 的结构破位延迟大多为负贡献。
3. reentry 的局部高质量区间可小幅受益，但不足以改善整体版本。
4. 大量 `LOW_90D_MFE_CAPTURE` 实际来自 `SL_HIT/GAP_SL_HIT` 后未来恢复，这不是出场延迟问题，而是入场前假突破/失败回踩识别问题。
5. 因此，出场层修复应先做分桶验证，不应直接扩大持仓时间或整体放宽结构止损。

## V61 验证过但不能作为默认生产优于 V60 的结果

V61 保持 V60 入场 gate 不变，只对部分结构出场延迟：

- 不扩展 PRIMARY
- 不扩展 `SL_HIT/GAP_SL_HIT`
- 只尝试对部分 `REENTRY_SETUP` 的 `STRUCT_CONFIRM_BREAK/GRADED_STRUCT_BREAK` 做 runner 延迟确认

最终：

```json
{
  "V60": {
    "n": 4450,
    "WR": 65.69,
    "avg_pnl": 11.696,
    "avg_R": 2.833,
    "avg_90d_capture": 0.276
  },
  "V61": {
    "n": 4318,
    "WR": 64.36,
    "avg_pnl": 11.582,
    "avg_R": 2.811,
    "avg_90d_capture": 0.262
  }
}
```

虽然局部 `V61_REENTRY_RUNNER` 有收益：

```json
{
  "n": 240,
  "wr": 95.0,
  "avg_pnl": 21.645,
  "avg_delta": 0.541
}
```

但整体不优于 V60。

## 下次正确工作流

当用户说“结构止损卖早 / MFE 捕获不足 / 盈亏比低”时，不要先改出场参数。按这个顺序做：

1. 按 `exit_reason × setup_family × BQ区间 × trend_score × entry_mode` 分桶。
2. 把 `STRUCT_CONFIRM_BREAK/GRADED_STRUCT_BREAK` 和 `SL_HIT/GAP_SL_HIT` 分开处理。
3. 对结构止损，只允许先做局部 runner 实验，并要求：
   - 分桶 delta 为正；
   - 整体 WR/avgPnL/avgR/90D capture 不低于 baseline；
   - release gate 通过。
4. 对 `SL_HIT 后未来恢复`，不要延迟止损；应进入下一层“假突破/失败回踩二次门禁”：
   - break 后是否立刻 reclaim；
   - retest 是否只是刺穿、没有有效站稳；
   - zone 是否二次失效；
   - 入场后 1–3 bar 是否缺少跟随；
   - SL 是否被 max-risk cap 截得过近；
   - 是否应等待二次确认再入场。
5. 如果候选版本 release gate 通过但弱于 baseline，要明确标记为实验版，不要把它说成生产优于 baseline。

## 前端同步注意

候选版本接入前端后必须验证：

- `/api/summary`
- `/api/autopsy/closed-loop`
- `/api/picks`
- `/api/kline_full?symbol=...&tf=daily&ver=候选版本`
- `/backtest`

如果启动多个 `smc_unified.py`，可能出现旧进程占用 8890；验证 `ACTIVE_VERSION` 和返回文件路径，不要只看服务启动日志。
