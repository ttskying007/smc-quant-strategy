# -*- coding: utf-8 -*-
"""tests_escore.py —— core/escore.py 测试(12)
覆盖: 因子无前视性/指数加载与回退/广度计算/陈旧检测/系数映射/历史复现对齐"""
import io, os, sys, json, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.escore import escore_for_date, breadth_newhigh_pct, exposure_coef, _load_index, _idx_at, _version_

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print("  OK " + name)
    else:
        FAIL += 1; print("  FAIL " + name + " | " + str(detail))

print("== 1. 模块元 ==")
ok("版本标记", _version_ == "escore_v1")

print("== 2. 指数加载与因子 ==")
sh = _load_index("SH_000001_daily.json") or _load_index("000001_SH_day.json")
ok("上证指数加载", len(sh) > 100)
r = _idx_at(sh, "20260401")
ok("_idx_at 无前视(asof≤d8)", r is not None and r["asof"] <= "20260401", str(r))
r_bad = _idx_at(sh, "19900101")
ok("数据不足返回 None", r_bad is None)

print("== 3. E-score 端到端(20260615, f1 外部注入避免全市场慢扫) ==")
e, meta = escore_for_date("20260615", f1=0.08, with_meta=True)
ok("E 计算成功", e is not None, meta)
ok("E ∈ [0,1]", 0 <= e <= 1, e)
ok("meta 含三因子", all(k in meta for k in ("f1", "f2_off_high", "f3_r20")))
ok("中证1000代理标注", meta.get("mid_proxy") in ("512100", "512100_SH", "000300"), meta.get("mid_proxy"))
ok("陈旧检测字段存在", "asof_stale" in meta)
# canonical 指数已由 pull_index_daily 刷新至最新 → 20260615 回看 asof 距离 ≤10 自然日
# (不陈旧是正确行为; 陈旧检测的真实验证: 查询日远超数据末尾)
e_far, meta_far = escore_for_date("20261231", f1=0.08, with_meta=True)
ok("陈旧检测: 远超数据末尾如实标注", meta_far.get("asof_stale") is True,
   f"asof_stale={meta_far.get('asof_stale')} stale_days={meta_far.get('mid_stale_days')}")
ok("历史日(20260615)数据新鲜", meta.get("asof_stale") is False and meta.get("mid_stale_days", 99) <= 10,
   meta)
e0 = escore_for_date("20260615", f1=0.0)
e1 = escore_for_date("20260615", f1=0.5)
ok("F1 单调性(广度越高 E 越大)", e1 > e0, f"{e0} vs {e1}")

print("== 4. 仓位系数映射(D1B: 排序降仓不杀单) ==")
ok("E 缺失→满仓(不杀单纪律)", exposure_coef(None) == 1.0)
ok("Q1 区→0.3", exposure_coef(0.20) == 0.3)
ok("中段→0.5/0.75", exposure_coef(0.40) == 0.5 and exposure_coef(0.50) == 0.75)
ok("黄金区→1.0", exposure_coef(0.60) == 1.0)

print("== 5. 广度(抽样日期, 全市场扫) ==")
f1 = breadth_newhigh_pct("20260615")
ok("F1 计算或 None(数据窗)", f1 is None or 0 <= f1 <= 1, f1)

print("\n结果: PASS=%d FAIL=%d" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)