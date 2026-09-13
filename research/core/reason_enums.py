# -*- coding: utf-8 -*-
"""core/reason_enums.py —— 第七轮审计 P1 清单#6: 订单/退出 reason 枚举统一(2026-09-13, R7)。

背景: R1/R2 已统一回测/纸面判定优先级(停牌/跌停→T+1→SL_GAP→SL/BE→TP1→TP2/TP3→TIME_STOP),
但 reason 字面量散落在 core/execution.py / paper_sim.py / core/setup_exit.py / core/portfolio.py,
无单一事实源 —— 新增 reason 或消费方拼错字符串都要靠人肉发现。
本模块是唯一权威枚举源; 字面量以各引擎实际产出为准(R2 锁定 + R7 全链实测补登),
**不改变任何运行时行为**, 只提供:
  1) 常量(供未来代码引用, 防拼写漂移)
  2) 各族冻结集合
  3) tests_reason_enums.py 用 freeze 集合做全链字面量校验(防新增未登记 reason)
"""

# ================= 1. 退出 reason(try_exit 快照 / simulate bar 循环) =================
EXIT_SUSPENDED = "SUSPENDED"          # 停牌(不可交易)
EXIT_SL_GAP = "SL_GAP"               # 开盘跳空穿 SL → 开盘价成交(含滑点)
EXIT_SL_HIT = "SL_HIT"               # 盘中触及 SL(或 BE 前的 SL)
EXIT_BE = "BE"                        # TP1 后保本位被击穿
EXIT_TP1 = "TP1"                      # 部分止盈(partial)
EXIT_TP2 = "TP2"                      # 全平止盈
EXIT_TP3 = "TP3"
EXIT_TIME_STOP = "TIME_STOP"          # 交易日 bar 计数持有期满(R1 起 CONT 统一)

EXIT_REASONS = frozenset({
    EXIT_SUSPENDED, EXIT_SL_GAP, EXIT_SL_HIT, EXIT_BE,
    EXIT_TP1, EXIT_TP2, EXIT_TP3, EXIT_TIME_STOP,
})

# ---- simulate()(bar 循环)专属 reason(gen_v20f/组合回测/paper_sim TP2 分支消费) ----
SIM_TP2_RUNNER = "TP2_RUNNER"          # TP2 全平(runner 路径; paper_sim 消费同一字面量)
SIM_TP3_RUNNER = "TP3_RUNNER"          # TP3 runner
SIM_TP_STRUCTURAL = "TP_STRUCTURAL"    # 结构位止盈(v20f 组合带)
SIM_SKIP_LIMIT_UP = "SKIP_LIMIT_UP"    # 一字涨停跳过(非真实交易)
SIM_BAD_ENTRY = "BAD_ENTRY"            # ep<sl 非法区间几何(防机械获利)
SIM_BAD_SIGNAL = "BAD_SIGNAL"          # sl>=entry 非法 Setup 拒绝(fail-closed)
SIM_REASONS = frozenset({SIM_TP2_RUNNER, SIM_TP3_RUNNER, SIM_TP_STRUCTURAL,
                         SIM_SKIP_LIMIT_UP, SIM_BAD_ENTRY, SIM_BAD_SIGNAL})

# ---- paper 账本专属退出语义(非撮合引擎, 纸面裁决/人工复核通道) ----
PAPER_EXIT_ADJUDICATE = "PAPER_ADJUDICATE"  # paper_adjudicate.py 纸面裁决退出(账本历史主族 n=58)
PAPER_EXIT_HOLD_EXIT = "HOLD_EXIT"          # 旧 CONT 自然日分支(R1 删除, 仅历史账本)
PAPER_EXITS = frozenset({PAPER_EXIT_ADJUDICATE, PAPER_EXIT_HOLD_EXIT})

# ---- 账本历史 exit_reason(旧 v20f 组合带, 不再产出但账本存续; reconcile.py 归一化对象) ----
LEDGER_LEGACY_EXITS = frozenset({"TP4_RUNNER", "TP_HIT"})

