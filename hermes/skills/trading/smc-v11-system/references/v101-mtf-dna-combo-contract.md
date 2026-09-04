# V101 MTF/DNA 多组合合同层与 BOS 候选池闭环

## 触发场景

用户要求在 SMC 生产前端已经稳定后继续推进：
- 保持当前高质量反转生产池不变
- 将 `BOS_CONTINUATION` / 多组合合同单独沉淀为候选池
- 不允许把未独立验证的 BOS 延续信号混入反转 A 生产池
- 同时要求 `/api/picks`、`/api/live-prices`、`ops_latest.json` 字段合同继续为 0 缺失

## 核心原则

1. **V101 是合同层，不是底层信号重写**
   - 不改 V100/V98 的信号、入场、出场数学
   - 只在 `v101_mtf_dna_combo_contract.py` 上追加合同字段、候选门禁和输出文件

2. **生产池和候选池必须分离**
   - `PRODUCTION_COMBO_WHITELIST` 只保留已验证生产组合，例如：
     `REVERSAL_SSL_CHOCH_DEMAND_OB_STRUCTURAL_5R`
   - 新组合使用独立 `CANDIDATE_COMBO_WHITELIST`
   - 候选字段用：
     - `combo_candidate_whitelist_v101`
     - `combo_candidate_eligible_v101`
     - `combo_candidate_gate_reason_v101`
   - 不要把候选组合写入 `production_eligible_v101=True`

3. **BOS_CONTINUATION 候选门禁应使用预筛字段，不使用事后收益字段**
   典型候选门禁：
   - `combo_contract_key == CONTINUATION_BOS_PULLBACK_STRUCTURAL`
   - `mtf_trend_permission == MTF_LONG_ALLOWED`
   - `tp2_rr >= 5.0`
   - `tp3_rr >= 8.0`
   - `expected_tp2_net_pct >= 0.8`
   - `0 < risk_pct <= 1.2`

4. **报告和日报链路都要带候选统计**
   `v101_report.json` 建议增加：
   - `candidate_combo_whitelist`
   - `bos_continuation_candidate_total`
   - `bos_continuation_candidate_stats`
   - `combo_counts_candidate_whitelist`

   `smc_daily_ops.py` 的 `v101_contract_summary` 也要同步这些字段，避免每日任务执行后 `ops_latest.json` 看不到候选池。

5. **候选池单独输出文件**
   建议输出：
   - `/root/.hermes/smc_opt_v101_mtf_dna_combo_contract/v101_bos_continuation_candidates.json`

## 验证标准

必须同时验证三层：

### 1. 生成层

```bash
python3 -m py_compile /root/.hermes/scripts/v25/v101_mtf_dna_combo_contract.py /root/.hermes/scripts/v25/smc_daily_ops.py
python3 /root/.hermes/scripts/v25/v101_mtf_dna_combo_contract.py
```

检查：
- `production_total` 保持不变
- `combo_counts_production` 不包含 `CONTINUATION_BOS_PULLBACK_STRUCTURAL`
- `bos_continuation_candidate_total > 0`
- `v101_bos_continuation_candidates.json` 存在且字段完整

### 2. 日报层

```bash
python3 /root/.hermes/scripts/v25/smc_daily_ops.py
```

注意：该链路会顺序跑 V98 → V99 → V100 → V101，V98/V101 可能各耗时数分钟。不要误判为卡死；看子进程和输出文件 mtime 是否更新。

检查 `ops_latest.json`：
- `shadow_selector.returncode == 0`
- `v101_contract_summary.production_total` 正常
- `v101_contract_summary.bos_continuation_candidate_total` 正常
- `v101_contract_summary.combo_counts_candidate_whitelist` 正常
- `v101_contract_summary.field_missing_active` 总和为 0

### 3. 前端/API 层

回归检查：
- `/api/summary` 仍为 V101
- `/api/picks` 的 `pick_date/join_date/engine/zone/cost_line/volatility_pct` 缺失为 0
- `/api/live-prices` 的 `pickDate/joinDate/engine/zone/costLine/volatilityPct` 缺失为 0
- `/monitor` 和 `/live` 页面仍显示选股日期、加入日期、Zone、成本线、波动

## 重要坑

- 信号偏少/当前持仓只剩少数几只时，不要先放宽入场或信号；先审计底层候选→生产池→active 文件→前端可见窗口的压缩链路。详见 `references/v103-signal-scarcity-active-watchlist-audit.md`。
- `BOS_CONTINUATION` 全量候选可能很多，但如果 `v100_A=0`，不能直接进生产池；只能独立候选化。
- 候选池的胜率/收益可以报告，但不能作为生产混入理由；必须先有独立 SL/TP/MTF 合同验证。
- `combo_candidate_gate_reason_v101` 对非候选为空是正常的，不应放入全体字段缺失强制项；否则会把正常非候选误报为缺失。
- `gitnexus detect-changes` 在 `/root/.hermes/scripts` 非 git repo 下会失败；这不是代码失败。能跑影响分析时跑，索引未覆盖新脚本时要明确记录影响范围为单文件合同生成层。
