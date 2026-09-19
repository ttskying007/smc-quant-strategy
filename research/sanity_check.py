# -*- coding: utf-8 -*-
"""sanity_check.py —— 周一开盘前 60s 自检
落地三个常见故障:
  ① announce DB 最近 max(date) 滞后(数据源卡了发现过)
  ② selection_funnel_history.json (<8 日, ±2σ 不启动)
  ③ PAPER 台账字段初始化能验证

用法: python sanity_check.py
exit 0 = 无风险 / exit 1 = 有警告
"""
import io, json, os, sqlite3, sys
from datetime import date, datetime, timedelta
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config as CFG

PASS, FAIL = [], []

def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    flag = "[OK]" if cond else "[FAIL]"
    print(" " + flag + " " + name + ((" -- " + str(detail)) if (detail and not cond) else ""))

def wd_back(d, n):
    """回溯最近 n 个工作日(周一=0..周五=4)"""
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.strftime("%Y-%m-%d"))
        d -= timedelta(days=1)
    return out

print("== 1. announce DB 时新性 ==")
try:
    c = sqlite3.connect(CFG.ANNOUNCE_DB)
    max_d = c.execute("SELECT MAX(date) FROM announce").fetchone()[0]
    print("   DB max:", max_d)
    ok("max(date) 记录存在", max_d is not None)
    today = date.today()
    # 合理预期: 周日前 max 应围绕前一个工作日(周五)
    if today.weekday() == 6:  # 周日 → 前 2 天(周五-2)
        lookback = wd_back(today - timedelta(days=2), 1)
    elif today.weekday() == 5:  # 周六 → 前 1 天(周五)
        lookback = wd_back(today - timedelta(days=1), 1)
    else:  # 工作日 → 前一天
        lookback = wd_back(today - timedelta(days=1), 1)
    print("   期望 >=:", lookback[0] if lookback else "n/a")
    ok("DB 不落后预期", max_d >= lookback[0] if lookback else True)
    recent = [x[0] for x in c.execute(
        "SELECT DATE(date) FROM announce WHERE date >= ? GROUP BY DATE(date) ORDER BY DATE(date) DESC LIMIT 10",
        ((today - timedelta(days=10)).strftime("%Y-%m-%d"),)).fetchall()]
    print("   近 10 天有数据日:", recent)
    c.close()
except Exception as e:
    ok("announce DB 可连接", False, str(e))

print("\n== 2. selection funnel 深度(R7 需要 8 天基线) ==")
try:
    with open(r"research\selection_funnel_history.json", encoding="utf-8") as f:
        hist = json.load(f)
    n = len(hist) if isinstance(hist, list) else 0
    print("   已累积天数:", n, [x.get("day") for x in (hist[-6:] if n >= 6 else hist)])
    ok("funnel 有样本", n >= 3, f"n={n}")
    ok("漏斗达 8 天基线可启 ±2σ 判异", n >= 8, f"当前 n={n}, 待 {8 - n} 天")
except Exception as e:
    ok("selection_funnel_history.json", False, str(e))

print("\n== 3. PAPER ledger 完整 ==")
try:
    led = json.load(open(CFG.LEDGER, encoding="utf-8"))
    closed = [o for o in led if o.get("status") == "CLOSED"]
    n_attr = sum(1 for o in closed if o.get("loss_attribution"))
    with_rank = sum(1 for o in closed if o.get("rank_score") is not None)
    print("   CLOSED:", len(closed), "| 含 loss_attribution:", n_attr,
          "| 含 rank_score:", with_rank, "/", len(closed))
    ok("有 CLOSED 订单", len(closed) >= 10, f"n={len(closed)}")
    ok("有 rank_score(全部覆盖)", len(closed) > 0 and with_rank == len(closed),
       f"{with_rank}/{len(closed)}")
except Exception as e:
    ok("PAPER ledger 完整", False, str(e))

print("\n== 4. 核心模块可导入 ==")
try:
    from core.attribution import attribute_trade, ALL_LABELS
    ok("core.attribution", len(ALL_LABELS) == 20, f"n={len(ALL_LABELS)}")
except Exception as e:
    ok("core.attribution", False, str(e))
try:
    import core.adaptive, core.profile, core.regime
    ok("core 辅助模块", True)
except Exception as e:
    ok("core 辅助模块", False, str(e))

print("\n合计: PASS=%d FAIL=%d" % (len(PASS), len(FAIL)))
if FAIL:
    print("失败清单:")
    for name, detail in FAIL:
        print("  *", name, "->", detail)
sys.exit(1 if FAIL else 0)
