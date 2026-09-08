# -*- coding: utf-8 -*-
"""exit_new 样本减半归因：simulate skip 原因分布（2024 旧过滤集合）"""
import io, json, os, sqlite3, sys
from collections import Counter
sys.path.insert(0, r"E:\test\smc_project\research")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
from core.events import classify_title
import core.execution as EX
from v20f_common import bars_of, adx14, stage_of, is_strong_old  # 共享工具，无模块级执行

conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
cur = conn.cursor()
cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
skip_reasons = Counter()
checked = 0
seen = set()
for date, code, title in cur.fetchall():
    if not is_strong_old(title):
        continue
    d = str(date)[:10].replace("-", "")
    if (code, d) in seen:
        continue
    seen.add((code, d))
    bs = bars_of(code)
    if not bs:
        continue
    dates = [b["t"] for b in bs]
    if d not in dates:
        continue
    i = dates.index(d)
    if stage_of(bs, i) not in ("ACCUM", "DOWNTREND"):
        continue
    adx = adx14(bs, i)
    if adx is None or adx < 20:
        continue
    entry_idx = i + 1
    if entry_idx + 17 >= len(bs) or entry_idx < 130:
        continue
    if bs[entry_idx]["t"] < "20230901" or bs[entry_idx]["t"][:4] != "2024":
        continue
    ep_open = bs[entry_idx]["o"]
    if ep_open <= 0:
        continue
    disc_close = bs[i]["c"]
    highs, lows = [], []
    for j in range(i - 1, max(0, i - 60), -1):
        if j < 3 or j + 3 >= i:
            continue
        if len(highs) < 2 and bs[j]["h"] > max(bs[k]["h"] for k in range(j - 3, j)) and bs[j]["h"] >= max(bs[k]["h"] for k in range(j + 1, j + 4)):
            highs.append(bs[j]["h"])
        if len(lows) < 2 and bs[j]["l"] < min(bs[k]["l"] for k in range(j - 3, j)) and bs[j]["l"] <= min(bs[k]["l"] for k in range(j + 1, j + 4)):
            lows.append(bs[j]["l"])
        if len(highs) >= 2 and len(lows) >= 2:
            break
    if not highs or not lows:
        continue
    highs.sort()
    limit = disc_close * 0.99
    ep = limit if bs[entry_idx]["l"] <= limit else ep_open
    _atr = 0
    if i >= 15:
        _trs = [max(bs[k]["h"] - bs[k]["l"], abs(bs[k]["h"] - bs[k - 1]["c"]), abs(bs[k]["l"] - bs[k - 1]["c"]))
                for k in range(i - 14, i)]
        _atr = sum(_trs) / 14
    sl1 = (lows[0] - 0.5 * _atr) if _atr > 0 else lows[0] * 0.99
    _tps = sorted([x for x in (highs[0], highs[1] if len(highs) > 1 else highs[0] * 1.05, highs[-1]) if x and x > ep])
    if not _tps:
        continue
    checked += 1
    r = EX.simulate(bs, entry_idx, ep, sl1, tp1=_tps[0],
                    tp2=_tps[1] if len(_tps) > 1 else _tps[0] * 1.05,
                    tp3=_tps[2] if len(_tps) > 2 else _tps[1] * 1.05,
                    partial_tp1=0.3, stop_to_be=True, max_hold=15, code=code)
    if r.get("skipped"):
        skip_reasons[r["reason"]] += 1
        # 记录一个 BAD_ENTRY 细节
        if r["reason"] == "BAD_ENTRY" and skip_reasons["BAD_ENTRY"] <= 3:
            print(f"  BAD_ENTRY样例: ep={ep:.3f} sl1={sl1:.3f} risk={ep-sl1:.3f} entry_o={bs[entry_idx]['o']:.3f} prev_c={bs[entry_idx-1]['c']:.3f}")
    if skip_reasons.get("SKIP_LIMIT_UP", 0) == 1 and "SKIP_LIMIT_UP" not in (skip_reasons or {}) :
        pass

print(f"\n2024 旧过滤集合: checked={checked}")
print("skip 分布:", dict(skip_reasons))
conn.close()