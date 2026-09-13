# -*- coding: utf-8 -*-
"""core/cost_model.py —— CostModel 单点描述（R28, 第八轮审计 P1-6）。

审计 P1-6: "把成本模型抽象为 CostModel, 明确费率是单边还是双边; 买入、
卖出分别应用滑点和费用; 所有结果记录 cost_model_version; 增加平价
round-trip 必须为负成本的黄金测试。"

## 本模块的诚实定位: 描述层单源, 不是行为变更
R28 是**纯等价重构**: 数值零变化(事件回测冻结基线 n=1639 依赖现有数值),
只把散落在 execution.py/config.py 的成本口径收敛为单点可审计描述:

  - FEE_PCT  = 0.20    **双边总费用**(%)—— simulate 一次扣减即完整语义;
  - SLIPPAGE = 0.001   **单边滑点**  —— 买入 fill_px×(1+s), 卖出 exit×(1−s);

## 各执行路径成本应用(现状锁定, 等价不变)
  | 路径        | 买入成本                     | 卖出成本                    |
  |------------|------------------------------|-----------------------------|
  | simulate   | ep 隐含(回测口径)             | gross−FEE(双边总, 一次扣)    |
  | try_fill   | px×(1+SLIP) 挂单价含滑       | —                           |
  | try_exit   | —                            | exit×(1−SLIP) 卖出价含滑    |

## 黄金测试(tests_audit_r8q)
  - 平价 round-trip: 同价进出 → net 为负(成本>0 必亏) —— 审计原文要求;
  - CostModel 描述与 config 值逐项一致(单源不漂移);
  - simulate/try_fill/try_exit 成本应用与描述一致(源码级)。

## 历史(DailyPortfolioEngine 双侧计费)
历史组合引擎(core/portfolio.py)在买卖两侧分别计费——独立研究路径, 与
simulate 的"双边总一次扣"是**不同计费体系**, 不互换不比较; 其数值不受
本模块影响(研究参数, 文档已写明语义分界)。
"""
from __future__ import annotations

import config as CFG

COST_MODEL_VERSION = "COST_V1_FEE_TOTAL_020_SLIP_SIDE_001"


def fee_pct_total() -> float:
    """双边总费用(%)——simulate 的 gross−FEE 一次扣减即完整双边语义。"""
    return float(CFG.FEE_PCT)


def slippage_side() -> float:
    """单边滑点——买入 +×, 卖出 −×(try_fill/try_exit 现行口径)。"""
    return float(CFG.SLIPPAGE)


def round_trip_cost_pct(entry_px: float, exit_px: float, qty: float = 1.0) -> dict:
    """平价 round-trip 黄金计算器(审计 P1-6 黄金测试的内核)。
    同价进出(entry_px==exit_px) → net 必为负(费用+双边滑点>0)。
    按生产三路径口径合成: 买入含 +s 滑, 卖出含 −s 滑, 双边总费用一次扣。"""
    buy_px = entry_px * (1 + slippage_side())
    sell_px = exit_px * (1 - slippage_side())
    gross_pct = (sell_px / buy_px - 1) * 100 if buy_px else 0.0
    net_pct = gross_pct - fee_pct_total()
    return {"buy_px": round(buy_px, 6), "sell_px": round(sell_px, 6),
            "gross_pct": round(gross_pct, 6), "net_pct": round(net_pct, 6),
            "fee_total_pct": fee_pct_total(),
            "slip_buy_pct": round(slippage_side() * 100, 4),
            "slip_sell_pct": round(slippage_side() * 100, 4),
            "cost_model_version": COST_MODEL_VERSION}


def describe() -> dict:
    """成本模型单点描述(可写进 run 状态/manifest 的 cost_model_version 块)。"""
    return {
        "cost_model_version": COST_MODEL_VERSION,
        "fee_pct": fee_pct_total(),
        "fee_basis": "TOTAL_BOTH_SIDES",     # 双边总, simulate 一次扣
        "slippage": slippage_side(),
        "slippage_basis": "PER_SIDE",          # 单边: 买+卖−
        "paths": {
            "simulate": "gross - FEE(双边总一次扣, 回测口径)",
            "try_fill": "fill_px × (1+SLIP) 买入含滑",
            "try_exit": "exit × (1−SLIP) 卖出含滑",
        },
    }