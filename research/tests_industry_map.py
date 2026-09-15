# -*- coding: utf-8 -*-
"""tests_industry_map.py —— R35(第八轮审计): A股行业映射数据源 + 行业门接线.

测试两层:
  A) 数据级: hermes/data/industry_map.json 存在/规模/格式/符号兼容;
  B) 行为级: get_industry 兼容格式、UNKNOWN fail-open、sector_counts
     计数与排除、文件缺失降级(monkeypatch 路径, 隔离生产缓存)、
     throttle_open 接真实行业桶后 MAX_SECTOR 拒绝第 4 单;
  C) 接线级: paper_sim 两处 gate 源码传真实 sector_counts(不再恒空)。
"""
import io, json, os, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} :: {detail}")

from core import industry_map as IM

print("== A1. 数据源存在与规模 ==")
MAP = os.path.normpath(os.path.join(HERE, "..", "hermes", "data", "industry_map.json"))
ok("industry_map.json 存在", os.path.exists(MAP), MAP)
rows = json.load(open(MAP, encoding="utf-8"))
ok("规模 ≥5000 股", isinstance(rows, list) and len(rows) >= 5000, f"n={len(rows)}")
mapped = [r for r in rows if str(r.get("industry") or "").strip()]
ok("有行业字段 ≥5000", len(mapped) >= 5000, f"mapped={len(mapped)}")
_ok_fields = all(r.get("symbol") for r in mapped[:100])
ok("symbol 字段齐全(抽样100)", _ok_fields)

print("== A2. 符号格式兼容 ==")
# 生产 ledger code 为 6 位纯数字; 数据源 symbol 为 '600000.SH'
sample_syms = [str(r.get("symbol")) for r in rows[:200]]
ok("数据源 symbol 格式 'NNNNNN.XX'", all("." in s and len(s.split(".")[0]) == 6
                                          for s in sample_syms if s), sample_syms[:3])

print("== B1. get_industry 行为 ==")
IM.reset_cache_for_tests()
ind_bank = IM.get_industry("600000")       # 浦发银行 → J66货币金融服务
ok("600000 → 银行业非空", ind_bank != "UNKNOWN" and len(ind_bank) > 2, ind_bank)
ok("格式兼容 '600000.SH'", IM.get_industry("600000.SH") == ind_bank)
ok("未知股 → UNKNOWN(fail-open)", IM.get_industry("999999") == "UNKNOWN")
ok("脏输入不抛异常", IM.get_industry("") == "UNKNOWN" and IM.get_industry(None) == "UNKNOWN")

print("== B2. sector_counts 计数语义 ==")
# 同行业 3 只 + 异行业 1 只 + UNKNOWN 1 只
im_coded = {}
for r in rows:
    if str(r.get("industry") or "").strip():
        im_coded[str(r.get("symbol")).split(".")[0]] = r["industry"]
inds = sorted(set(im_coded.values()))
by_ind = {}
for c, i in im_coded.items():
    by_ind.setdefault(i, []).append(c)
big_ind_name, big_ind = max(by_ind.items(), key=lambda kv: len(kv[1]))
big_set = big_ind[:4]                     # 4 只同行业
ok("测试前提: 找到 ≥4 只同行业", len(big_set) >= 4, big_ind_name)
sc = IM.sector_counts(big_set)
ok("4 同行业 → 该行业计数 4", sc.get(big_ind_name) == 4, str(sc))
sc2 = IM.sector_counts(big_set, exclude=big_set[0])
ok("exclude 排除本单(计数-1)", sc2.get(big_ind_name) == 3, str(sc2))
_mixed = [big_set[0], big_set[1], "999999"]  # 2 同行业 + 1 未知
scm = IM.sector_counts(_mixed)
ok("UNKNOWN 不归桶(只计 1 行业=2)", len(scm) == 1 and max(scm.values()) == 2, str(scm))

print("== B3. throttle_open 接行业桶(端到端) ==")
from core.portfolio import throttle_open
sc3 = IM.sector_counts(big_set[:3])         # 该行业已有 3 单
gate3 = throttle_open([False]*3, sc3, max_positions=10, max_sector=3, max_daily_opens=5)
ok("同行业已有 3 单 → 拒第 4(MAX_SECTOR)", gate3 == (False, "MAX_SECTOR"), str(gate3))
gate2 = throttle_open([False]*2, IM.sector_counts(big_set[:2]),
                      max_positions=10, max_sector=3, max_daily_opens=5)
ok("同行业 2 单 → 放行", gate2[0] is True, str(gate2))

