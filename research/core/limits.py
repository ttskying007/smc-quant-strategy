# -*- coding: utf-8 -*-
"""core/limits.py —— V2 第四轮 A8: A股涨跌停幅度全项目统一
第三轮深审 A8: profile 用统一 9.5% 近似, execution 按板块区分 → 同一股票两模块规则不一致。
本模块成为唯一真值源:
  - 主板(60/00): ±10%
  - 创业板(30)/科创板(68): ±20% (2020-08-24 注册制后)
  - 北交所(8/4/92): ±30%
  - ST: ±5% (无法从代码判定ST状态, 需外部传入; 默认 False)
日期感知: 2020-08-24 前创业板也按 10%。
"""
from datetime import date as _date


def daily_limit_pct(code, d8=None, is_st=False):
    """统一涨跌停幅度(%)。code 支持 '600000'/'600000.SH'/'000001_SZ' 等形式。
    d8: YYYYMMDD(2020-08-24 前创业板 10%)。is_st: ST 股(主板5%)。"""
    c = str(code or "")
    digits = "".join(ch for ch in c if ch.isdigit())
    if len(digits) < 6:
        return 10.0
    head = digits[:6]
    # 2020-08-24 之前创业板仍是 10%
    gem20 = True
    if d8:
        try:
            gem20 = str(d8)[:8].replace("-", "") >= "20200824"
        except Exception:
            gem20 = True
    if head.startswith("68"):            # 科创板
        return 20.0
    if head.startswith("30"):            # 创业板
        return 20.0 if gem20 else 10.0
    if head.startswith(("8", "4", "92")) and not head.startswith(("80", "68")):
        # 北交所(83/87/88/43/92 等) —— 简化: 8/4/9 开头且非沪深主板规则
        if head[0] in ("4", "8", "9"):
            return 30.0
    if is_st:
        return 5.0
    return 10.0                          # 主板(60/00/90深市基金除外等按10%)


def is_limit_up(close, prev_close, code, d8=None, is_st=False, tol=1e-4):
    """收盘是否涨停(相对昨收, 幅度>=限幅-tol)。"""
    if not prev_close or prev_close <= 0:
        return False
    lim = daily_limit_pct(code, d8, is_st) / 100.0
    return close / prev_close - 1 >= lim - tol


def is_limit_down(close, prev_close, code, d8=None, is_st=False, tol=1e-4):
    if not prev_close or prev_close <= 0:
        return False
    lim = daily_limit_pct(code, d8, is_st) / 100.0
    return close / prev_close - 1 <= -(lim - tol)