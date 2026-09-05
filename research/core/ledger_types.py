# -*- coding: utf-8 -*-
"""core/ledger_types.py —— 迭代八：四本账（回测/纸面/shadow/实盘）类型与门禁

蓝图：回测账(固定历史)、纸面账(实时信号不下单)、shadow账(模拟真实订单/延迟)、实盘账(真金)。
门禁：满足条件才允许 research → shadow → live；未通过不得升级。
"""
import json, os, time

LEDGER_TYPES = ("backtest", "paper", "shadow", "live")


def ledger_book(kind):
    """四本账文件名。"""
    if kind not in LEDGER_TYPES:
        raise ValueError(f"unknown ledger type: {kind}")
    return f"{kind}_ledger.json"


def annotate_trade(tr, kind, run_id="", signal_id=None):
    """给交易记录打四本账标签（蓝图附录 A 交易字段子集）。"""
    if kind not in LEDGER_TYPES:
        raise ValueError(kind)
    tr["ledger_type"] = kind
    tr["run_id"] = run_id
    if signal_id:
        tr["signal_id"] = signal_id
    tr["created_at"] = tr.get("created_at") or time.strftime("%Y-%m-%dT%H:%M:%S")
    return tr


# ---------------- 门禁检查（蓝图 §9）----------------
def _check(cond, msg):
    return (True, "") if cond else (False, msg)


def gate_research_to_shadow(checks):
    """research → shadow 门禁。checks: dict of {name: bool}。
    蓝图 §9：无前视/可追溯/数据锁定/成本建模/OOS-WF 通过/非单点最优/漏斗完整/多状态可解释。
    """
    results = []
    for name, passed in checks.items():
        results.append((name, passed))
    failed = [n for n, p in results if not p]
    return (len(failed) == 0), failed


def gate_shadow_to_live(shadow_stats):
    """shadow → 小额实盘门禁。shadow_stats: dict。
    蓝图 §9：连续窗口稳定/成交偏差可解释/无数据缺口/数量分布无漂移/回滚可用。
    """
    req = {
        "consecutive_stable": shadow_stats.get("consecutive_stable_days", 0) >= 30,
        "fill_deviation_ok": shadow_stats.get("fill_deviation_pct", 99) <= shadow_stats.get("max_fill_dev_pct", 0.5),
        "no_data_gap": not shadow_stats.get("has_data_gap", True),
        "signal_volume_stable": shadow_stats.get("signal_volume_drift", 99) <= 0.3,
        "rollback_ready": shadow_stats.get("rollback_version", "") != "",
    }
    failed = [n for n, p in req.items() if not p]
    return (len(failed) == 0), failed, req


def require_manifest(path):
    """fail-closed：运行目录必须有有效 run_manifest.json，否则拒绝进入生产链。"""
    try:
        with open(os.path.join(path, "run_manifest.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        if m.get("status") == "invalid":
            return False, "manifest invalid: " + m.get("invalid_reason", "")
        return True, "ok"
    except FileNotFoundError:
        return False, "missing run_manifest.json (fail-closed)"
    except Exception as e:
        return False, f"manifest read error: {e}"
