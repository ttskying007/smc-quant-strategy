# -*- coding: utf-8 -*-
"""STANDARD execution-quality audit (run for EVERY iteration, per user requirement).
Checks: entry reasonableness (bought early/high?), exit reasonableness (sold early/late?).
Usage: python exec_quality_audit.py [--smc] [--event] [--version v13]
Output: exec_quality_report.json + console summary"""
import argparse, csv, glob, io, json, os, sqlite3, sys
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, r"E:\test\smc_project\wdh")
import wdh_engine as we

KT = r"E:\test\smc_project\hermes\kline_cache_tencent"
OUT = r"E:\test\smc_project\research\exec_quality_report.json"


def bars(path):
    try:
        raw = json.load(open(path, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = "".join(c for c in str(r.get("t") or "") if c.isdigit())[:8]
        o, h, l, c, v = we.f(r.get("o")), we.f(r.get("h")), we.f(r.get("l")), we.f(r.get("c")), we.f(r.get("v"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": v})
    out.sort(key=lambda b: b["t"])
    return out


def med(vals):
    if not vals:
        return None
    s = sorted(vals)
    return s[len(s) // 2]


def audit_smc():
    """SMC leg entry/exit quality."""
    stats = {"n": 0, "entry_zone": [0, 0, 0], "mae5": [], "mfe_after_tp": [], "sl_rebound": [], "time_after": []}
    bar_cache = {}
    def get_bars(sym):
        if sym not in bar_cache:
            bar_cache[sym] = bars(os.path.join(KT, sym.replace(".", "_") + "_daily_800.json"))
        return bar_cache[sym]
    n = 0
    for p in sorted(os.listdir(KT)):
        if not p.endswith("_daily_800.json"):
            continue
        n += 1
        daily = bars(os.path.join(KT, p))
        if len(daily) < 400:
            continue
        sym = p.replace("_daily_800.json", "").replace("_", ".", 1)
        for sd in we.build_seeds(sym, daily):
            r20 = sd.get("r20")
            if r20 == "" or r20 is None or not (0 <= float(r20) < 0.15):
                continue
            entry_idx = int(sd["entry_idx"])
            if entry_idx < 61:
                continue
            w60 = daily[entry_idx - 60:entry_idx]
            ret60 = w60[-1]["c"] / w60[0]["c"] - 1
            if ret60 <= 0:
                continue  # UPTREND/MARKUP proxy
            ep = we.f(sd["entry_price"])
            zl, zh = we.f(sd["zone_low"]), we.f(sd["zone_high"])
            stats["n"] += 1
            if zl <= ep <= zh:
                stats["entry_zone"][0] += 1
            elif ep < zl:
                stats["entry_zone"][1] += 1
            else:
                stats["entry_zone"][2] += 1
            mae = min((daily[k]["l"] / ep - 1) * 100 for k in range(entry_idx + 1, min(len(daily), entry_idx + 6)))
            stats["mae5"].append(mae)
            tr = we.replay_tp2(sd, daily)
            if not tr:
                continue
            ex_i = min(entry_idx + int(tr["hold_bars"]), len(daily) - 1)
            reason = tr.get("reason")
            if reason in ("TP2_RUNNER", "BE"):
                stats["mfe_after_tp"].append(max((daily[k]["h"] / daily[ex_i]["c"] - 1) * 100 for k in range(ex_i + 1, min(len(daily), ex_i + 6))))
            elif reason == "SL_HIT":
                stats["sl_rebound"].append(max((daily[k]["h"] / daily[ex_i]["c"] - 1) * 100 for k in range(ex_i + 1, min(len(daily), ex_i + 6))))
            elif reason == "TIME_STOP":
                stats["time_after"].append(max((daily[k]["h"] / daily[ex_i]["c"] - 1) * 100 for k in range(ex_i + 1, min(len(daily), ex_i + 6))))
        if n % 2000 == 0:
            print(f"  smc {n} files", flush=True)
    res = {
        "n": stats["n"],
        "entry_inside_zone_pct": round(100 * stats["entry_zone"][0] / stats["n"], 1) if stats["n"] else 0,
        "entry_below_zone_pct": round(100 * stats["entry_zone"][1] / stats["n"], 1) if stats["n"] else 0,
        "entry_above_zone_pct": round(100 * stats["entry_zone"][2] / stats["n"], 1) if stats["n"] else 0,
        "mae5_med_pct": round(med(stats["mae5"]), 2),
        "mfe_after_tp_med_pct": round(med(stats["mfe_after_tp"]), 2),
        "sl_rebound_med_pct": round(med(stats["sl_rebound"]), 2),
        "time_exit_after_med_pct": round(med(stats["time_after"]), 2),
    }
    print(f"=== SMC 腿执行质量 ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
    return res


def audit_event(limit=3000):
    """Event leg entry/exit quality."""
    conn = sqlite3.connect(r"E:\test\smc_project\announce\smc_announce.db")
    cur = conn.cursor()
    code2file = {f.split("_")[0]: os.path.join(KT, f) for f in os.listdir(KT) if f.endswith("_daily_800.json")}
    bar_cache = {}
    def bars_of(code):
        if code not in bar_cache:
            p = code2file.get(code)
            if not p:
                bar_cache[code] = []
                return bar_cache[code]
            raw = json.load(open(p, encoding="utf-8"))
            bs = []
            for r in raw:
                t = "".join(x for x in str(r.get("t") or "") if x.isdigit())[:8]
                if t and r.get("o") and r.get("h") and r.get("l") and r.get("c"):
                    bs.append({"t": t, "o": float(r["o"]), "h": float(r["h"]), "l": float(r["l"]), "c": float(r["c"])})
            bs.sort(key=lambda b: b["t"])
            bar_cache[code] = bs
        return bar_cache[code]
    def is_strong(title):
        t = str(title or "")
        if "回购" in t:
            if "完成" in t or "进度" in t or "进展" in t or "结果" in t or "前十名" in t:
                return False
            return True
        if "增持" in t:
            return True
        return False
    stats = {"n": 0, "gap": [], "day_low": [], "exit_vs_peak": [], "hold_best": defaultdict(int)}
    cur.execute("SELECT date, stock_code, title FROM announce WHERE title LIKE '%增持%' OR title LIKE '%回购%'")
    seen = set()
    cnt = 0
    for date, code, title in cur.fetchall():
        if not is_strong(title):
            continue
        d = str(date)[:10].replace("-", "")
        if (code, d) in seen:
            continue
        seen.add((code, d))
        bs = bars_of(code)
        if not bs:
            continue
        dates = [b["t"] for b in bs]
        nxt = [x for x in dates if x > d]
        if not nxt:
            continue
        i = dates.index(nxt[0])
        if i + 15 >= len(bs) or i == 0:
            continue
        ep = bs[i]["o"]
        if ep <= 0:
            continue
        stats["n"] += 1
        stats["gap"].append((ep / bs[i - 1]["c"] - 1) * 100)
        stats["day_low"].append((bs[i]["l"] / ep - 1) * 100)
        ex = bs[i + 10]["c"]
        stats["exit_vs_peak"].append((max(bs[k]["h"] for k in range(i + 11, min(len(bs), i + 16))) / ex - 1) * 100)
        best = max((5, 10, 15), key=lambda h: (bs[i + h]["c"] / ep - 1))
        stats["hold_best"][best] += 1
        cnt += 1
        if cnt >= limit:
            break
    conn.close()
    res = {
        "n": stats["n"],
        "entry_gap_med_pct": round(med(stats["gap"]), 2),
        "entry_day_low_med_pct": round(med(stats["day_low"]), 2),
        "exit_vs_peak_med_pct": round(med(stats["exit_vs_peak"]), 2),
        "hold_best_dist": {str(k): v for k, v in sorted(stats["hold_best"].items())},
    }
    print(f"=== 事件腿执行质量 ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smc", action="store_true")
    ap.add_argument("--event", action="store_true")
    args = ap.parse_args()
    report = {}
    if args.smc:
        report["smc"] = audit_smc()
    if args.event:
        report["event"] = audit_event()
    if report:
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\n报告已保存: {OUT}")
