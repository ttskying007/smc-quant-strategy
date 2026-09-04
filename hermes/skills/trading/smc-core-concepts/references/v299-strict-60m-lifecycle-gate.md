# V299 strict 60m lifecycle gate

## 触发场景

V297/V298 证明同源 60m `ACC→MAN→DIS` 供给充足，但 raw 和 entry-session persistence 仍在 202603/202605 弱月崩。用户要求继续围绕“按时间顺序、参数自适应、大小周期、股票DNA/庄家生命周期”持续迭代。

## 审计范围

- 脚本：`/root/.hermes/scripts/v25/v299_strict_60m_lifecycle_gate.py`
- 结果：`/root/.hermes/smc_audit/v299_strict_60m_lifecycle_latest.json`
- 明细：`/root/.hermes/smc_audit/v299_strict_60m_lifecycle_no_write_20260703_141214/v299_rows.csv`
- 数据：本地 60m + daily K线，覆盖主要为 2025-2026 近端窗口。
- 写入：no-write，不写 production/frontend/watchlist。
- T+1：0 违规。

## 方法

在 V297 同源 60m 生命周期基础上补更严格的操盘生命周期字段：

```text
ACC: 8/12/16/20 根 60m 蓄势，记录 range 与 quiet volume
MAN: 向下刺破 ACC low，记录 sweep_pct 与 MAN volume / ACC volume
RECLAIM: 收回 ACC low，记录 reclaim volume / MAN volume
DIS: 收盘突破 ACC high，记录 DIS volume / ACC volume
HOLD: 要求 1/2/3 根 60m 连续站上 ACC high，signal_date = 最后一根确认bar
EXECUTION: 下一日开盘买入，daily T+1 replay
```

测试的非泄漏字段包括：`acc_range_pct`, `vol_quiet`, `sweep_pct`, `man_vol_ratio`, `reclaim_vol_ratio`, `dis_vol_ratio`, `hold_req`, `no_deep_rebreak`, `takeover_delay`, `risk_pct`, `close_extension_pct`。不使用 `pnl/reason/exit/post_*` 等结果字段作为 selector。

## 结果

| 层级 | N | WR | Avg | 2025 WR | 2026 WR | 月度最低 | T+1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| raw strict-feature rows | 65,387 | 50.69 | +0.73 | 57.89 | 48.50 | 30.63 | 0 |
| best min-month rule: `sweep>=2 & man_vol>=1.6 & close_ext>=1.0` | 639 | 44.91 | +0.57 | 43.12 | 45.28 | 40.23 | 0 |
| high-WR pocket: `man_vol>=1.6 & risk<=6 & close_ext>=1.0` | 1,090 | 54.31 | +0.59 | 66.52 | 51.15 | 36.84 | 0 |
| broad high-WR pocket: `risk<=6 & close_ext>=1.0` | 8,400 | 53.56 | +0.65 | 58.95 | 51.05 | 35.05 | 0 |

## 机制结论

1. 60m 内构造更严格的 `ACC压缩→MAN放量刺破→RECLAIM→DIS放量扩散→多bar站稳` 没有救回弱月，甚至按 min-month 排序的最稳规则总 WR 只有 44.91%。
2. `MAN_VOL>=1.6`、`DIS_VOL>=1.6`、`hold>=2/3` 这类“看起来更像庄家接管”的条件没有形成稳定提升；部分高WR口袋主要来自 `risk<=6 + close_ext>=1`，仍只是更好的风险/突破幅度口袋，不是 lifecycle 质变。
3. 弱月亏损仍集中在 `RISK>=8`、中/宽蓄势、深扫、放量刺破/放量突破组合，说明 60m OHLCV 粗粒度无法区分真接管和假放量诱多。
4. V299 关闭“继续在现有 60m K线内部调 lifecycle 阈值”的方向；下一步若继续该目标，必须引入更原生数据或更短周期：15m、分笔/盘口、竞价、成交额持续性、真实板块资金扩散。否则继续调 `acc_len/sweep/man_vol/dis_vol/hold_req` 只是在同一失败面上反复搜索。

## 验证

Focused ad-hoc verification PASS：

```json
{
  "status": "PASS",
  "checked": [
    "helper boundaries",
    "artifact counts + T+1/no-write contract",
    "top-rule leakage guard",
    "best-rule materialization"
  ],
  "rows": 65387,
  "symbols": 4081,
  "t1": 0,
  "best_n": 639
}
```

该验证不是完整 canonical test suite green。
