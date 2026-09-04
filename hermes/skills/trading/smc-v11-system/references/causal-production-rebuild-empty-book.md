# SMC 因果生产重建与空仓控制面

## 适用场景

用于以下一类任务：

- 历史策略指标很好，但当前全市场无法同源生成信号；
- 历史候选包、实时扫描器、前端 active picks 的语义混杂；
- 用户要求先完整设计，再逐步执行；
- 需要修复行情刷新 fail-open、版本隐式回退或“无票也要出票”；
- 路线图中的 baseline/survivor 与最新因果审计结果冲突。

## 第一原则：证据覆盖路线图

路线图是待验证假设，不是事实。每次继续任务前，必须直接读取最新 artifact 和生产文件，重新核对：

1. 历史优势是否通过因果审计；
2. 合法入场是否晚于所有参与筛选的确认 bar；
3. 当前候选是否来自最新原始全市场扫描，而非历史 trades/picks；
4. shadow survivor 是否真的大于 0；
5. 新本体是否已经做过一次冻结回放并被关闭。

若证据与旧计划冲突，必须明确纠正旧计划。例如：

- 历史策略入场早于 takeover 确认 → 降为研究档案，不能作为生产 baseline；
- 合法延迟入场后经济门禁失败 → 不得声称能“重建并继承历史优势”；
- survivor=0 → 只能作为负对照，不能占用 shadow challenger；
- 一次冻结本体回放失败 → 永久关闭，不做参数/窗口/SL/TP/持有期变体。

## 五层生产架构

```text
事务化行情 epoch
→ 无 outcome 的本体生成器
→ 独立语义 Oracle
→ 一次性冻结 T+1 回放
→ 当前全市场同源 scanner / BUY_VALID 控制面
```

### 1. 事务化行情 epoch

仅有聚合 `gate_pass` 不够。若 fetch 成功一只就直接覆盖生产 K 线，最终门禁失败时会留下混合日期缓存。

正确模式：

1. 所有股票先写 staging epoch；
2. 在 staging 上检查请求覆盖、统一最新交易日、价格对齐、日期回退、未来日期；
3. FAIL：删除 staging，旧生产缓存和 current manifest 不变；
4. PASS：生成不可变 manifest，再 promote 文件；
5. 所有文件完成后，最后原子提交 current manifest；
6. scanner 只接受 `COMMITTED` manifest；promotion 中断或 manifest 缺失必须 fail-closed。

验证必须包含故障注入：失败前后生产缓存 checksum 不变。

### 2. 本体生成器

- 输入只允许原始 K 线和事件时点之前可知字段；
- 输出 `tradable=false`、`buy_enabled=false`；
- 禁止 outcome、exit、PnL、MFE、MAE 等字段；
- 先冻结事件、POI、确认、eligible entry、SL、target 的定义；
- 每个 identity 必须保留完整索引：
  `source_event_idx → poi_idx → touch_idx → reclaim_idx → hold_idx → eligible_entry_idx`。

### 3. 独立语义 Oracle

不能让 generator 自证正确。独立实现应重新推导 swing、结构事件、POI 与生命周期，要求：

- identity set 100% 相等；
- mismatch=0；
- chronology failure=0；
- duplicate identity=0；
- 所有年份达到预先声明的支持量。

### 4. 一次性冻结 T+1 回放

- 在打开 outcomes 前声明唯一 entry/SL/target/exit/max-hold；
- `search_count=1`；
- 严格 A 股 T+1；
- gap-aware；同 bar TP/SL 冲突采用保守 SL；
- 同时检查 aggregate、每年和前后两个 chronological epoch；
- 失败后关闭该 ontology，禁止通过变体挽救。

### 5. 当前生产控制面

生产状态建议显式化：

```json
{
  "state": "EMPTY_BOOK",
  "production_strategy": null,
  "shadow_challenger": null,
  "buy_enabled": false,
  "active_buy_valid_count": 0,
  "forbidden_fallback": true
}
```

不得再根据“某报告文件存在”猜测 active version。registry 缺失、损坏、epoch 不一致或策略未晋级时一律 EMPTY_BOOK。

## BUY_VALID 合同

仅当以下条件全部成立才允许买入：

```text
DATA_EPOCH_VALID
AND STRATEGY_PROMOTED
AND CURRENT_RAW_SCANNER_SOURCE
AND SIGNAL_DATE == DATA_EPOCH_MARKET_DATE
AND SEMANTIC_ORACLE_PASS
AND CHRONOLOGY_PASS
AND ENTRY_AFTER_CONFIRMATION
AND STRICT_T1_CONTRACT
AND CURRENT_PRICE_ABOVE_INVALIDATION
AND EXECUTION_FIELDS_COMPLETE
AND ACTIVE_PICK_HAS_NO_OUTCOME_FIELDS
```

任何一项失败：丢弃或 WATCH_ONLY。禁止回退旧版本、历史 active 文件或研究候选。

## 单 shadow 槽位

- 同时最多一个 shadow challenger；
- 只有 generator + Oracle + frozen replay 全 PASS 才可占用；
- rejected lineage 只可标记 `NEGATIVE_CONTROL`；
- shadow 与 production 使用物理隔离的输出目录；
- shadow 永远 `buy_enabled=false`，直到独立 current-smoke 和 production promotion 完成。

## 新 SMC 本体研究纪律

真正不同的本体必须改变因果叙事，而不是修改阈值。

以下三个本体已经完成 outcome-free generator、独立 Oracle 和一次冻结 T+1 replay，且均未通过年度/epoch 晋级门禁，现已永久关闭：

- Supply-Failure Breaker；
- Target-First DOL；
- Protected-Swing Transfer。

不得重新研究它们的窗口、阈值、止损、目标或持有期变体。研究计划完成后，生产 registry 应设置 `next_ontology=null` 并保持 `EMPTY_BOOK`；只有出现一个因果叙事真正不同、预先声明的新 SMC 本体，才允许开启下一轮 generator → Oracle → 单次冻结 replay。

## 执行顺序

1. 只读审计真实状态；
2. 保存完整架构/任务计划；
3. 先修数据事务性和 fail-closed；
4. 建生产 registry，删除隐式版本回退；
5. 物理隔离被拒历史策略与实时源；
6. 每次只研究一个新本体；
7. PASS 后才构建当前全市场 shadow scanner；
8. 最后验收 API、前端、推送、ingest 和 T+1。

## 完成标准

完成不是“产出一只股票”，而是：

- 每个最新交易日可从 committed 全市场原始数据独立生成候选；
- 当前候选与历史 generator 同定义、同来源；
- 没有合法信号时所有生产面一致 EMPTY_BOOK；
- 不存在历史回退、fail-open、伪 BUY_VALID 或 shadow 买入；
- 每个生产信号可逐字段追溯到原始 K 线和门禁 artifact。
