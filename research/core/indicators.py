# -*- coding: utf-8 -*-
"""core/indicators.py —— 技术指标单一实现(R22, 第八轮审计 P1-7)。

审计 P1-7: "把 ADX 放进 core/indicators.py, 回测和生产只调用一个实现, 并用
同一组 golden fixtures 锁定边界" —— 本模块是 ADX 的唯一权威实现。

## 实现分叉的诚实记录(重要)
- **adx14_of(bars, i)** = Wilder 平滑 ADX(14), 生产(paper_sim EVENT 腿)在用,
  2026-09-12 修复(旧单窗 DX 系统性偏低, ADX>=20 门过严错杀边界股);
- **gen_v20f.py(冻结回测基线)** 仍用其内嵌 legacy 单窗 DX —— 冻结基线
  n=1639(±1) 依赖该口径, 改动=毁基线。分叉显式标注于 gen_v20f 头部, 待
  研究级重基线决策(重跑全事件回测+全测试链)后才统一。
- 任何新代码(回测/纸面/shadow)需要 ADX 时**只允许** import 本模块。

Golden fixtures(锁定边界): tests_audit_r8k.py
  - 常量序列 ADX=0(无方向运动);
  - 单调上升序列 ADX>0 且 PDI>MDI 结构正确;
  - 样本不足(<30 bars) → None;
  - 与 paper_sim 原实现逐位一致(单源迁移无损)。
"""
from __future__ import annotations


def adx14_of(bs, i):
    """标准 Wilder ADX(14) —— 生产唯一 ADX 实现(2026-09-12 修复版单源化)。

    旧实现返回单窗 DX(|PDI-MDI|/(PDI+MDI)), 不是 ADX(DX 的平滑均值) →
    系统性偏低(0.33/5.78/5.45 vs 标准 13.06/7.55/13.46), ADX>=20 拒绝门
    过严错杀边界股。新实现: Wilder 平滑 TR/+DM/-DM → PDI/MDI → DX →
    ADX(DX 的 14 期 Wilder 平滑)。"""
    n = 14
    need = n * 2 + 2
    if i < need:
        return None
    lo = max(1, i - 120)                 # warm-up 尽量长(<=120 bars, 递归平滑对 warm-up 敏感)
    trs, pdms, mdms = [], [], []
    for k in range(lo, i + 1):
        h, l, pc = bs[k]["h"], bs[k]["l"], bs[k - 1]["c"]
        up = h - bs[k - 1]["h"]
        dn = bs[k - 1]["l"] - l
        pdms.append(up if (up > dn and up > 0) else 0)
        mdms.append(dn if (dn > up and dn > 0) else 0)
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    # Wilder 首值 = 前 n 和, 之后迭代平滑
    if len(trs) < need:
        return None
    tr_s = sum(trs[:n]); pd_s = sum(pdms[:n]); md_s = sum(mdms[:n])
    dxs = []
    for k in range(n, len(trs)):
        tr_s = tr_s - tr_s / n + trs[k]
        pd_s = pd_s - pd_s / n + pdms[k]
        md_s = md_s - md_s / n + mdms[k]
        pdi = 100 * pd_s / tr_s if tr_s else 0
        mdi = 100 * md_s / tr_s if tr_s else 0
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0)
    if not dxs:
        return None
    return sum(dxs[-n:]) / n


ADX_IMPL_VERSION = "ADX14_WILDER_20260912"  # 结果记录用(审计 P1-6 cost_model_version 同型字段)
