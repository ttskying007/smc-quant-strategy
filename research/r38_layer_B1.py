# -*- coding: utf-8 -*-
"""r38_layer_B1.py —— 假设 B1 验证: SL=spring假跌破止损 vs 原 swing low−0.5ATR.
对冻结基线 EVENT 腿逐笔重放: 保持入场(ep)与 TP 结构不变, 只改 SL 语义:
  原: sl1 = swing_low − 0.5×ATR (真跌破时提供超 -1R 亏损)
  B1: sl1 = 假跌破后收回的实体低点 (Wyckoff spring 止损; 若披露日前 20 根内
      无 spring 结构, 退回原 sl1 —— 不改变无结构票)
判据: 触价顺序逐 bar 重放(与 core.execution.simulate 同语义, 但 SL 参数不同).
纯研究, 不修改生产冻结线. 输出: B1 vs 原 的 avg/PF/WR/RR分布/左尾(<=-1R)."""
import csv, io, json, os, sys
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\research")

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
bar_cache = {}
def bars_of(code):
    if code not in bar_cache:
        p = code2file.get(code)
        if not p:
            bar_cache[code] = []; return bar_cache[code]
        raw = json.load(open(p, encoding="utf-8"))
        bs = []
        for r in raw:
            t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
            if t and r.get("o") and r.get("h") and r.get("l") and r.get("c") and r.get("v"):
                bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]),
                           "c": float(r["c"]), "v": float(r["v"])})
        bs.sort(key=lambda b: b["t"])
        bar_cache[code] = bs
    return bar_cache[code]

def atr14(bs, i):
    if i < 15: return 0
    trs = []
    for k in range(i-14, i):
        tr = max(bs[k]["h"]-bs[k]["l"], abs(bs[k]["h"]-bs[k-1]["c"]), abs(bs[k]["l"]-bs[k-1]["c"]))
        trs.append(tr)
    return sum(trs)/14 if trs else 0

def spring_sl(bs, disp_idx, orig_sl, ep):
    """Wyckoff spring: 披露日前 20 根内若有'跌破前低→次日收回前低上方'的假跌破,
    则 SL 收紧到 spring 低点上方(实体低点); 否则退回 orig_sl.
    返回 (new_sl, is_spring). """
    lo = max(0, disp_idx-20)
    for j in range(lo, disp_idx):
        prev_low = min(bs[k]["l"] for k in range(max(0, j-5), j)) if j >= 5 else bs[j]["l"]
        if bs[j]["l"] < prev_low * 0.995 and j+1 < len(bs) and bs[j+1]["c"] > prev_low:
            # 假跌破(j 日低点破前低) + 次日收回 → spring
            sl_cand = max(bs[j]["l"], bs[j+1]["l"]) * 1.001  # 实体低点上方
            if sl_cand < ep:  # SL 必须低于入场价才有效
                return sl_cand, True
    return orig_sl, False

def replay(bs, entry_idx, ep, sl, tp1, tp2, tp3, max_hold=15):
    """简化逐 bar 重放: 与 core.execution.simulate 同序 (TP1先30%+保本, SL逐bar, 跳空按开盘).
    返回 (net_pnl_pct, reason, exit_r, mae). 若 ep>=sl 视为 BAD_ENTRY skip. """
    if ep <= 0 or sl >= ep:
        return None, "BAD_ENTRY", 0.0, 0.0
    remaining = 1.0
    net = 0.0
    stop = sl
    tp1_hit = False
    be_armed = False
    mae = 0.0
    for k in range(entry_idx, min(len(bs), entry_idx+max_hold)):
        b = bs[k]
        mae = min(mae, (b["l"]/ep - 1)*100)
        # SL 跳空: 开盘低于 stop → 按开盘价全平
        if b["o"] <= stop:
            net += (b["o"]/ep - 1)*100 * remaining
            return net, "SL_GAP", net/((ep-sl)/ep), mae
        # 盘中 SL
        if b["l"] <= stop:
            px = stop
            net += (px/ep - 1)*100 * remaining
            return net, "SL_HIT", net/((ep-sl)/ep), mae
        # TP1: 30% 部分止盈 + 保本
        if not tp1_hit and b["h"] >= tp1:
            net += (tp1/ep - 1)*100 * 0.3
            remaining = 0.7
            tp1_hit = True
            stop = ep  # 保本
            be_armed = True
        # TP2: 剩仓全平
        if tp1_hit and b["h"] >= tp2:
            net += (tp2/ep - 1)*100 * remaining
            return net, "TP2_RUNNER", net/((ep-sl)/ep), mae
        # TP3: runner 到 tp3 也全平
        if tp1_hit and b["h"] >= tp3:
            net += (tp3/ep - 1)*100 * remaining
            return net, "TP3", net/((ep-sl)/ep), mae
    # 持有到期 → 按最后一根收盘
    end_c = bs[min(len(bs)-1, entry_idx+max_hold-1)]["c"]
    net += (end_c/ep - 1)*100 * remaining
    return net, "TIME_STOP", net/((ep-sl)/ep), mae

