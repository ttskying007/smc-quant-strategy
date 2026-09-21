# R61 交接 — Jensen Alpha 期望引擎 三线接入(2026-09-21)

## 用户指令
"在交易时增加 jev，联动和判断交易决策" → 对话确认 jev = **Jensen's Alpha**；
口径选择： **PF-后验反推基准** + rank/gate/面板 **三线全接入**(gate 默认 shadow 只记录不拦截)。

## 交付物

| 件 | 路径 | 说明 |
|---|---|---|
| Alpha 引擎(单源) | `research/core/alpha.py` | `alpha_expect(chain, stage)` 前向期望 α；`alpha_realized` 后验 α |
| 基准生成器 | `research/gen_alpha_benchmark.py` | 从 combo_v22_trades.csv 切桶落盘 |
| 基准表 | `research/alpha_benchmark.json` | 9 桶 trend×retrace，1524 EVENT 腿 |
| 生产接线 | `research/paper_sim.py` | `_alpha_of()` 软失败助手；EVENT+CONT 挂单带 alpha_expect/bucket 4 字段；漏斗加 alpha_shadow_low |
| 前端 | `hermes/scripts/smc_unified.py` | /kline API smc_chain 附 α；链面板加"期望 Alpha (Jα)"行 |

## 口径(纪律)
- **基准 = PF 后验反推**: 冻结窗(至 2026-09-18)1524 EVENT 腿按 (trend_state, retrace_state) 条件桶算均值；
  候选 α_expect = 命中桶均值 − 全局均值(3.787%，已含 0.20% 费的净口径)
- **1日滞后**: 交易决策只用上一数据周期产出的基准表，无前视
- **软失败**: 无表/空链/trend=none → None, 绝不阻断选股(与 chain 同模式)
- **桶逐级退化**: `trend|retrace|stage` → `trend|retrace|*` → `trend|*|*` → `*|*|*`, 每级 n≥10
- **stage 维暂走阶退化**: 腿级 CSV 无 stage 列(生产 stage 在 gate 层), 三级桶全部落到 `|*|`; 待未来加入腿级 stage 列即可无缝分桶

## 基准实况(冻结窗)
| 桶 | n | avg | WR | α |
|---|---:|---:|---:|---:|
| down\|no_retrace | 314 | +5.67% | 74.8% | **+1.88** |
| down\|retrace_ok | 485 | +4.81% | 61.6% | +1.03 |
| down\|retrace_fail | 391 | +3.14% | 68.8% | −0.64 |
| up 系合计 | 334 | +1.28% | 58.1% | **−2.50** |

与 R58 正交性结论互相印证(up 系拖累组合)。**BSL 收割之前的新上市事件(down|no_retrace)期望值最高**。

## 三线现状
1. **rank 分量**: ledger 腿带 `alpha_expect / alpha_bucket / alpha_bucket_n / alpha_global_avg`(只记录)
2. **gate**: `CFG.ALPHA_SHADOW_MIN`(默认 −1.0)；shadow 模式 → `alpha_shadow_low` 计数进 selection_funnel, 不拦截
3. **面板**: /kline 信号链表多了"期望 Alpha (Jα)"行(正绿/负红, 显示桶与全局均值)

## 升级路径(尚未做，需下季数据)
- shadow 数据积累 ≥20 决策日后： 核对 alpha_shadow_low 腿的后续表现 vs 未拦截腿
- 核对通过 → `ALPHA_GATE_MODE='enforce'` 启用真拦截(届时必须预注册， 不冻结基线)
- 腿级 stage 列落 CSV → 三级桶生效(更细粒度 α)

## 验证
- 228 断言审计全绿
- 688326 实测: trend=down retrace_fail → α=−0.65 桶 n=391
- 空链/无表软失败为 None 的边例已测
- git: `21fb65f`(R61 主) + `ceb67c6`(R61b 蜡烛 ECharts 索引合并修复)

## 关联
- R60b `003004_SZ.SZ` 归一化 / R60c 页面加载自启动 / R61b series id 修复——三个前端修复同日交付
- 前端验证方式: Edge headless `--screenshot` 实拍(本轮新工具化手段)