print("== B3b. R37 000157 误拒复盘(行为级) ==")
# 09:30:15 实弹重构: live = 002655×2+688035(C39桶=3) + 600449+002801+601633(异行业)
# + 000157(C35, 候选)。R35 旧接线(传全行业桶) → MAX_SECTOR 误拒无关候选;
# R37 新语义: 只传候选股自己行业的桶 → 放行。
_r37_live = ["002655", "002655", "688035", "600449", "002801", "601633"]
_r37_cand = "000157"
_cand_ind_r37 = IM.get_industry(_r37_cand)
_full_buckets = IM.sector_counts(_r37_live, exclude=_r37_cand)
ok("R37 复盘前提: C39 桶=3(002655×2+688035)", _full_buckets.get("C39计算机、通信和其他电子设备制造业") == 3, str(_full_buckets))
_g_old = throttle_open([False]*6, _full_buckets, max_positions=10, max_sector=3, max_daily_opens=5)
ok("旧 R35 接线复现: 全行业桶 → MAX_SECTOR 误拒(无关候选)",
   _g_old == (False, "MAX_SECTOR"), str(_g_old))
_cand_bucket_r37 = {_cand_ind_r37: _full_buckets.get(_cand_ind_r37, 0)} if _cand_ind_r37 != "UNKNOWN" else {}
_g_new = throttle_open([False]*6, _cand_bucket_r37, max_positions=10, max_sector=3, max_daily_opens=5)
ok("R37 候选桶语义: 000157(C35 桶=0) → 放行", _g_new == (True, "OK"), str(_g_new))
# 单日新开修复: 6 旧仓(False)+本单 → True 数=1 < 5, 不触发 MAX_DAILY_OPEN
_g_daily = throttle_open([False]*6, {}, max_positions=10, max_sector=3, max_daily_opens=5)
ok("R37 单日新开: 旧仓 False 不计入(放行)", _g_daily == (True, "OK"), str(_g_daily))
_g_daily2 = throttle_open([True]*5, {}, max_positions=10, max_sector=3, max_daily_opens=5)
ok("单日新开真 5 → MAX_DAILY_OPEN 保持", _g_daily2 == (False, "MAX_DAILY_OPEN"), str(_g_daily2))
# MAX_POSITIONS 语义保持(当日开仓数≥10)
_g_pos = throttle_open([True]*10, {}, max_positions=10, max_sector=3, max_daily_opens=50)
ok("当日开仓 10 → MAX_POSITIONS 保持", _g_pos == (False, "MAX_POSITIONS"), str(_g_pos))

print("== B4. 数据缺失降级(fail-open) ==")
IM.reset_cache_for_tests()
_orig_exists, _orig_env = os.path.exists, os.environ.get("SMC_INDUSTRY_MAP", None)
_orig_default = IM._DEFAULT_MAP
try:
    IM._DEFAULT_MAP = os.path.join(HERE, "_no_such_map.json")   # 不存在的路径
    ok("缺文件 → UNKNOWN(不抛异常)", IM.get_industry("600000") == "UNKNOWN")
    ok("缺文件 → sector_counts 空(fail-open 放行)", IM.sector_counts(["600000", "000001"]) == {})
finally:
    IM._DEFAULT_MAP = _orig_default
    IM.reset_cache_for_tests()
    if _orig_env is None and "SMC_INDUSTRY_MAP" in os.environ:
        del os.environ["SMC_INDUSTRY_MAP"]

print("== B5. coverage 体检 ==")
_led = json.load(open(os.path.join(HERE, "paper_ledger.json"), encoding="utf-8"))
_codes = [t.get("code") for t in _led if t.get("status") in ("PENDING_ORDER", "FILLED")]
if _codes:
    cov = IM.coverage(_codes)
    ok(f"当前 live 条目覆盖率({cov['n']}单) > 0", cov["mapped"] > 0, str(cov))
else:
    ok("live 条目(空时跳过)", True)

print("== C1. 生产接线(paper_sim 源码) ==")
src = open(os.path.join(HERE, "paper_sim.py"), encoding="utf-8").read()
ok("创建前 gate 导入 sector_counts", "from core.industry_map import sector_counts as _sector_counts" in src)
ok("创建前 gate 候选桶语义(R37: 只传候选自己行业)",
   "_cand_bucket = {_cand_ind:" in src and "throttle_open(day_opens, _cand_bucket," in src)
ok("成交前 gate 候选桶语义(R37 同源修复)",
   "_cand_bucket2 = {_cand_ind2:" in src and "throttle_open(_day_opens, _cand_bucket2," in src)
ok("全行业桶直传已消除(R37 复盘 000157 误拒根因)",
   "throttle_open(day_opens, _sect," not in src
   and "throttle_open(_day_opens, _sect2," not in src)
ok("空 dict 直传已消除(仅历史注释除外)",
   src.count("throttle_open(day_opens, {},") == 0
   and src.count("throttle_open(_day_opens, {},") == 0)
ok("R35+R37 标记存在", "R35" in src and "R37" in src)

print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(0 if FAIL == 0 else 1)
