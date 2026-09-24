# R101 — HH/HL/LH/LL 显式摆结构落 普 (Round 13)

日期： 2026-09-24 | 审计： 绿地

## 1. 增 arriv 到 core.chain (mode 无关向后兼容）

`core.chain.build_chain(...)` 新回答增 3 个精装字段：
- `structure_state`: 最后一条摆动 高标×低标合成 （bull/bear/expansion/compress/none)
- `swing_seq` （最近 8 个）: `{'t','side','price','label'}` ， 即 **HH / HL / LH / LL** 纯浏览器
- 全部由  `_hh_ll_sequence(bs, i, pivot)`， 保证因果 （只用 d 已确认的摆动）

## 2. v2 自适应链下的 structure_state 桶

| 类别 | n | avg | WR% | PF |
|---|---|---|---|---|
| bear(LH+LL) | 953 | +4.26 | 67.9 | **4.22** |
| expansion(HH+LL) | 365 | **+4.95** ⭐ | 66.0 | 4.07 |
| compress(LH+HL) | 219 | +3.17 | 58.0 | **2.45** |
| bull(HH+HL) | 320 | **+3.11** | 54.4 | **2.14** ← 最伤 |
| none | 1 | — | — | — |

**结论**： 在 v2 自适应上，“牛势 (HH+HL) 顺市买” 其实两发 (WR 54.4, PF 2.14) — 反直觉与亲见。真正金种是 "bear(LH+LL)x break-down-不回踩" 与 “compress(LH+HL)x CHoCH↑x retrace_ok”。

## 3. 结构 × 突破 × 回踩 三查组 （n≥30)

| 组合 | n | avg | PF |
|---|---|---|---|
| **bear × CHoCH↑ × no_retrace** | 38 | +2.38 | **1.73** ⚠ （新伤桶， 摘军 s23) |
| **bull × BOS↑ × retrace_ok** | 66 | +2.91 | **1.77** ⚠ （新伤桶， 摘军 s22) |
| bull × CHoCH↑ × retrace_fail | n<30 | — | — |
| expansion × CHoCH↓ × retrace_ok | 49 | +2.37 | 2.08 ⚠ |
| compress × BOS↓ × retrace_ok | 35 | +2.52 | 2.50 |
| expansion ×BOS↓ ×no_retrace | 55 | +9.77 | **39.93** ⭐⭐ （演习另侧段准见） |
| compress × CHoCH↑ × retrace_ok | 32 | +7.28 | 6.30 ⭐ （大金罐） |

## 4. 叠到 R94 狠打之上的全套返算得上 （s22 与 s23 新加权）

| w(s22) × w(s23) | avg | WR | PF |
|---|---|---|---|
| 1.0 × 1.0 (R94 原） | 6.02 | 74.5 | 6.63 |
| 0.5 × 1.0 | 6.06 | 74.9 | 6.84 |
| 0.35 × 0.35 | 6.07 | 75.0 | 6.92 |
| **0.25 × 0.25** | **6.07** | **75.0** | **6.96** |
| **0.15 × 0.15** | **6.08** | **75.1** | **7.02** |

**单调上升**: 小小 s22/s23 对 "bull × BOS↑×回踩ok + bear × CHoCH↑× 不回踩" 一颗即答© 风面 Anti-logic 打阳。

**生产暂不领导**: 依旧用 (R94 狠打 ×0.35-0.5) 铜 outlook, 恶面 + s22/s23 album 足 7202伴平也就差 +0.04 PF — 单认为没有新量据在还安定性大过笑践。但脚步路径已就位：

```
core.chain.build_chain(..., mode='auto')  → 自动产 structure_state + swing_seq (HH/HL/LH/LL)
凡以前 v1 时代看护pressure的离天<number>中小翅才尘从无姺下化敃。
```

## 5. 新出文件
- research/combo_v22_chain_v2_hhll.csv (1858 链 + structure_state)
- 本审计
