# V91 Shadow Zone-Entry Scanner Lessons

日期：2026-06-13

用于把 V91 研究结论（zone_mid/zone_low 限价入场、RISK/HOLD_LAG 可恢复）落成 shadow scanner，并接入 V88 前端 picks 流，但不替换 V88 生产回测基线。

## 产物

- Scanner：`/root/.hermes/scripts/v25/v91_shadow_zone_entry_scanner.py`
- 测试：`/root/.hermes/scripts/v25/test_v91_shadow_zone_entry_scanner.py`
- 输出目录：`/root/.hermes/smc_opt_v91_shadow_zone_entry_scanner/`
  - `v91_active_picks.json`
  - `v91_all_contract_candidates.json`
  - `v91_shadow_scan_report.json`

## 核心结论

1. V91 是 shadow 层，不是 V88 生产替代层。
2. 最大改善来自 daily zone 内入场价格位置，不是当前 60min reclaim 追涨确认。
3. `orig_v85_entry` / 确认价入场是高 SL 的主要来源；优先测试 `zone_mid_limit` / `zone_low_limit`。
4. `risk_pct` 与 `hold_bars` 不能独立硬过滤；它们必须与入场位置绑定判断。此前被 V86 过滤的 `RISK`、`RISK+HOLD_LAG` 桶在 zone_mid 入场后可恢复为高质量候选。
5. 60min 当前更适合做死亡/取消过滤，不适合直接作为追涨入场条件。

## V91 scanner 字段合同

V91 active picks 必须输出并通过 0 缺失审计：

- 日期：`pick_date`, `join_date`, `pickDate`, `joinDate`, `selectDate`, `选股日期`, `加入日期`
- 引擎：`engine=V91_SHADOW_ZONE_ENTRY_SCANNER`, `contract_source=V91_SHADOW_DAILY_ZONE_MID_LOW_LIMIT_ENTRY`
- Zone：`zone`, `zone_type`, `zone_low`, `zone_high`
- 成本/波动：`cost_line`, `costLine`, `volatility`, `volatility_pct`, `volatilityPct`, `vol_class`, `volClass`
- 执行：`entry_price`, `sl`, `tp1`, `tp2`, `tp3`, `rr`
- V91 诊断：`v91_gate_reason`, `v91_entry_layer`, `v91_target_semantics`

## 前端接入模式

在 `smc_unified.py` 中只做 V88 picks 流 shadow 合并，不改 V88 trades/summary/backtest：

1. 增加 `V91_DIR = Path('/root/.hermes/smc_opt_v91_shadow_zone_entry_scanner')`
2. `_active_pick_mtime()` 监听 `v91_active_picks.json`
3. 增加 `_merge_v91_shadow_picks(raw_picks)`，将 V91 shadow rows 放在原 picks 前面，按 `symbol|pick_date/entry_date|engine|v91_entry_layer/entry_mode|entry_idx` 去重
4. `_refresh_cache()` 顺序：`_merge_v66_daily_picks` → `_merge_v90_daily_picks` → `_merge_v91_shadow_picks`
5. `get_version_picks('V88')` 同样合并 V91 shadow picks
6. `_api_live_prices()` 若要展示完整 V91 诊断字段，需要显式透传：`entry_price`, `selectDate`, `v91_gate_reason`, `v91_entry_layer`

## 重要坑：重启与旧进程

如果 `/api/picks` 已有 V91 rows，但 `/api/live-prices` 缺少新透传字段，优先检查 8890 是否仍由旧 `python3 smc_unified.py` 进程监听。代码改动不会自动热更新。需要重启 8890 后再验收。

验收时不要只看 `/api/picks`；必须同时检查 `/api/live-prices`，否则会出现 picks 字段完整但 live 表字段仍旧的假闭环。

## 验收命令

```bash
cd /root/.hermes/scripts/v25
python3 v91_shadow_zone_entry_scanner.py
python3 test_v91_shadow_zone_entry_scanner.py
python3 -m py_compile v91_shadow_zone_entry_scanner.py test_v91_shadow_zone_entry_scanner.py ../smc_unified.py
```

## 本轮扫描基线

| 指标 | 结果 |
|---|---:|
| 扫描股票 | 4655 |
| 最新行情日 | 20260612 |
| 全部 V91 合同候选 | 12,713 |
| 近45bar 活跃候选 | 559 |
| PASS 活跃候选 | 28 |
| RISK 活跃候选 | 531 |
| 字段缺失 | 0 |
| T+1 违规 | 0 |

## API 验收目标

| API | 目标 |
|---|---|
| `/api/picks` | V88 + V90 + V91 合并显示，V91 字段缺失 0 |
| `/api/live-prices` | V91 rows 中 `selectDate/entry_price/zone/成本线/波动/sl/tp1/rr` 全部非空 |
| `/monitor` | 可见 V91 shadow rows |
| `/live` | 可见 V91 shadow rows |
| `/api/summary` | 仍以 V88 生产基线为准，不被 V91 shadow 改写 |
