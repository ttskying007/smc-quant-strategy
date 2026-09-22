# -*- coding: utf-8 -*-
"""sim_trailing_r71.py — R71: 用真实日K回放验证 S2 trailing 改进
方法:
 - 只对 EVENT 腿(buy/sell 完整); CONT 腿缺 fill 字段, 略过
 - 每腿: 以 buy_date/buy_price 入场, tp/sl/hold 来自腿记录
 - 三种规则回放:
    base : 原始 (touch sl → sl价出, touch tp → tp价出, 12bar → 收盘出)
    T8   : 高线破 entry*1.08 → 半仓锁定 @ entry*1.08, 剩半仓 stop 拉到 breakeven
    T10  : entry*1.10 锁定, 剩半仓 stop 拉到 +4%
 - 对每腿计算出金 vs 真实 v22 pnl:
    两个口径:
      (a) replay_base 与 recorded 差异(回放引擎一致性检查)
      (b) replay_T8 与 replay_base 的差异(就是 trailing 增益的可答性)
 - 一致性: 优先 K线 t 精确, 找不到该 symbol 的 cache 文件 → 略腿
"""
import csv, os, json, sys, io
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = os.path.dirname(os.path.abspath(__file__))
LEGS = os.path.join(ROOT, "combo_v22_trades.csv")
KC_DIR = os.path.normpath(os.path.join(ROOT, "..", "hermes", "kline_cache_tencent"))
HOLD_NB = 12  # TIME_STOP 实际中位拿出数据里 h=12 cache 验证


def sym_to_file(sym):
    s = sym.replace(".", "_")
    if "_SZ" not in s and "_SH" not in s and "_BJ" not in s:
        if s.startswith("6") or s.startswith("9"):
            s += "_SH"
        elif s.startswith("4") or s.startswith("8"):
            s += "_BJ"
        else:
            s += "_SZ"
    return os.path.join(KC_DIR, s + "_daily_800.json")


def load_bars(sym):
    p = sym_to_file(sym)
    if not os.path.exists(p):
        return None
    try:
        d = json.load(open(p, encoding="utf-8"))
        return [(b["t"], float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])) for b in d]
    except Exception:
        return None


def replay(bars, entry, tp, sl, lock=None, lock_to=None, hold=HOLD_NB):
    """从首个 date >= buy_date 的 bar 开始持有, 挂买卖模拟"""
    # 入场后: 从 entry 后的第一根 bar 起算
    seen_entry = False
    for i, (t, o, h, l, c) in enumerate(bars):
        if not seen_entry:
            seen_entry = True
            continue  # buy_date 当天不计
        step = i - 0
        # 止损/止盈
        if lock is not None:
            # trailing 逻辑: 盘高过 entry*lock 值 → 半仓锁, 余半仓止损抬到 entry*lock_to
            pass
        if sl and l <= sl:
            return sl, t, "SL"
        if tp and h >= tp:
            return tp, t, "TP"
        if step >= hold:
            return c, t, "TIME"
    return bars[-1][4], bars[-1][0], "EOD"


def replay_trailing(bars, entry, tp, sl, lock_level, half_stop, hold=HOLD_NB):
    """更仔细的半仓版: 旧半仓尾随基线 bp(可上调), 新半仓已锁死"""
    seen_entry = False
    locked_half_done = False
    locked_price = 0.0
    trail_stop = sl  # 未触锁时, 全部持仓用原 sl
    for i, (t, o, h, l, c) in enumerate(bars):
        if not seen_entry:
            seen_entry = True
            continue
        # Step A: 锁线
        if not locked_half_done and h >= entry * lock_level:
            locked_half_done = True
            locked_price = entry * lock_level
            trail_stop = max(trail_stop, entry * half_stop)  # 剩半仓的底线
        # Step B: 停/止结算 (剩余仓位)
        if trail_stop and l <= trail_stop:
            rest_px = trail_stop
            # 组合收益: 半仓锁(如果已锁) + 半仓走 stop
            avg_px = 0.5 * (locked_price if locked_half_done else rest_px) + 0.5 * rest_px
            return avg_px, t, "TRAIL_STOP"
        if tp and h >= tp:
            rest_px = tp
            avg_px = 0.5 * (locked_price if locked_half_done else tp) + 0.5 * tp
            return avg_px, t, "TRAIL_TP"
        if i >= hold:
            avg_px = 0.5 * (locked_price if locked_half_done else c) + 0.5 * c
            return avg_px, t, "TRAIL_TIME"
    last = bars[-1][4]
    avg = 0.5 * (locked_price if locked_half_done else last) + 0.5 * last
    return avg, bars[-1][0], "TRAIL_EOD"


