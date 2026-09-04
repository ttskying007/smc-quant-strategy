# V26 每日选股 cron 运维补充

## 适用场景

用户要求执行“V26每日选股任务”或类似每日扫描/前端健康检查/输出今日 top 信号的任务时使用。

## 标准步骤

1. 运行扫描：
   ```bash
   cd /root/.hermes && python3 scripts/v25/daily_scan.py
   ```
2. 记录 stdout 中的关键值：
   - `New picks: ...`：本轮相对既有 latest 的新增候选数。
   - `Today (YYYYMMDD): ... signals`：脚本基于本轮 `new_picks` 计算的原始今日信号数。
3. 检查前端端口：
   ```bash
   ss -tlnp | grep 8890 || true
   ```
4. 如果无监听，重启 SMC 前端：
   ```bash
   cd /root/.hermes/scripts && python3 smc_unified.py
   ```
   使用后台进程方式启动长驻服务，并再次运行 `ss -tlnp | grep 8890` 验证。
5. 读取 `/root/.hermes/smc_opt_v25/v26_picks.json` 汇总前端实际 picks：
   - `latest_date = max(entry_date)`
   - `today_count = count(entry_date == latest_date)`
   - top 信号从 `today` 列表排序，优先 `score`，再用质量字段，报告 `symbol/regime/conf_type/entry_price/sl_pct/tp/ctx_seq`。

## 关键坑点

- `daily_scan.py` 写文件时会按 `symbol` 只保留最新一条：`sym_best[symbol] = latest pick`。因此 stdout 的 `Today (...) signals` 是原始本轮信号数，picks 文件中的今日数量是前端实际去重后数量，两者可能不同。
- 日报不要只报其中一个数字；建议写清：
  - “脚本输出今日信号” = stdout `Today (...)`
  - “前端实际 picks 今日数量” = JSON 文件内 latest_date 计数
- 如果端口初次检查为空但随后已有其他 watchdog/进程拉起，也要以最终 `ss` 验证为准，不要声称启动的后台 pid 就是最终监听 pid。
