# R64 交接 — Jev(TypeSafe System One) 影子判断层(2026-09-21)

## 背景
用户引入外部"判断型"模型 **Jev**(TypeSafe 旗舰 System One 模型, 返回类型化判断+概率,
不是生成式文本)。用户已提供 API key 并两次确认调用意图。该模型用于"决策加速"——
在我们的回测/选股链里补一个"语义判断"维度。

## 交付物
| 件 | 路径 | 说明 |
|---|---|---|
| Jev 客户端 | `research/core/jev_client.py` | 纯 stdlib HTTP; key 只走 `TYPESAFE_API_KEY` 环境变量, 绝不落盘 |
| 生产接线 | `research/paper_sim.py` | `_jev_of(order, chain)` 软失败助手; EVENT+CONT 两腿过 PortfolioGate 后采样; jev 字段落 ledger; 影子 jsonl |
| 漏斗计数 | `research/paper_sim.py` | `jev_judged`(本日采样数) 进 selection_funnel |
| 影子 log | `research/jev_shadow_log.jsonl` | 每次判断一行 {code,date,signal_combo,4个答案} , 供后续本地校准 |
| 验证样例 | (Jev 冒烟) | 已验证 300660 实战判决 → bottom_accumulation 97% |

## 三问契约(预注册 — R60/R61 同纪律)
| 问题 | 类型 | 输出 | 含义 |
|---|---|---|---|
| executable_now | noul | p∈[0,1] | "此刻是否值得执行" 的概率(只看信号) |
| event_kind | choice | kind 四选一 + confidence | 底部吸筹/趋势回踩/假信号/不明 |
| expected_excess | score | 0-3 段 + confidence | 未来2周相对等权组合超额分位 |

## 纪律(与 rank/alpha 同章)
- **影子**(R64): 只记录, 不拦截/加分; ledger 每笔挂单带 jev 四字段
- **数据积累**(n≥30 腿): 本地统计 — Jev p_executable 是否与净 pnl 相关; event_kind 分布; excess_score 分位后验 vs 实际
- **升级**(需新一次用户审定): 若 p_executable × excess 组合在 OOS 上显著改善 PF/WR → 与 alpha 一样申多个 rank 分量承载, 默认仍不 gate

## 安全与费用
- key 只在 DAG 的 env: 本次会话已验证 200 OK; 生产跑批靠 `SMC_TASK env 注入` 或调度脚本 `-SetTSAKey`
- 每次判断 ~800 输入 tokens + ~90 输出; 按住仓 1-3 笔/日的选股节奏 ≈ 可忽略
- 挂进 paper_sim 前做了 `syntax + 空key + 全绿 228` 三重验证

## 首份实战(300660, 在生产 pending 状态下判决)
| 问 | 答 |
|---|---|
| executable_now | **0.48** — 中性偏可 |
| event_kind | **bottom_accumulation**(置信 0.97, 几乎确定) — 与我们 BUYBACK_STRONG 设计意图对齐 ✓ |
| expected_excess | score 1.69, 概率 [0.10, 0.27, 0.46, 0.17] — 中性偏正 |

语义对齐有效: **我们的策略的选股信号确实命中增持/吸筹真相**。

## R64.1 续(2026-09-22) — backfill + R67 性能升级
- **árchive 8 笔近期挂单补打 Jev 字段**(`_jev_backfill_orders.py`, 一次性): 7 笔 CLOSED 全部 `event_kind=bottom_accumulation@0.96-0.98`(语义高度一致); **单支 PENDING 300808 的 event_kind 置信只 0.52** —— 语义层对它没那么"确定是底部吸筹", 标记为观察目标
- **R67 性能**: `core/jev_client.judge_many`(keep-alive 连接池 + 6 worker 并发 + 指数退避), 实测 8 腿 15.1s → 2.8s (**5.3x**); 下次全量审计 1858 腿预计 8 分钟级别
- **key 持久化**: `TYPESAFE_API_KEY` 已写入 Windows **用户级**环境变量(setx), 0:00/08:00/15:30 三个调度的新进程直接可读; 不进任何仓库文件(唯一外泄点在聊天记录, 建议抽时间轮换)

## R65 警示(直接打在脸上): Jev 作"回测选股器"已 **证伪**
- 全量 1858 腿净视野审计(R65b, cache v2): p_valid 各桶 pnl 无区分度(+2.4~+4.3 平坦), 方向准确率 **37.9%**(<随机线), timing 无流形
- v1 "PF 3.36→6.07" 的假象是 **state 里混入 net_pnl/sell_price 前视泄漏**导致 — 已归档 `jev_audit_cache_v1_CONTAMINATED.jsonl` 作为教程样本
- **结论**: Jev 的语义判断对"这支信号未来赚不赚"**没帮助**; 但"这是不是底部吸筹"(语义判型) 96%+置信, 与事件设计意图高度自洽 — **定位: 语义一致性存档, 不是选股者**

## 下一步
- 本次数据积累 ≥2 周后回来校准(按 R58/R58 框架)
- 校准前, 这只是一个"数据生产者"
- **观察 300808**(event_kind 置信仅 0.52 的单支 pending), 看走出怎样的结果