# ================= 2. setup_exit.py(Setup Engine V3 单源退出) =================
SE_STATUS_SL, SE_STATUS_TP, SE_STATUS_TIME, SE_STATUS_INVALIDATED, SE_STATUS_OPEN = (
    "SL", "TP", "TIME", "INVALIDATED", "OPEN")
SE_EXIT_SL_HIT = "SL_HIT"              # 同名复用 EXIT 族
SE_EXIT_TP_STRUCT = "TP_STRUCT"        # 3R 结构位止盈
SE_EXIT_TIME_STOP = "TIME_STOP"        # 同名复用
SE_EXIT_INVALIDATED = "INVALIDATED_BEFORE_FILL"  # fill 前破 invalid → Setup 作废
SE_EXIT_NOT_YET = "NOT_YET"            # 窗口未走完(open)
SE_STATUS = frozenset({SE_STATUS_SL, SE_STATUS_TP, SE_STATUS_TIME, SE_STATUS_INVALIDATED, SE_STATUS_OPEN})
SE_EXIT_REASONS = frozenset({SE_EXIT_SL_HIT, SE_EXIT_TP_STRUCT, SE_EXIT_TIME_STOP,
                             SE_EXIT_INVALIDATED, SE_EXIT_NOT_YET})

# ================= 3. try_fill / try_exit 未成交·未离场原因 why =================
WHY_NO_PRICE = "NO_PRICE"             # 无快照价
WHY_SUSPENDED = "SUSPENDED"           # 停牌
WHY_LIMIT_UP = "LIMIT_UP"            # 买方涨停不可买
WHY_NOT_YET_VALID = "NOT_YET_VALID"  # 早于 valid_from
WHY_WAIT_RETRACE = "WAIT_RETRACE"    # 限价未触(low>ref)
WHY_NO_OPEN = "NO_OPEN"              # limit_or_open 兜底但无开盘价
NOT_FILLED_WHY = frozenset({
    WHY_NO_PRICE, WHY_SUSPENDED, WHY_LIMIT_UP,
    WHY_NOT_YET_VALID, WHY_WAIT_RETRACE, WHY_NO_OPEN,
})

WHY_LIMIT_DOWN_SELL = "LIMIT_DOWN_SELL"  # 跌停无法卖出
WHY_BAD_POSITION = "BAD_POSITION"        # 持仓字段非法
WHY_HOLD = "HOLD"                         # 无触发(继续持有)
WHY_T1_LOCKED = "T1_LOCKED"              # T+1 当日买入不可卖
NOT_EXIT_WHY = frozenset({WHY_LIMIT_DOWN_SELL, WHY_BAD_POSITION, WHY_HOLD,
                          WHY_NO_PRICE, WHY_SUSPENDED, WHY_T1_LOCKED})

# ---- PENDING 撤单原因(expire_reason, R8) ----
EXP_BAD_GEOMETRY_FILL_GE_SL = "BAD_GEOMETRY_FILL_GE_SL"  # 成交时 fill价>=SL → 撤单(回测 BAD_ENTRY 同语义)
EXPIRE_REASONS = frozenset({EXP_BAD_GEOMETRY_FILL_GE_SL, "TIMEOUT"})

# ================= 4. 账本 status / entry_mode / fill mode / day_status =================
ST_PENDING_ORDER = "PENDING_ORDER"
ST_FILLED = "FILLED"
ST_EXPIRED = "EXPIRED"
ST_CLOSED = "CLOSED"
ORDER_STATUS = frozenset({ST_PENDING_ORDER, ST_FILLED, ST_EXPIRED, ST_CLOSED})

EM_LIMIT_RETRACE = "limit_retrace"    # 严格限价: 未触价永不成交
EM_LIMIT_OR_OPEN = "limit_or_open"    # 限价 + 开盘兜底(显式)
EM_NEXT_OPEN = "next_open"            # 次日开盘撮合
EM_LEGACY_RETRACE = "retrace"         # 废弃别名(= limit_or_open; 旧账本兼容, 生产不再写入)
ENTRY_MODES = frozenset({EM_LIMIT_RETRACE, EM_LIMIT_OR_OPEN, EM_NEXT_OPEN})
LEGACY_ENTRY_MODES = frozenset({EM_LEGACY_RETRACE})

