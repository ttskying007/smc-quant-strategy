# -*- coding: utf-8 -*-
"""回填多指标结构分层 TP/SL（swing+FVG+BSL，tp1-tp4/sl1-sl2）"""
import io, json, sys
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

led = ps.load_ledger()
n = 0
for t in led:
    code = t.get("code")
    sig = str(t.get("signal_date", "") or t.get("disclose_date", ""))
    sig8 = sig.replace("-", "")
    tp1, tp2, tp3, tp4, sl1, sl2 = ps.structural_sltp(code, sig8)
    if tp1 is None or sl1 is None:
        continue
    ep = t.get("entry_price") or t.get("filled_price") or 0
    if ep <= 0:
        continue
    # ensure all TP > entry and ascending; SL < entry
    levels = sorted([x for x in (tp1, tp2, tp3, tp4) if x and x > ep])
    if not levels:
        levels = [ep * 1.03, ep * 1.06, ep * 1.10, ep * 1.15]
    while len(levels) < 4:
        levels.append(levels[-1] * 1.03)
    t["tp1"], t["tp2"], t["tp3"], t["tp4"] = [round(x, 3) for x in levels[:4]]
    t["tp_price"] = t["tp4"]
    t["sl1"] = round(sl1, 3) if sl1 < ep else round(ep * 0.96, 3)
    t["sl2"] = round(sl2, 3) if sl2 and sl2 < t["sl1"] else round(t["sl1"] * 0.94, 3)
    t["sl_price"] = t["sl1"]
    n += 1
ps.save_ledger(led)
print(f"回填 {n} 笔多指标结构分层")
for t in led[:4]:
    print(f"  {t.get('code')} {t.get('name')} ep={t.get('entry_price')} TP1={t.get('tp1')} TP2={t.get('tp2')} TP3={t.get('tp3')} TP4={t.get('tp4')} SL1={t.get('sl1')} SL2={t.get('sl2')}")
