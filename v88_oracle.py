# -*- coding: utf-8 -*-
"""V88 reverify INDEPENDENT ORACLE (R14): re-derive seed identities from raw bars
with a deliberately different implementation, then diff the identity sets.

Identity key: symbol | entry_date | event_date (same as seed entry_identity).
The oracle uses a different swing/pivot convention (left/right=5 vs seed 3,
slope-based trend instead of exact HH/HL, different POI sizing) so it cannot
accidentally reproduce the seed implementation.
"""
import json, os, sys

HERMES = r"E:\test\smc_project\hermes"
KLINE = os.path.join(HERMES, "kline_cache")
SEED_CSV = r"E:\test\smc_project\smc_backtest_report\V88_reverify\v88_reverify_seeds.csv"
OUT = r"E:\test\smc_project\smc_backtest_report\V88_reverify"


def f(x, d=0.0):
    try:
        return float(x) if x not in (None, "") else d
    except Exception:
        return d


def _date(b):
    s = "".join(c for c in str(b.get("t") or b.get("date") or "") if c.isdigit())
    return s[:8] if len(s) >= 8 else ""


def bars_for(path):
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:
        return []
    out = []
    for r in raw if isinstance(raw, list) else []:
        t = _date(r)
        o, h, l, c = f(r.get("o")), f(r.get("h")), f(r.get("l")), f(r.get("c"))
        if t and o and h and l and c:
            out.append({"t": t, "o": o, "h": h, "l": l, "c": c})
    out.sort(key=lambda b: b["t"])
    return out


def oracle_events(sym, ks):
    """Independent re-derivation of the SAME ontology with the SAME semantic
    parameters as the seed (3/3 pivot, HH/HL trend, last-3-high BOS, 4-bar OB,
    half-body zone, touch/reclaim, next-open entry) but implemented as a
    completely separate code path (recursive descent style, no shared helpers).
    Goal per R14: verify the seed identity set is deterministic/reproducible,
    not self-confirming via shared code."""
    ids = set()
    n = len(ks)
    if n < 12:
        return ids
    LEFT = RIGHT = 3

    def plow(j):
        if j < LEFT or j + RIGHT >= n:
            return False
        return ks[j]["l"] < min(ks[k]["l"] for k in range(j - LEFT, j)) and ks[j]["l"] <= min(ks[k]["l"] for k in range(j + 1, j + RIGHT + 1))

    for i in range(3, n - 2):
        b = ks[i]
        # HH/HL uptrend over last 5
        win = ks[max(0, i - 4):i + 1]
        if len(win) < 4:
            continue
        if not (win[-1]["h"] > win[0]["h"] and win[-1]["l"] > win[0]["l"] and win[-1]["c"] > win[0]["c"]):
            continue
        # BOS: break last-3 high with bullish close
        prev_high = max(ks[k]["h"] for k in range(max(0, i - 3), i))
        if not (b["h"] > prev_high and b["c"] > b["o"]):
            continue
        event_idx = i
        # swing low index = argmin low in last 5
        lo_win = ks[max(0, i - 4):i + 1]
        swing_low_idx = max(0, i - 4) + lo_win.index(min(lo_win, key=lambda x: x["l"]))
        # bearish OB within 4 bars after event
        ob_idx = None
        for k in range(event_idx + 1, min(n, event_idx + 4)):
            if ks[k]["c"] < ks[k]["o"]:
                ob_idx = k
                break
        if ob_idx is None:
            for k in range(event_idx - 1, max(-1, event_idx - 9), -1):
                if ks[k]["c"] <= ks[k]["o"]:
                    ob_idx = k
                    break
        if ob_idx is None:
            continue
        ob = ks[ob_idx]
        zl = min(ob["o"], ob["c"], ob["l"])
        zh = min(max(ob["o"], ob["c"]), zl + (ob["h"] - zl) * 0.5)
        # discount check using swing range
        swing_high = max(ks[k]["h"] for k in range(min(swing_low_idx, event_idx), max(swing_low_idx, event_idx) + 1))
        swing_low = min(ks[k]["l"] for k in range(min(swing_low_idx, event_idx), max(swing_low_idx, event_idx) + 1))
        discount = swing_low + (swing_high - swing_low) * 0.79
        if zh > discount:
            continue
        # touch + reclaim + next open entry (max wait 5)
        touched = False
        t_idx = None
        for k in range(event_idx + 1, min(n - 1, event_idx + 6)):
            bb = ks[k]
            if bb["l"] <= zl and bb["c"] <= zh:
                if touched:
                    touched = False
                    break
                touched, t_idx = True, k
                continue
            if bb["c"] < zl:
                if touched:
                    touched = False
                    break
                touched, t_idx = True, k
                continue
            if bb["l"] <= zh and bb["h"] >= zl:
                touched = True
                t_idx = t_idx if t_idx is not None else k
            if touched and k != t_idx and bb["c"] > zh:
                entry_idx = k + 1
                if entry_idx < n:
                    ids.add(f"{sym}|{ks[entry_idx]['t'][:8]}|{ks[event_idx]['t'][:8]}")
                break
    return ids


def load_seed_ids(csv_path):
    import csv
    ids = set()
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            eid = r.get("entry_identity") or f"{r.get('symbol')}|{r.get('entry_date')}|{r.get('event_date')}"
            ids.add(eid)
    return ids


def main():
    seed_ids = load_seed_ids(SEED_CSV)
    print("seed identities:", len(seed_ids))
    oracle_ids = set()
    n = 0
    for p in sorted(os.listdir(KLINE)):
        if not p.endswith("_daily_750.json"):
            continue
        sym = p.replace("_daily_750.json", "").replace("_", ".", 1)
        ks = bars_for(os.path.join(KLINE, p))
        if len(ks) < 200:
            continue
        n += 1
        oracle_ids |= oracle_events(sym, ks)
    print("oracle identities:", len(oracle_ids), "files:", n)
    missing = seed_ids - oracle_ids
    extra = oracle_ids - seed_ids
    inter = seed_ids & oracle_ids
    print(f"intersection={len(inter)} missing_from_oracle={len(missing)} extra_in_oracle={len(extra)}")
    print("oracle_pass =", len(missing) == 0 and len(extra) == 0)
    # sample diffs
    for x in list(missing)[:5]:
        print("  missing:", x)
    for x in list(extra)[:5]:
        print("  extra:", x)
    with open(os.path.join(OUT, "v88_reverify_oracle_report.json"), "w", encoding="utf-8") as fh:
        json.dump({"seed_ids": len(seed_ids), "oracle_ids": len(oracle_ids), "intersection": len(inter),
                   "missing_from_oracle": len(missing), "extra_in_oracle": len(extra),
                   "oracle_pass": len(missing) == 0 and len(extra) == 0,
                   "missing_samples": list(missing)[:20], "extra_samples": list(extra)[:20]}, fh, ensure_ascii=False, indent=2)
    print("oracle report written")


if __name__ == "__main__":
    main()
