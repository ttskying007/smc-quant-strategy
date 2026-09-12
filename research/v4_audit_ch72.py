# -*- coding: utf-8 -*-
"""v4_audit_ch72.py —— 审计 §7.2 股票分层(ABCDE)的事件腿落档(预注册 #43)
审计建议按流动性/波动率分层(大盘/中盘/小盘高波/低流动/ST次新)分别定参数。
现有台账无成交额/市值字段 → 用**价格代理 + 代码前缀代理**做可归因分层:
  L1 板块: 60xxxx 主板 / 000/002 主板+中小 / 300 创业 / 688 科创
  L2 价格档: <5 低价 / 5-20 中价 / 20-50 中高 / >50 高价(流动性弱近似)
预注册:
  D1 各板块 avg/pf 差异 >2pp → 板块分层有信息(审计建议有据)
  D2 各价格档差异 >2pp → 价格分层有信息
  D3 若某层 n<30 → 该层样本不足(如实报, 不下结论)
  D4 事件腿是否已有板块语义: 涨跌幅限制不同(主板10%/创业科创20%) → SL_GAP 率按板块分解"""
import csv, io, json, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv",
                                encoding="utf-8-sig", errors="replace")))
ev = []
for r in rows:
    if r.get("src") != "EVENT" or not r.get("net_pnl_pct"):
        continue
    sym = str(r.get("symbol") or "")
    code = sym.split(".")[0]
    try:
        bp = float(r.get("buy_price") or 0)
    except Exception:
        bp = 0
    if code.startswith("688"):
        board = "科创688"
    elif code.startswith("300"):
        board = "创业300"
    elif code.startswith("60"):
        board = "主板60x"
    elif code.startswith("002"):
        board = "中小002"
    else:
        board = "深主00x"
    if bp < 5:
        px = "<5低价"
    elif bp < 20:
        px = "5-20中价"
    elif bp < 50:
        px = "20-50中高"
    else:
        px = ">50高价"
    ev.append({"board": board, "px": px, "pnl": float(r["net_pnl_pct"]),
               "reason": str(r.get("reason") or ""), "bp": bp})
n = len(ev)
print(f"n={n}")

def stats(v):
    if not v:
        return {"n": 0}
    w = sum(x for x in v if x > 0); l_ = abs(sum(x for x in v if x <= 0))
    return {"n": len(v), "avg": round(sum(v) / len(v), 2),
            "wr": round(len([x for x in v if x > 0]) / len(v) * 100, 1),
            "pf": round(w / l_, 2) if l_ > 0 else 99}

# D1 板块
by_board = defaultdict(list)
for t in ev:
    by_board[t["board"]].append(t["pnl"])
print("\nD1 板块分层:")
boards = {}
for b in sorted(by_board, key=lambda k: -len(by_board[k])):
    boards[b] = stats(by_board[b])
    s = boards[b]
    print(f"  {b}: n={s['n']} avg={s['avg']} wr={s['wr']}% pf={s['pf']}" + (" (n<30 不足)" if 0 < s["n"] < 30 else ""))

# D2 价格档
by_px = defaultdict(list)
for t in ev:
    if t["bp"] > 0:
        by_px[t["px"]].append(t["pnl"])
print("\nD2 价格档分层:")
pxs = {}
for p in ("<5低价", "5-20中价", "20-50中高", ">50高价"):
    pxs[p] = stats(by_px.get(p, []))
    s = pxs[p]
    print(f"  {p}: n={s['n']} avg={s.get('avg')} pf={s.get('pf')}")

# D4 SL_GAP 率按板块(涨跌幅限制语义)
gap = defaultdict(lambda: [0, 0])
for t in ev:
    gap[t["board"]][1] += 1
    if "GAP" in t["reason"]:
        gap[t["board"]][0] += 1
print("\nD4 SL_GAP(跳空止损)率按板块:")
gaps = {}
for b, (g, tot) in sorted(gap.items()):
    gaps[b] = round(g / tot * 100, 1)
    print(f"  {b}: {g}/{tot} = {g/tot*100:.1f}%")

valid_avgs = [s["avg"] for s in boards.values() if s.get("n", 0) >= 30]
spread_b = round(max(valid_avgs) - min(valid_avgs), 2) if len(valid_avgs) >= 2 else None
valid_px = [s["avg"] for s in pxs.values() if s.get("n", 0) >= 30]
spread_p = round(max(valid_px) - min(valid_px), 2) if len(valid_px) >= 2 else None
verdict = {
    "D1_板块分层有信息(差>2pp)": bool(spread_b is not None and spread_b > 2.0),
    "板块avg差": spread_b,
    "D2_价格分层有信息(差>2pp)": bool(spread_p is not None and spread_p > 2.0),
    "价格avg差": spread_p,
    "D3_样本不足层": [b for b, s in boards.items() if 0 < s.get("n", 0) < 30],
    "D4_SL_GAP率": gaps,
    "注": "审计§7.2建议ABCDE按市值/成交额分层——台账无此字段, 用板块+价格代理; 结论只对代理维度负责",
}
print("\n预注册:", json.dumps(verdict, ensure_ascii=False))
json.dump({"boards": boards, "px": pxs, "preregistered": verdict},
          open(r"E:\test\smc_project\research\handover\V4_股票分层落档.json", "w",
               encoding="utf-8"), ensure_ascii=False, indent=2)
print("已写 handover/V4_股票分层落档.json")