# core/entry.py fill_in_zone 模式(STRICT_LIMIT 为 A4 生产默认; MARKET_OPEN 最宽研究档)
ENTRY_FILL_MODES = frozenset({"STRICT_LIMIT", "LIMIT_OR_OPEN", "INVALIDATED_BEFORE_FILL", "MARKET_OPEN"})

# paper_sim selection_result.day_status(R14 日历四态)
DAY_STATUS = frozenset({"OK", "WEEKEND", "HOLIDAY_OR_NO_DATA", "NO_SIGNAL"})

# ================= 5. 事件腿拒绝层(reject_ledger, R5/R6) + 组合回测器 =================
REJ_EVENT_FILTER = "EVENT_FILTER"
REJ_DUP_EXISTING = "DUP_EXISTING"
REJ_DATA_MISSING = "DATA_MISSING"
REJ_STAGE_PREFIX = "STAGE_"
REJ_ADX_LT20 = "ADX_LT20"
REJ_BAD_SL_GE_ENTRY = "BAD_SL_GE_ENTRY"          # R8: sl1>=挂单价 非法几何 fail-closed 拒单
REJ_CAPACITY_REJECT = "CAPACITY_REJECT"          # R15(第八轮审计 P1-9): 组合容量/kill switch 拒单(与策略拒绝分开)
REJECT_STAGES = frozenset({REJ_EVENT_FILTER, REJ_DUP_EXISTING, REJ_DATA_MISSING,
                           REJ_ADX_LT20, REJ_BAD_SL_GE_ENTRY, REJ_CAPACITY_REJECT})

# portfolio.py DailyPortfolioEngine 简化 reason(组合回测器内部) + 挂单 TTL
PF_SL, PF_TP, PF_TIME = "SL", "TP", "TIME"
PF_TTL_EXPIRED = "TTL_EXPIRED"          # 组合层挂单 TTL(5 交易日, V3-A)
PF_REASONS = frozenset({PF_SL, PF_TP, PF_TIME, PF_TTL_EXPIRED})

# ================= 6. SL 状态版本原因(sl_reason, R2) =================
SLR_INIT = "INIT"
SLR_TP1_MOVE_TO_BE = "TP1_MOVE_TO_BE"
SLR_SL_TOUCH_INTRADAY = "SL_TOUCH_INTRADAY"
SLR_SL_GAP_OPEN_BELOW_STOP = "SL_GAP_OPEN_BELOW_STOP"
SL_REASONS = frozenset({SLR_INIT, SLR_TP1_MOVE_TO_BE, SLR_SL_TOUCH_INTRADAY, SLR_SL_GAP_OPEN_BELOW_STOP})


# ================= 7. 校验助手 =================
def is_known_exit_reason(r):
    """账本 exit_reason 校验(None=未离场)。
    current = try_exit/simulate 现行族; paper = 纸面裁决/历史分支;
    ledger_legacy = v20f 旧组合带; 未知 → False。"""
    if r is None:
        return True, "open"
    if r in EXIT_REASONS or r in SIM_REASONS:
        return True, "current"
    if r in PAPER_EXITS:
        return True, "paper_legacy"
    if r in LEDGER_LEGACY_EXITS:
        return True, "ledger_legacy(v20f 旧组合带)"
    return False, f"UNKNOWN_EXIT_REASON:{r}"


def is_known_not_filled_why(w):
    if w is None:
        return False, "missing"
    if w in NOT_FILLED_WHY:
        return True, "current"
    if w == "unknown":  # 历史 PENDING 记录缺 why 的兜底值
        return True, "legacy(unknown 兜底)"
    return False, f"UNKNOWN_NOT_FILLED_WHY:{w}"