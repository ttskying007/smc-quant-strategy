# V297-V298 60m 同源 ACC→MAN→DIS 生命周期生成器闭环

## 触发场景

V296 证明 second60 persistence + lifecycle gate 可以把近端弱月改善到 122笔 / WR72.95 / Avg+3.14，但样本小且只是在 V293/V294 659行上做过滤。下一步需要验证：真正同源的 60m `Accumulation → Manipulation → Distribution` 生成器，是否能替代“日线 zone + 60m overlay”。

## 审计范围

- V297 脚本：`/root/.hermes/scripts/v25/v297_intraday_acc_man_dis_generator.py`
- V297 结果：`/root/.hermes/smc_audit/v297_intraday_acc_man_dis_latest.json`
- V298 脚本：`/root/.hermes/scripts/v25/v298_v297_entry60_persistence_overlay.py`
- V298 结果：`/root/.hermes/smc_audit/v298_v297_entry60_persistence_latest.json`
- 数据：4553个本地 60m 文件，4552只股票实际扫描；本地 60m 覆盖主要为 2025-11 到 2026-05。
- 写入：no-write；不写 production/frontend/watchlist。
- T+1：V297 / V298 均为 0 违规。

## V297 方法

使用同一只股票的 60m K线直接生成完整生命周期：

```text
ACC: 8/12/16/20 根60m窄幅蓄势
MAN: 1-3根内向下刺破 ACC low
RECLAIM: 1-3根内收回 ACC low
DIS/TAKEOVER: 1-4根内收盘突破 ACC high 且突破 reclaim high
EXECUTION: signal_date 下一交易日开盘买入，SL = min(man_low, acc_low)*0.992，日线 T+1 replay
```

注意：首次运行时曾把 `post_hold_min_pct` 放进 selector，这是 post-entry 字段，已立即剔除并重跑；最终 V297 top rules 不含 outcome/post-entry 字段。

## V297 结果

| 层级 | N | WR | Avg | 2025 | 2026 | 月度最低 | SL% | GAP_SL% | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| raw ACC→MAN→DIS | 26048 | 50.47 | +0.68 | 57.96 | 48.15 | 30.56 | 38.68 | 6.38 | 0 |
| best non-leak rule: `risk<=8 & sweep>=1 & takeover_delay<=2` | 906 | 55.52 | +0.97 | 74.02 | 47.20 | 31.49 | - | - | 0 |
| best min-month rule: `sweep>=1 & reclaim_delay<=2` | 3363 | 50.49 | +0.79 | 60.44 | 47.74 | 36.57 | - | - | 0 |

结论：同源 60m ACC→MAN→DIS 能给足供给，但质量仍不足；2026 和 202603/202605 明显退化。

## V298 方法

把 V297 生成的 `acc_lo/acc_hi` 映射为 entry-session zone：

```text
zone_low = acc_lo
zone_high = acc_hi
entry day 第 k 根60m：
  市场上涨占比 >= mup
  行业上涨占比 >= iup
  个股 low > zone_low 且 close > zone_high
  k>=2 时 close 不得低于 first60 close * 0.995
  entry = 第 k 根60m close
  日线 T+1 replay
```

## V298 结果

| Variant | N | WR | Avg | 2025 | 2026 | 月度最低 | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| k2_mup65_iup50_raw | 3589 | 55.28 | +1.44 | 64.31 | 52.30 | 33.51 | 0 |
| k2_mup65_iup50_nodecay | 3242 | 55.12 | +1.43 | 64.35 | 51.84 | 30.62 | 0 |
| k3_mup50_iup50_raw | 5459 | 53.54 | +1.37 | 60.79 | 50.37 | 35.47 | 0 |

结论：entry-session 市场/行业/个股 60m persistence 能把 raw V297 从 WR50.47/Avg0.68 提到 WR55.28/Avg1.44，但仍远低生产门槛，且月度最低只有 33.51。

## 机制结论

1. “同源 60m 生命周期生成”方向比日线固定参数更合理，但当前 60m ACC→MAN→DIS 定义仍过粗。
2. 2026 退化不是 T+1、交易量、或单一 market/industry 阈值问题；V297/V298 仍在 202603/202605 弱月崩。
3. 只靠 60m 的 `ACC range / sweep / reclaim / breakout` 仍像普通短线反弹，不足以证明庄家接管。
4. V296 的高质量来自更细的 lifecycle 过滤，但 V297/V298 证明：把 lifecycle 作为生成器主体后，若没有更低级别/更原生数据，质量仍会稀释。
5. 下一步不应继续调 V297 的窗口；应补充更原生 intraday 证据：15m/分笔/竞价/成交额持续性，或在 60m 内构造更严格的 `ACC压缩 → MAN放量刺破 → RECLAIM缩量不破 → DIS连续放量扩散`，并做 weak-month autopsy。

## 验证

Focused ad-hoc verification PASS：

```json
{
  "status": "PASS",
  "checked": [
    "compile/import V297/V298",
    "no-write contract",
    "T+1 invariants",
    "artifact row counts",
    "V297 selector field leak guard",
    "V298 variant contract"
  ],
  "v297_rows": 26048,
  "v298_best_rows": 3589,
  "v297_t1": 0,
  "v298_t1": 0
}
```

该验证不是完整 canonical test suite green。
