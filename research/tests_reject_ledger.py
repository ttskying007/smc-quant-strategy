# -*- coding: utf-8 -*-
"""tests_reject_ledger.py —— R5 拒绝账本+漏斗三分解+前向收益评估器 测试库(2026-09-13)。
覆盖: ①_tri_decompose 守恒 ②_persist_rejects 去重/追加/上限/原子性 ③eval_one 纯函数
(前瞻收益/MFE/MAE/TP/SL/SL优先) ④evaluate 分层汇总+DUP跳过 ⑤预注册判定方向。"""
import io, json, os, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 注意: reject_forward_eval 模块级会重包 sys.stdout(utf-8), 本测试库不重复包
# (双重 wrapper 会让先建的一层被 GC 关闭 → ValueError: I/O operation on closed file)
import paper_sim  # noqa: E402
from reject_forward_eval import eval_one, evaluate, _avg_vs_pass, FWD_DAYS  # noqa: E402

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " " + str(detail))

def mkbars(c=10.0, n=30, vol=1.0):
    """n 根日线: 精确几何级数 c[k]=c*1.01^(k+1)(6dp, 无逐bar取整漂移);
    o=c[k-1](前收), h=c[k]*1.02, l=o*0.98。"""
    bs = []
    for k in range(n):
        o = round(c * (1.01 ** k), 6)
        cc = round(c * (1.01 ** (k + 1)), 6)
        bs.append({"t": f"202601{k+1:02d}",
                   "o": o, "h": round(cc * 1.02, 6), "l": round(o * 0.98, 6), "c": cc, "v": vol})
    return bs

print("== 1. 三分解守恒 (_tri_decompose) ==")
tri = paper_sim._tri_decompose(raw=162, hard=100, soft=15, soft_delta=0, skipped_stage=30,
                               skipped_adx=12, nodata=4, dup=1, orders=0)
ok("source_supply=raw", tri["source_supply"] == 162)
ok("quality_reject=分类+阶段+ADX", tri["quality_reject"] == 100 + 15 + 0 + 30 + 12)
ok("守恒: raw=quality+data_missing+dup+orders",
   tri["source_supply"] == tri["quality_reject"] + tri["data_missing"] + tri["execution_capacity"]["dup"] + tri["orders_created"])
tri2 = paper_sim._tri_decompose(100, 60, 10, 5, 20, 3, 2, 0, 0)
ok("守恒(第二组)", 100 == tri2["quality_reject"] + 2 + 0 + 0)

print("== 2. 拒绝账本持久化 (_persist_rejects) ==")
with tempfile.TemporaryDirectory() as td:
    fp = os.path.join(td, "reject_ledger.json")
    r1 = [{"code": "000001", "date": "2026-09-10", "stage": "ADX_LT20", "title": "x"},
          {"code": "000002", "date": "2026-09-10", "stage": "STAGE_MARKUP", "title": "y"}]
    n1 = paper_sim._persist_rejects(r1, root=td)
    ok("首次写入 2 条", n1 == 2)
    # 重复写同记录 → 去重
    n2 = paper_sim._persist_rejects(r1, root=td)
    ok("同记录去重不增", n2 == 2)
    # 同(code,date)阶段变迁 → 新增(保留两条)
    r3 = r1 + [{"code": "000001", "date": "2026-09-10", "stage": "STAGE_MARKUP", "title": "x2"}]
    n3 = paper_sim._persist_rejects(r3, root=td)
    ok("阶段变迁追加为3", n3 == 3)
    data = json.load(open(fp, encoding="utf-8"))
    ok("date 规范化为 d8", all(len(str(r["date"])) == 8 for r in data))
    ok("ts 字段存在", all("ts" in r for r in data))
    # 上限裁剪
    many = [{"code": f"{i:06d}", "date": "20260910", "stage": "ADX_LT20", "title": "z"} for i in range(300)]
    paper_sim._persist_rejects(many, root=td, cap=50)
    data2 = json.load(open(fp, encoding="utf-8"))
    ok("cap 裁剪至最近50", len(data2) == 50)
    # 坏 JSON 场景 → 当作空列表重建(不抛)
    open(fp, "w").write("{{{broken")
    n5 = paper_sim._persist_rejects(r1, root=td)
    ok("坏账本重建不抛", n5 == 2)

