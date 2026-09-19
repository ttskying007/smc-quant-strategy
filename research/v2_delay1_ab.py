# -*- coding: utf-8 -*-
"""受控 ENTRY-DELAY A/B: 预注册 2026-09-19 (R13 发现驱动, 单一假设)
背景: 事件腿 530 亏损归因(R13 20类)揭示 LOSS_TIME_SHORT 59 笔/10.9% ——
      入场后 ≤2 根 bar 即 SL_HIT, 怀疑"入场过早、缺确认根"。
假设 H: 把入场推迟 1 根 bar(A=立即, B=延迟1根), 其余全部不变:
  - 同一 announce DB / 同 title 过滤 / 同 stage/ADX 门槛
  - 同一 SL/TP 语义(gen_v20f 现行口径, SL=lows[0]-0.5ATR)
  - 唯一变量: entry_idx → entry_idx+1; B 臂仍用 <t+1bar limit(disc_close*0.99) 成交规则
信息时点: d=公告收盘才构造 zone/sl, 入场在 d+1 / d+2, 无前瞻(两臂都只用 ≤i 信息)
晋级线(预注册): OOS avg 与 PF 双升才允许”延迟入场”成为候选改造;
             若 B 恶化或持平, 直接回滚不入库。
执行方式: 单进程双语义(避免 DB 回填污染), 字段对子级输出(n≥30 才报 CI 小样本慎判)。
"""
import csv, io, json, os, sqlite3, sys
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

src = open(r"E:\test\smc_project\research\gen_v20f.py", encoding="utf-8").read()
head = src.split("ev = []")[0]
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
skipped_delay = 0
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
    if entry_idx + 1 >= len(bs):  # B 臂需要下一根
        skipped_delay += 1
        continue
    ep_open = bs[entry_idx]["o"]
    disc_close = bs[i]["c"]
    if ep_open <= 0:
        continue
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
    sl = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
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

    # 臂 A: 立即入场(entry_idx)
    epA = limit if bs[entry_idx]["l"] <= limit else ep_open
    _tps = sorted([x for x in (highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]) if x and x > epA])
    if not _tps:
        continue
    tp1A = _tps[0]; tp2A = _tps[1] if len(_tps) > 1 else tp1A * 1.05
    tp3A = _tps[2] if len(_tps) > 2 else tp2A * 1.05
    rA = _sim(bs, entry_idx, epA, sl, tp1=tp1A, tp2=tp2A, tp3=tp3A,
              partial_tp1=0.3, stop_to_be=True, max_hold=15, code=str(code)[:6])

    # 臂 B: 延迟 1 根入场(entry_idx+1), SL/TP 保持不变(同信息时点构造)
    eB = entry_idx + 1
    epB = limit if bs[eB]["l"] <= limit else bs[eB]["o"]
    _tpsB = sorted([x for x in (highs[0], (highs[1] if len(highs) > 1 else highs[0] * 1.05), highs[-1]) if x and x > epB])
    if not _tpsB:
        skipped_delay += 1
        continue
    tp1B = _tpsB[0]; tp2B = _tpsB[1] if len(_tpsB) > 1 else tp1B * 1.05
    tp3B = _tpsB[2] if len(_tpsB) > 2 else tp2B * 1.05
    rB = _sim(bs, eB, epB, sl, tp1=tp1B, tp2=tp2B, tp3=tp3B,
              partial_tp1=0.3, stop_to_be=True, max_hold=15, code=str(code)[:6])

    if rA.get("skipped") or rB.get("skipped"):
        continue
    pairs.append({"code": str(code), "date": bs[entry_idx]["t"],
                  "netA": rA.get("net_pnl_pct", 0.0), "netB": rB.get("net_pnl_pct", 0.0),
                  "reasonA": rA.get("reason", ""), "reasonB": rB.get("reason", ""),
                  "holdA": rA.get("hold_bars", 0), "holdB": rB.get("hold_bars", 0),
                  # TIME_SHORT 标记(A 臂口径): SL_HIT 且 hold≤2
                  "tsA": (rA.get("reason") == "SL_HIT" and rA.get("hold_bars", 0) <= 2)})
conn.close()
print(f"候选对: {len(pairs)} | 延迟构造跳过: {skipped_delay}")
print(f"A 臂 TIME_SHORT 命中(SL_HIT&hold≤2): {sum(1 for p in pairs if p['tsA'])}")

OOS = "20250701"
def stats(key, subset=None):
    xs = [p[key] for p in pairs if (subset is None or subset(p))]
    if not xs:
        return {"n": 0}
    w = [x for x in xs if x > 0]
    l_ = [x for x in xs if x <= 0]
    return {"n": len(xs), "avg": round(sum(xs)/len(xs), 3), "wr": round(len(w)/len(xs), 3),
            "pf": round(sum(w)/abs(sum(l_)), 2) if l_ and sum(l_) else 99}

def split(key):
    return {"IS": stats(key, lambda p: p["date"] < OOS),
            "OOS": stats(key, lambda p: p["date"] >= OOS)}

out = {"prereg": {"hypothesis": "delay1 improves OOS avg & PF", "asof": "2026-09-19"},
       "pairs": len(pairs), "skipped_delay": skipped_delay,
       "A_immediate": split("netA"), "B_delay1": split("netB")}
# TIME_SHORT 子集(A 判定)
ts = [p for p in pairs if p["tsA"]]
if ts:
    out["timeshort_subset"] = {
        "n": len(ts),
        "A_avg": round(sum(p["netA"] for p in ts)/len(ts), 3),
        "B_avg": round(sum(p["netB"] for p in ts)/len(ts), 3),
        "B_escaped_loss": sum(1 for p in ts if p["netB"] > 0),
        "OOS": {"n": sum(1 for p in ts if p["date"] >= OOS),
                "A_avg": round(sum(p["netA"] for p in ts if p["date"] >= OOS)/max(1, sum(1 for p in ts if p["date"] >= OOS)), 3),
                "B_avg": round(sum(p["netB"] for p in ts if p["date"] >= OOS)/max(1, sum(1 for p in ts if p["date"] >= OOS)), 3)}}
print("\n== 受控 ENTRY-DELAY A/B(同DB同候选, 唯一变量=入场bar+1) ==")
print(f"  A 立即: IS={out['A_immediate']['IS']} OOS={out['A_immediate']['OOS']}")
print(f"  B 延迟1根: IS={out['B_delay1']['IS']} OOS={out['B_delay1']['OOS']}")
if "timeshort_subset" in out:
    tso = out["timeshort_subset"]
    print(f"  TIME_SHORT 子集 n={tso['n']}: A_avg={tso['A_avg']}% vs B_avg={tso['B_avg']}% | B 转正 {tso['B_escaped_loss']} 笔")
    print(f"    OOS: n={tso['OOS']['n']} A={tso['OOS']['A_avg']}% B={tso['OOS']['B_avg']}%")
A_oos, B_oos = out["A_immediate"]["OOS"], out["B_delay1"]["OOS"]
verdict = (A_oos.get("n", 0) >= 30 and B_oos.get("n", 0) >= 30
           and B_oos.get("avg", 0) > A_oos.get("avg", 0)
           and B_oos.get("pf", 0) > A_oos.get("pf", 0))
out["verdict_promote"] = verdict
print(f"\n晋级判定(OOS avg 与 PF 双升): {'PASS' if verdict else 'NOT-PROMOTE(回滚不入库)'}")

json.dump(out, open(r"E:\test\smc_project\research\handover\受控延迟入场AB.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("已写 handover/受控延迟入场AB.json")
