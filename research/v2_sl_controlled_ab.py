# -*- coding: utf-8 -*-
"""受控 SL 语义 A/B: 排除 announce DB 回填干扰。
在【同一次运行】内, 对同一批候选逐笔双 SL 计算:
  slA = 原语义(lows[0] − 0.5×ATR)
  slB = 结构位收紧 min(披露前5根最低低×0.995, slA)
只对比 SL 语义差异, 入场/TP/其他条件完全同 gen_v20f 当前源码。"""
import csv, io, json, os, sqlite3, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 复用 gen_v20f 的函数(import 触发模块级回测——改用 exec 提取函数)
src = open(r"E:\test\smc_project\research\gen_v20f.py", encoding="utf-8").read()
head = src.split("ev = []")[0]  # 只取函数定义段(含 import 与 bars_of 等)
# 剥掉 gen_v20f 的 stdout 重包装行(它会关闭主脚本 stdout 的底层 buffer)
import re as _re
head = "\n".join(l for l in head.split("\n")
                 if "sys.stdout" not in l and "io.TextIOWrapper" not in l)
ns = {"__file__": r"E:\test\smc_project\research\gen_v20f.py", "__name__": "gen_v20f_head"}
exec(head, ns)
bars_of, is_strong, adx14, stage_of = ns["bars_of"], ns["is_strong"], ns["adx14"], ns["stage_of"]

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")

from core.execution import simulate as _sim
pairs = []
for date, code, title in cur.fetchall():
    if not is_strong(title):
        continue
    d = str(date)[:10].replace("-", "")
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    st = stage_of(bs, i)
    if st not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901":
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
    # swing lows (与 gen_v20f 一致)
    lows = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(lows) >= 2:
            break
    if not lows:
        continue
    _atr = 0
    if i >= 15:
        _trs = []
        for _k in range(i - 14, i):
            _tr = max(bs[_k]["h"] - bs[_k]["l"], abs(bs[_k]["h"] - bs[_k - 1]["c"]), abs(bs[_k]["l"] - bs[_k - 1]["c"]))
            _trs.append(_tr)
        _atr = sum(_trs) / 14 if _trs else 0
    slA = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    _struct_low = min(bs[k]["l"] for k in range(max(0, i - 4), i + 1))
    slB = min(_struct_low * 0.995, slA)
    # TP 层(与 gen_v20f 一致)
    highs = []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(highs) >= 2:
            break
    if not highs:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    tp1, tp2, tp3 = highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]
    _tps = sorted([x for x in (tp1, tp2, tp3) if x and x > ep])
    if not _tps:
        continue
    tp1 = _tps[0]
    tp2 = _tps[1] if len(_tps) > 1 else tp1 * 1.05
    tp3 = _tps[2] if len(_tps) > 2 else tp2 * 1.05
    # 双 SL 重放
    rA = _sim(bs, entry_idx, ep, slA, tp1=tp1, tp2=tp2, tp3=tp3,
              partial_tp1=0.3, stop_to_be=True, max_hold=15, code=str(code)[:6])
    rB = _sim(bs, entry_idx, ep, slB, tp1=tp1, tp2=tp2, tp3=tp3,
              partial_tp1=0.3, stop_to_be=True, max_hold=15, code=str(code)[:6])
    if rA.get("skipped") or rB.get("skipped"):
        continue
    pairs.append({"code": str(code), "date": bs[entry_idx]["t"],
                  "netA": rA.get("net_pnl_pct", 0.0), "netB": rB.get("net_pnl_pct", 0.0),
                  "reasonA": rA.get("reason", ""), "reasonB": rB.get("reason", ""),
                  "slA": round(slA, 3), "slB": round(slB, 3),
                  "sl_changed": abs(slA - slB) / max(slA, 1e-9) > 0.005})
conn.close()
print(f"候选对: {len(pairs)} | SL 实际变化: {sum(1 for p in pairs if p['sl_changed'])}")

OOS = "20250701"
def stats(key, oos):
    sel = [p[key] for p in pairs if (p["date"] >= OOS) == oos]
    if not sel:
        return {"n": 0}
    w = [x for x in sel if x > 0]
    l_ = [x for x in sel if x <= 0]
    return {"n": len(sel), "avg": round(sum(sel)/len(sel), 3), "wr": round(len(w)/len(sel), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ else 99}

out = {"pairs": len(pairs), "sl_changed": sum(1 for p in pairs if p['sl_changed']),
       "A_oldSL": {"IS": stats("netA", False), "OOS": stats("netA", True)},
       "B_structSL": {"IS": stats("netB", False), "OOS": stats("netB", True)}}
# SL 变化子集(真正受影响的交易)
chg = [p for p in pairs if p["sl_changed"]]
sel_oos = [p["netA"] for p in chg if p["date"] >= OOS]
sel_oos_B = [p["netB"] for p in chg if p["date"] >= OOS]
if chg:
    out["changed_subset"] = {
        "n": len(chg),
        "OOS_A": {"n": len(sel_oos), "avg": round(sum(sel_oos)/len(sel_oos), 3) if sel_oos else None},
        "OOS_B": {"n": len(sel_oos_B), "avg": round(sum(sel_oos_B)/len(sel_oos_B), 3) if sel_oos_B else None}}
print(f"\n== 受控 SL A/B(同DB同候选同TP) ==")
print(f"  A 原SL: IS={out['A_oldSL']['IS']} OOS={out['A_oldSL']['OOS']}")
print(f"  B 结构SL: IS={out['B_structSL']['IS']} OOS={out['B_structSL']['OOS']}")
if "changed_subset" in out:
    cs = out["changed_subset"]
    print(f"  SL变化子集 n={cs['n']}: OOS A={cs['OOS_A']} vs B={cs['OOS_B']}")

json.dump(out, open(r"E:\test\smc_project\research\handover\受控SL语义AB.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("已写 handover/受控SL语义AB.json")