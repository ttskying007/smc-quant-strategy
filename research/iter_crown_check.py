# -*- coding: utf-8 -*-
"""实盘皇冠信号检查：当前 8-17~8-20 事件中哪些是"周一+放量/ACCUM+放量"皇冠信号"""
import io, json, sys
import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")
import paper_sim as ps

led = json.load(open(r"E:\test\smc_project\research\paper_ledger.json", encoding="utf-8"))
new = [t for t in led if str(t.get("signal_date", "") or t.get("disclose_date", "")) >= "2026-08-17"]

print("=== 8-17 起事件信号的皇冠特征识别 ===\n")
for t in new:
    code = t.get("code")
    sig = str(t.get("signal_date", ""))
    d8 = sig.replace("-", "")
    bs = ps.bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d8 not in dates:
        continue
    i = dates.index(d8)
    # monday check
    try:
        wd = datetime.date(int(d8[:4]), int(d8[4:6]), int(d8[6:8])).weekday()
        mon = "周一" if wd == 0 else f"周{['一','二','三','四','五','六','日'][wd]}"
    except Exception:
        mon = "?"
    # volume ratio
    avg_v = sum(bs[k]["v"] for k in range(i + 1 - 20, i + 1)) / 20 if i + 1 >= 20 else 0
    v_ratio = bs[i + 1]["v"] / avg_v if (avg_v and i + 1 < len(bs)) else 1.0
    vol_mark = "放量" if v_ratio > 1.2 else "缩量/中量"
    st, deep = ps.stage_and_deep(bs, i) if i >= 91 else (None, False)
    crown1 = "✅周一+放量" if (wd == 0 and v_ratio > 1.2) else ""
    crown2 = "✅ACCUM+放量" if (st == "ACCUM" and v_ratio > 1.2) else ""
    mp = t.get("mark_pnl_pct")
    mp_s = f"{mp:+.2f}%" if mp is not None else "-"
    print(f"  {code} {t.get('name')} sig={sig} {mon} {vol_mark}({v_ratio:.2f}) 阶段={st} 浮盈={mp_s} {crown1}{crown2}")
