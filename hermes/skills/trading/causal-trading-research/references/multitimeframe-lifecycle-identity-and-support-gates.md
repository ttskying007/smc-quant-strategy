# 多周期 SMC 生命周期、identity 与支持门禁

适用于周线→日线→60m 等多周期、结果盲状态机研究。

## 1. identity 一致不等于状态机正确

独立 generator/oracle 只有在**完整结构对象 identity**精确一致时才可授权后续步骤。identity 不能只写 event time；若同一根 bar 可对应多个 liquidity pool，必须含 pool 的 pivot time（必要时也含价格），否则不同对象会伪装成同一信号。

不要依赖 set/dict 的同时间遍历顺序：它不是交易语义。对“同一 sweep bar raid 多个已确认、未消耗 pivot”的情形，在预注册中二选一：

- 每个被 raid 的 pivot 都是独立 chain，identity 明确包含 pivot；或
- 明确定义唯一 canonical pool（例如 pivot time 最近的仍未消耗 pool）。

实现两侧必须使用同一条预注册规则。先用一个多-pool fixture 验证两实现选择相同 pivot，再跑全市场 identity compare。

## 2. 生命周期 hard cancel 要维护到 entry

`W1 → D1 → D2 → D3 → D4 → H1 → H2 → H3 → H4 → E` 不是只在进入下一状态时检查一次。每项硬失效都应持续检查到实际 next-open：

- W1 protected low：每个已完成周线 close；
- D1 sweep low：D2 之后每个已完成日线 close；
- 日线 POI：D4 后每个日线 close，及 H1 后每个 60m close；
- E：H4 hold 后下一根 60m open 是实时订单可行性判断；若 open 不在预先定义的结构止损一侧，取消，不能把无法建立的多头仓位送入 replay。

这些检查只读取 entry 前 bar，是因果状态转换，不是根据回放收益删选。

## 3. identity compare 后仍须先做支持门禁

在任何冻结回放**之前**，对完整 exact-match identity universe 检查预注册的最低支持量（例如总 unique identities ≥1,000，及可用年度的最低覆盖）。

- 样本不足：关闭该本体，禁止回放；回放不会创造独立支持。
- 不得通过标的、年份、月份、pool、目标、止损或收益子集补足样本。
- exact identity match 仅证明定义可复现，不证明样本支持或经济性。

## 4. 推荐顺序

`预注册结构对象唯一性与持续失效 → outcome-blind seeds → independent primitive/state oracle → exact full identity compare → outcome-blind support gate → one frozen strict-T+1 replay → independent metrics audit → close or production pre-audit`。