def avg_list(nums):
    return sum(nums) / max(len(nums), 1)


def fmt(rs):
    return f"n={len(rs)} avg={avg_list([x[0] - 1 for x in rs])*100:+.2f}%"


def main():
    legs = []
    for r in csv.DictReader(open(LEGS, encoding="utf-8-sig")):
        if not (r.get("buy_date") and r.get("buy_price")):
            continue
        if r.get("src") != "EVENT":
            continue
        try:
            entry = float(r["buy_price"]); tp = float(r.get("tp") or 0) or None
            sl = float(r.get("sl") or 0) or None
        except Exception:
            continue
        legs.append({"symbol": r["symbol"], "buy_date": r["buy_date"], "entry": entry, "tp": tp, "sl": sl,
                     "recorded_pnl": float(r["net_pnl_pct"] or 0) / 100})
    print(f"回放腿数: {len(legs)} EVENT")

    cache = {}
    diffs_base_v22, diffs_T8_base, diffs_T10_base = [], [], []
    skipped = 0
    for lg in legs:
        if lg["symbol"] not in cache:
            cache[lg["symbol"]] = load_bars(lg["symbol"])
        bars = cache[lg["symbol"]]
        if not bars:
            skipped += 1
            continue
        # 截断到 buy_date 之后的部分
        idx = next((i for i, b in enumerate(bars) if b[0] >= lg["buy_date"]), None)
        if idx is None:
            skipped += 1
            continue
        seg = bars[idx:]
        # 一致性校验: 先跑 base
        b_px, b_dt, b_why = replay(seg, lg["entry"], lg["tp"], lg["sl"])
        t8_px, t8_dt, t8_why = replay_trailing(seg, lg["entry"], lg["tp"], lg["sl"],
                                                lock_level=1.08, half_stop=1.0)
        t10_px, t10_dt, t10_why = replay_trailing(seg, lg["entry"], lg["tp"], lg["sl"],
                                                  lock_level=1.10, half_stop=1.04)
        r_base = b_px / lg["entry"]
        r_t8 = t8_px / lg["entry"]
        r_t10 = t10_px / lg["entry"]
        diffs_base_v22.append((r_base - 1) - lg["recorded_pnl"])  # 一致性偏差
        diffs_T8_base.append(r_t8 - r_base)
        diffs_T10_base.append(r_t10 - r_base)

    print(f"回放跳过={skipped}腿(缺cache或buy_date不命中)")
    print()
    print("| 口径 | 平均差 | 中位差 | 直接读数 |")
    print("|---|---|---|---|")
    def _st(ds, name):
        ds = sorted(ds)
        avg_d = sum(ds) / len(ds) * 100
        med = ds[len(ds) // 2] * 100
        print(f"| {name} | {avg_d:+.3f}pp | {med:+.3f}pp | n={len(ds)} |")
    _st(diffs_base_v22, "回放base - 真实pnl (一致性检查, 应接近0)")
    _st(diffs_T8_base, "T8 trailing - 回放base (增益)")
    _st(diffs_T10_base, "T10 trailing - 回放base (增益)")


if __name__ == "__main__":
    main()