print("== 3. eval_one 纯函数 ==")
bs = mkbars(c=10.0)
ev = eval_one(bs, "20260101")  # 基准日收盘 10*1.01=10.10
ok("基准=signal收盘", abs(ev["ref"] - 10.10) < 1e-6)
ok("回退带=+3%/-4%", ev["band"] == (round(10.10 * 1.03, 3), round(10.10 * 0.96, 3)))
# 手算: win=bs[1:21], fwdH = bs[H].c/ref - 1 = 1.01^(H+1)/1.01 - 1 = 1.01^H - 1
ok("fwd5 精确", ev["fwd5"] == round(1.01 ** 5 - 1, 4), ev["fwd5"])
ok("fwd10 精确", ev["fwd10"] == round(1.01 ** 10 - 1, 4), ev["fwd10"])
ok("fwd20 精确", ev["fwd20"] == round(1.01 ** 20 - 1, 4), ev["fwd20"])
ok("满窗口标记", ev["fwd_full_window"] is True)
# MFE/MAE: win = bs[1:21](索引1..20), h_max = c[20]*1.02; l_min = l[1] = o[1]*0.98 = ref*0.98
ok("MFE 相对基准", ev["mfe"] == round(10.0 * (1.01 ** 21) * 1.02 / 10.10 - 1, 4), ev["mfe"])
ok("MAE 相对基准", ev["mae"] == round(10.10 * 0.98 / 10.10 - 1, 4), ev["mae"])
# 基准日不在K线 → None
ok("基准日缺失返回None", eval_one(bs, "20251111") is None)
# 不足满窗 → partial 标记
ev_p = eval_one(bs[:12], "20260101")
ok("部分窗口 fwd20=None 但 fwd5/fwd10 有值", ev_p["fwd20"] is None and ev_p["fwd5"] is not None and ev_p["fwd_full_window"] is False)
# TP/SL: 构造先跌穿 SL 再涨穿 TP 的序列 → sl_first
seq = [{"t": f"2026020{k+1:02d}", "o": 10, "h": 10.5, "l": 9.8, "c": 10, "v": 1}] if False else [
    {"t": "20260201", "o": 10, "h": 10.4, "l": 9.5, "c": 9.6, "v": 1},   # bar1 触 SL(9.696)
    {"t": "20260202", "o": 9.6, "h": 10.6, "l": 9.6, "c": 10.5, "v": 1},  # bar2 触 TP(10.403)
    {"t": "20260203", "o": 10.5, "h": 10.7, "l": 10.4, "c": 10.6, "v": 1},
]
base_bar = {"t": "20260131", "o": 10, "h": 10.1, "l": 9.95, "c": 10.10, "v": 1}
ev2 = eval_one([base_bar] + seq, "20260131")
ok("先SL后TP → sl_first", ev2["sl_hit"] and ev2["tp1_hit"] and ev2["sl_first"])
# 同 K 双触 → SL 优先(bar2 h>=tp 且 l<=sl)
seq2 = [
    {"t": "20260201", "o": 10, "h": 10.6, "l": 9.4, "c": 10, "v": 1},  # 同bar双触
]
ev3 = eval_one([base_bar] + seq2, "20260131")
ok("同K双触 sl_first(SL优先)", ev3["sl_first"])
# 显式带
ev4 = eval_one([base_bar] + seq, "20260131", tp1=10.5, sl1=9.9)
ok("显式带覆盖回退带", ev4["band"] == (10.5, 9.9))

print("== 4. evaluate 分层汇总 ==")
recs = [
    {"code": "000001", "date": "20260101", "stage": "ADX_LT20", "ts": "1"},
    {"code": "000002", "date": "20260101", "stage": "ADX_LT20", "ts": "1"},
    {"code": "000003", "date": "20260101", "stage": "STAGE_MARKUP", "ts": "1"},
    {"code": "000001", "date": "20260101", "stage": "STAGE_MARKUP", "ts": "2"},  # 变迁: 取 ts 更大
    {"code": "000099", "date": "20260101", "stage": "DUP_EXISTING", "ts": "1"},  # 跳过评估但计数
    {"code": "000098", "date": "20260101", "stage": "ADX_LT20", "ts": "1"},      # 无K线 → unavailable
    {"code": "000004", "date": "20260101", "stage": "ADX_LT20", "ts": "1"},      # 有K线 → avail
]
def fake_bars(code):
    return mkbars() if code in ("000001", "000002", "000003", "000004") else None
agg = evaluate(recs, bars_of=fake_bars, band_for=lambda bs, i, c, d: (None, None))
ok("total_n=6(去重后)", agg["total_n"] == 6)
ok("ADX层 n=3 avail=2(000098无K线)", agg["per_stage"]["ADX_LT20"]["n"] == 3 and agg["per_stage"]["ADX_LT20"]["evaluable"] == 2,
   (agg["per_stage"]["ADX_LT20"]["n"], agg["per_stage"]["ADX_LT20"]["evaluable"]))
ok("000001 阶段变迁 → MARKUP 层", agg["per_stage"]["ADX_LT20"]["n"] == 3 and agg["per_stage"]["STAGE_MARKUP"]["n"] == 2)
ok("DUP 计数不评估", agg["per_stage"]["DUP_EXISTING"]["n"] == 1 and agg["per_stage"]["DUP_EXISTING"]["evaluable"] == 0)
ok("无K线 → unavailable=1", agg["unavailable"] == 1)
ok("fwd 均值/样本数成对", agg["per_stage"]["ADX_LT20"]["fwd_avg"]["h20"] == round(1.01 ** 20 - 1, 4)
   and agg["per_stage"]["ADX_LT20"]["fwd_n"]["h20"] == 2)

print("== 5. 预注册判定方向 (_avg_vs_pass) ==")
ok("差>2% → rejected_better", _avg_vs_pass(0.06, 0.03).startswith("rejected_better"))
ok("差<-2% → rejected_worse", _avg_vs_pass(0.01, 0.06).startswith("rejected_worse"))
ok("|差|<=2% → comparable", _avg_vs_pass(0.05, 0.04) == "comparable")
ok("缺数据 → insufficient", _avg_vs_pass(None, 0.03) == "insufficient_data")

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)