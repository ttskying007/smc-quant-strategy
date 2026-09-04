# V90 Daily Full-Market Scanner + Frontend Merge

日期：2026-06-13

用于 V88 生产合同之后解决“最新行情日没有真实daily候选”的链路缺口。

## 产物

- 扫描脚本：`/root/.hermes/scripts/v25/v90_daily_full_market_scanner.py`
- 回归测试：`/root/.hermes/scripts/v25/test_v90_daily_full_market_scanner.py`
- 输出目录：`/root/.hermes/smc_opt_v90_daily_full_market_scanner/`
- 前端合并：`/root/.hermes/scripts/smc_unified.py` 在 `ACTIVE_VERSION == 'V88'` 时把 `v90_active_picks.json` 合并到 V88 picks 前面。
- 自动任务：`/root/.hermes/scripts/v25/smc_daily_ops.py::run_selector()` 改跑 V90 scanner；V88 回测基线不变。

## 关键原则

1. V90 是 daily scanner，不替换 V88 3年回测生产基线。
2. 复用 V85/V86 信号层与 V88 合同字段：`engine/pick_date/join_date/zone/cost_line/volatility/sl/tp/rr` 必须全量非空。
3. 不再把 V86 的 `liquidity_target` 作为目标，因为它来自未来bar语义；V90 使用 entry 前已知 BSL/prior high：
   - `known_bsl_target`
   - `known_bsl_idx < entry_idx`
   - `v90_target_semantics = PRE_ENTRY_KNOWN_BSL_OR_FIXED_RR_NO_FUTURE_LIQUIDITY_TARGET`
   - 原未来字段只保留在 `liquidity_target_original_future_v86` 供审计。
4. RECOVERY 不直接全盘否决，先拆 `v90_recovery_substate`：
   - `RECOVERY_CONFIRMED_FAST_RECLAIM`
   - `RECOVERY_STABLE_HIGHER_LOW`
   - `RECOVERY_WEAK_LOWER_LOW_OR_FAILED_HIGH`
5. 前端合并只影响选股/实时候选展示，不改变 V88 trades/summary/backtest。

## 验收命令

```bash
cd /root/.hermes/scripts/v25
python3 v90_daily_full_market_scanner.py
python3 -m py_compile v90_daily_full_market_scanner.py test_v90_daily_full_market_scanner.py ../smc_unified.py smc_daily_ops.py
python3 - <<'PY'
import test_v90_daily_full_market_scanner as t
for name in sorted(n for n in dir(t) if n.startswith('test_')):
    getattr(t,name)()
print('v90 tests PASS')
PY
```

## 当前验收结果

- 扫描全市场：4655只
- 最新行情日：20260612
- V90全部合同候选：773
- V90近45bar活候选：34
- 前端 `/api/picks`：552行，其中 V90=34
- 前端 `/api/live-prices`：11行，其中 V90=6
- `pick_date/join_date/engine/zone/cost_line/volatility/vol_class`：0空值
- T+1 pick→join 同日违规：0
- known BSL 目标覆盖：100%

## 注意

若未来要把 V90 提升为正式生产版本，必须另做3年全量回测/出场复盘门禁。当前只是 daily scanner + 前端实时候选补齐层。