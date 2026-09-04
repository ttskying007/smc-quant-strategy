# V47.2 并行前端集成与同步验证教训

## 触发场景
当新的 SMC 候选版本已经产出 trades/picks/report，但用户要求“先并行验证，不覆盖当前默认生产版本”时使用。典型目标：新增 `/api/summary`、`/api/picks`、`/api/kline_full` 支持，并让 K 线页面可切换新版本。

## 核心原则
1. **默认版本不动**：保留 `ACTIVE_VERSION` 和 production pick file，不把 candidate 直接切成默认。
2. **版本读取隔离**：新增 `get_version_trades(version)` / `get_version_picks(version)` 这类旁路读取函数，避免把 candidate 数据混入全局 `_TRADES_CACHE/_PICKS_CACHE`。
3. **所有入口都带 `ver`**：`summary`、`picks`、`picks/contract`、`rejects`、`kline_full` 必须同时接受 `?ver=Vxx`，否则前端会出现“下拉切了版本但某个表仍显示旧版本”的伪同步。
4. **K线历史交易映射要单独补**：`kline_full` 通常有自己的 `ver_map` / `_ver_paths`，仅补 summary/picks 不够。必须确认 K 线 `trades` 样本里的 `engine` 是新版本，不是默认版本。
5. **wave_ref enrichment 只附加字段**：给 BOS/CHOCH/MSS 增加 `wave_ref_idx/date/label/price/distance` 和 `structure_layer`，不要覆盖原 Lux/Pine 的 pivot/currentLevel 语义。
6. **前端验证以端到端为准**：接口通过后还要浏览器切换版本并确认页面标题、下拉选项、K线交易记录、信号列表、选股/API 数据一致。

## 最小实现清单
- 添加候选目录常量：如 `V47_2_DIR = Path('/root/.hermes/smc_opt_v47_2_candidate')`。
- 在版本路径函数中增加：`trades`, `picks`, `metrics/report`, `rejects`, `script`, `engine_name`。
- 新增/扩展：
  - `/api/summary?ver=V47_2`
  - `/api/picks?ver=V47_2`
  - `/api/picks/contract?ver=V47_2`
  - `/api/picks/rejects?ver=V47_2`
  - `/api/kline_full?symbol=...&tf=daily&ver=V47_2`
- K线页面 `<select id="ver">` 增加候选版本 option，但保持默认 option 仍为生产版本。
- 重启服务后先跑 API contract，再用浏览器实际切换版本。

## 验证要点
- `/api/summary?ver=候选版本` 返回 `version` 为候选版本，统计数与候选 trades 文件一致。
- `/api/picks?ver=候选版本` 返回候选 active picks，且 `pick_scope` / `is_active_pick` contract 正确。
- `/api/kline_full?...&ver=候选版本`：
  - `version` 为候选版本。
  - `trades[0].engine` 为候选引擎名，不是当前默认引擎。
  - `signal_count`、`swing_count` 非空。
  - BOS/CHOCH/MSS 中大多数有 `wave_ref_*` 字段。
- 浏览器 K线页：标题显示候选版本，版本下拉选中候选版本，交易记录来自候选版本。
- 生产默认页仍显示当前默认版本，避免未验收候选版本误上线。

## 常见坑
- **只改了 summary/picks，忘了 kline_full 的历史交易 ver_map**：表现为标题切到新版本，但交易记录 `engine` 还是旧版本。
- **全局缓存污染**：把候选 trades 塞进 ACTIVE_VERSION 缓存后，会导致 V46/V47 互相串数据。
- **wave_swings 结构可能是 dict 而不是 list**：要兼容 `{'highs': [...], 'lows': [...]}` 和 list 两种形态。
- **浏览器截图工具失败不等于页面失败**：若视觉分析失败，仍应保存截图路径并用 accessibility snapshot / API 数据继续验证。
