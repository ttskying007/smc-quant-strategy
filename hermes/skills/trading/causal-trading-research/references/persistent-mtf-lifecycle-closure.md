# 持续有效的多周期状态机：生命周期闭环

适用于周线→日线→60m 的纯 SMC chain。它补充“先生成 seed、再 Oracle、一次冻结回放”的研究流程：**上层状态必须在实际 entry 前持续有效**，否则完整链并不具备因果语义。

## 研究序列

1. 同源 OHLCV：raw 60m 精确聚合 daily；daily 聚合 weekly；异常 session 必须成为 segment boundary，禁止跨源补洞。
2. 两套独立 primitive：confirmed pivot、close-break、wick/reclaim sweep、event-anchored OB 必须按时间戳集合 exact differential，不只比较数量。
3. 结果盲 chain：冻结 W1→D1→D2→D3→D4→H1→H2→H3→H4→E identity 与每个终态；不读 entry 后 bar、收益或 exit 字段。
4. 独立 chain Oracle：完整 ready identity exact match 后，才允许一次严格 T+1 回放。

## 持续有效性

- **W1**：从 D1 至 E 的每根已完成 weekly bar 必须仍在 protected low 上方；失效即永久取消，后续下级事件不能复活旧 chain。
- **D-POI**：D3 至 E 任一已完成 daily close < D-OB low 即取消；在日线尚未完成时，任一 60m close < D-OB low 也要即时取消。
- **POI-contained takeover**：H3 事件锚定的 local OB 必须与 active daily OB 有价格交集；远离 daily POI 的 local bounce 不得被归因到该 POI。
- **单向 first touch**：second entry into daily POI before H2 is terminal；无时间窗放宽来让链拖延。
- **执行可行性**：H4 后的 next 60m open 是当时可见的实时订单条件。若 `open <= max(H2 raid low, daily POI low)`，取消订单；不要把开盘位于 stop 下方的情况伪装成有效 entry，也不要用未来收益做此决定。

## 冻结回放后的只读归因

冻结 replay 失败必须关闭旧 ontology。允许的后验审计只能检查 pre-entry 结构事实：W1/D-POI 是否已失效、entry 是否在结构 stop 上方、各状态延迟及 chain identity 完整性；不能读取 pnl/exit/target 来设计补救过滤。

若审计证明 lifecycle invariant 在实现中缺失，下一研究对象必须作为**新的、预注册 ontology**，从同源语义审计和结果盲 seeds 重启。不得把旧 identity 或旧 replay 表现好的年份/标的/目标距离迁入新对象。

## 验证

- canonical time key 统一 daily `YYYYMMDD` 与 intraday timestamp，避免字符串排序误判；
- 每个 initial seed 只有一个 terminal state；
- ready identity 去重数等于 ready 行数；
- independent identity SHA-256 一致；
- T+1 exit date 严格晚于 entry date；
- production 保持 EMPTY_BOOK，直到新 ontology 完整通过其单次冻结回放门槛。
