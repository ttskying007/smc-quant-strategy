# -*- coding: utf-8 -*-
"""r38_regime_ab.py —— tests_regime.py 弱市断言 A/B (legacy vs 新基线).

tests_regime.py 断言"事件腿弱市(BEAR/PANIC)更优(逆向策略特征)"。
重基线后该断言 FAIL: weak=[3.176, 1.259] strong=[4.271]。

本脚本用**同一 core.regime 函数**分别跑 legacy 归档与新基线, 判定:
  · 若 legacy 也 FAIL → 该断言与本次重基线无关(预先脆弱/已被市场结构推翻)
  · 若 legacy PASS 而新 FAIL → 重基线改变了 regime 归因, 需按审计流程处置
纯诊断, 不修改任何数据。
"""
import csv, io, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = r"E:\test\smc_project\research"
sys.path.insert(0, HERE)
from core.regime import regime_effect_on_event_leg

def dist_for(path, label):
    if not os.path.exists(path):
        print("  %s: 文件缺失 %s" % (label, path)); return None
    rows = [r for r in csv.DictReader(open(path, encoding="utf-8-sig"))
            if r.get("src") == "EVENT" and r.get("net_pnl_pct") not in (None, "", "None")]
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["entry_date"]].append(float(r["net_pnl_pct"]))
    d = regime_effect_on_event_leg(dict(by_date))
    print("\n%s  (EVENT n=%d)" % (label, len(rows)))
    for reg, st in sorted(d.items(), key=lambda x: -x[1]["n"]):
        print("    %-10s n=%4d avg=%+.3f%% wr=%.3f pf=%.2f"
              % (reg, st["n"], st["avg"], st["wr"], st["pf"]))
    weak = [v["avg"] for k, v in d.items() if k in ("BEAR", "PANIC")]
    strong = [v["avg"] for k, v in d.items() if k == "BULL"]
    if weak and strong:
        passed = max(weak) > min(strong)
        print("    -> 断言 '弱市更优': %s (weak=%s strong=%s)"
              % ("PASS" if passed else "FAIL",
                 [round(x, 3) for x in weak], [round(x, 3) for x in strong]))
        return passed
    print("    -> 断言不可判定(缺 BEAR/PANIC 或 BULL 桶)")
    return None

legacy = dist_for(os.path.join(HERE, "archive", "combo_v20f_trades_legacy_dx_h15.csv"),
                  "① LEGACY 归档 (legacy DX, max_hold=15)")
new = dist_for(os.path.join(HERE, "combo_v20f_trades.csv"),
               "② 新基线 (Wilder, max_hold=12)")

print("\n" + "=" * 78)
print("判定:")
if legacy is False and new is False:
    print("  两者皆 FAIL → tests_regime 该断言**与本次重基线无关**")
    print("  属预先存在的脆弱断言(逆向策略弱市更优已被市场结构/样本变化推翻),")
    print("  应按独立议题处置(更新断言或标注为观察项), 不阻塞重基线。")
elif legacy is True and new is False:
    print("  legacy PASS / 新基线 FAIL → **重基线改变了 regime 归因**, 需审计处置。")
elif legacy is True and new is True:
    print("  两者皆 PASS → 与本次重基线无关(可能为运行期数据变动)。")
else:
    print("  结果不完整, 需人工复核。")