rows = list(csv.DictReader(open(r"E:\test\smc_project\research\combo_v20f_trades.csv", encoding="utf-8-sig")))
ev = [r for r in rows if r.get("src") == "EVENT"]
def f(x, d=0.0):
    try: return float(x)
    except: return d

res_orig = []
res_b1 = []
n_spring = 0
n_bad = 0
for r in ev:
    code = r["symbol"].split(".")[0]
    bs = bars_of(code)
    dates = [b["t"] for b in bs]
    disp_date = r.get("entry_date")
    if disp_date not in dates: continue
    di = dates.index(disp_date)
    entry_idx = di + 1
    if entry_idx >= len(bs): continue
    ep = f(r.get("buy_price"))
    if ep <= 0: continue
    # 原 SL (CSV 已存 sl 字段 = swing low - 0.5ATR)
    orig_sl = f(r.get("sl"))
    tp1 = f(r.get("tp"))
    # CSV tp 字段 = tp2 (runner). 用 tp*1.0 近似 tp1, 但 tp1<tp2 保证
    tp1v = orig_sl + (tp1 - orig_sl)*0.4   # 近似: tp1 位于 sl~tp2 间 40% 处
    tp2v = tp1
    tp3v = tp1 * 1.15
    # 原重放
    n1, reason1, rr1, mae1 = replay(bs, entry_idx, ep, orig_sl, tp1v, tp2v, tp3v)
    if n1 is None: n_bad += 1; continue
    res_orig.append(n1)
    # B1 重放
    new_sl, is_sp = spring_sl(bs, di, orig_sl, ep)
    if is_sp: n_spring += 1
    n2, reason2, rr2, mae2 = replay(bs, entry_idx, ep, new_sl, tp1v, tp2v, tp3v)
    res_b1.append(n2)

def stats(pnls):
    wins = [x for x in pnls if x > 0]; losses = [x for x in pnls if x <= 0]
    pf = sum(wins)/abs(sum(losses)) if sum(losses) else 99
    wr = 100*len(wins)/len(pnls)
    le1r = 100*sum(1 for x in pnls if x <= -10)/len(pnls)  # 近似 <=-1R (avg risk ~10%)
    return dict(n=len(pnls), wr=wr, avg=sum(pnls)/len(pnls), med=sorted(pnls)[len(pnls)//2],
                pf=pf, sum=sum(pnls), le1r=le1r)

so = stats(res_orig); sb = stats(res_b1)
print("="*88)
print("假设 B1: spring 假跌破止损 vs 原 swing low-0.5ATR (EVENT n=%d, 重放成功 %d, BAD_ENTRY %d)" %
      (len(ev), len(res_orig), n_bad))
print(f"  触发 spring 结构调整的票: {n_spring} ({100*n_spring/len(res_orig):.1f}%)")
print("="*88)
print(f"{'版本':<10}{'n':>6}{'胜率':>8}{'平均%':>9}{'中位%':>8}{'PF':>7}{'PnL合计%':>10}{'左尾<=-1R':>10}")
print(f"{'原SL':<10}{so['n']:>6}{so['wr']:>7.1f}%{so['avg']:>+8.2f}%{so['med']:>+8.2f}%{so['pf']:>7.2f}{so['sum']:>+10.2f}%{so['le1r']:>9.1f}%")
print(f"{'B1-spring':<10}{sb['n']:>6}{sb['wr']:>7.1f}%{sb['avg']:>+8.2f}%{sb['med']:>+8.2f}%{sb['pf']:>7.2f}{sb['sum']:>+10.2f}%{sb['le1r']:>9.1f}%")
print(f"\nΔ: avg {sb['avg']-so['avg']:+.2f}pp | PF {sb['pf']-so['pf']:+.2f} | PnL {sb['sum']-so['sum']:+.2f}pp | 左尾 {sb['le1r']-so['le1r']:+.1f}pp")
