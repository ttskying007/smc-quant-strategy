# 2023–2026 同源多周期 Raw Cache 合同

## 触发条件

当要研究价格结构、量价吸收、Spring/Test、SOS/Backup、Selling Climax，或任何跨 15m/60m/日线/周线的本体时，先完成此缓存层；不要把近端分钟缓存当作历史回测数据。

## 必须的来源与口径

1. 日线、60m、15m 均使用同一来源的未复权可成交 OHLCV（Baostock `adjustflag=3`）。禁止把 QFQ 日线与 raw 分钟线混合用于结构、POI、SL、TP 或回放。
2. 周线不向另一来源请求；只由同源 raw 日线聚合：周开=首日开、周高/低=max/min、周收=末日收、量额=sum。
3. Provider 的分钟请求可能静默截断。15m 按自然季度分块，60m 按自然年分块；每块都需返回成功后再合并、按 timestamp 去重、原子写入 gzip JSON。
4. 缓存应逐证券可恢复：任何 daily/60m/15m 一项缺失或时段审计失败时，不写该证券的完整成功标记；重跑只补不完整证券。

## 覆盖验收（先于任何本体）

以同源 raw 日线交易日期作为每个证券的 expected days：

| 周期 | 每日合法时段 | 验收 |
|---|---|---|
| 60m | 10:30、11:30、14:00、15:00 | 每个 expected date 恰好 4 bars，时段集合完全相等 |
| 15m | 09:45 至 11:30、13:15 至 15:00 | 每个 expected date 恰好 16 bars，时段集合完全相等 |
| 日线 | raw OHLCV | 日期唯一、OHLC 合法、覆盖研究区间 |
| 周线 | raw daily aggregation | 周 OHLCV 与组成日线严格可重算 |

验证范围至少覆盖 2023、2024、2025、2026 每一年；单个证券的新上市起点不是缺失，但不得以 QFQ cache 的短窗口替代 raw 日期基准。

## 北交所边界

若同源历史分钟 provider 不支持 BJ，应将 BJ 证券显式 `SOURCE_QUARANTINED`，并在报告中单列数量和样本。不得把仅覆盖 SH/SZ 的缓存声称为全市场；也不得用只有近端历史的替代源补齐后宣称 2023–2026 完整。

## 研究治理

数据缓存本身不产生信号、交易、前端候选或生产写入。四周期完整性审计通过后，新的独立本体仍须依次经过：outcome-blind generator → independent raw-bar Oracle → frozen strict T+1 replay → 逐年/逐月/逐笔审计。缓存完成不等于策略晋级。

## 实现参考

本次实现：`/root/.hermes/scripts/v25/v536_build_multitf_raw_cache.py`。
- SH/SZ raw cache root: `/root/.hermes/intraday_cache/raw_multitf_v536/{daily,weekly,m60,m15}`
- 支持 Baostock session 失效后登录并重试同一请求；为了避免 shared-session 并发不稳定，默认串行构建。
- `gzip` + 临时文件替换保证原子落盘；现有完整证券可跳过。
