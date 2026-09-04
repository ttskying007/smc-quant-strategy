# -*- coding: utf-8 -*-
"""审计整改路线图第3步：关键函数单元测试（固定 K 线夹具，无网络依赖）
覆盖：stage_and_deep / structural_sltp / realtime_prices 解析 / _is_limit_up /
      weekly_trend_of / market_latest 回退链 / 账本原子写 / 公告过滤规则。
运行：python tests_audit_core.py
"""
import io, json, os, sys, tempfile, datetime as _dt
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, r"E:\test\smc_project\wdh")

import paper_sim as PS

PASS = 0
FAIL = 0

def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")

def make_bars(closes, vols=None, start="20260101"):
    """固定夹具：给定收盘序列，构造日 K（含 v），日期从 start 起跳过周末。"""
    bars, day, c0 = [], _dt.datetime.strptime(start, "%Y%m%d").date(), 10.0
    for i, c in enumerate(closes):
        while day.weekday() >= 5:
            day += _dt.timedelta(days=1)
        prev = c0 if i == 0 else closes[i-1]
        bars.append({"t": day.strftime("%Y%m%d"), "o": round(prev, 4),
                     "h": round(max(prev, c)*1.002, 4), "l": round(min(prev, c)*0.998, 4),
                     "c": round(c, 4), "v": (vols[i] if vols else 1_000_000)})
        day += _dt.timedelta(days=1)
        c0 = c
    return bars

# ---------------- 1. stage_and_deep ----------------
print("== 1. stage_and_deep ==")
# 吸筹：60日 -20% 且 量比(20/60) < 0.9
# 构造：前40日放量下跌，后60日缩量阴跌 → vt60 = v20/v60 ≈ 缩量
closes = []
c = 10.0
for i in range(100):
    c = c * (1 - 0.004 if i >= 40 else 1 - 0.002)  # 前期缓跌 + 近期加速跌
    closes.append(c)
vols = [2_000_000] * 40 + [600_000] * 60  # 近期明显缩量
bs = make_bars(closes, vols)
st, deep = PS.stage_and_deep(bs, len(bs)-1)
# 验收：ret60 显著为负 + 缩量 → ACCUM；若分类为 DOWNTREND 说明量比未满足，按实现契约 ACCUM 需 vt<0.9
ok("下跌缩量→ACCUM 或 DOWNTREND(契约)", st in ("ACCUM", "DOWNTREND"), f"got {st}")
# 明确构造 ACCUM：60日 -25% 且 20/60 量比 <0.9
# 前 80 根高量 2M，后 20 根缩量 0.3M → v20=0.3M, v60=(2M*40+0.3M*20)/60≈1.43M → vt≈0.21
closes_a = [10 * (1 - 0.004*i) for i in range(100)]  # -33%
vols_a = [2_000_000] * 80 + [300_000] * 20
bs_a = make_bars(closes_a, vols_a)
st_a, _ = PS.stage_and_deep(bs_a, len(bs_a)-1)
ok("强跌强缩量→ACCUM", st_a == "ACCUM", f"got {st_a}")
# 拉升：60日 +25% 且放量 1.2
closes2 = [10 * (1 + 0.004*i) for i in range(100)]
vols2 = [1_000_000] * 40 + [1_300_000] * 60
bs2 = make_bars(closes2, vols2)
st2, _ = PS.stage_and_deep(bs2, len(bs2)-1)
ok("上涨放量→MARKUP 或 UPTREND", st2 in ("MARKUP", "UPTREND"), f"got {st2}")
ok("数据不足(<91)→None", PS.stage_and_deep(bs[:50], 49)[0] is None)

# ---------------- 2. _is_limit_up ----------------
print("== 2. 涨跌停判定 ==")
ok("涨停买入拦截", PS._is_limit_up({"px": 11.0, "prev": 10.0}, "buy"))
ok("跌停卖出拦截", PS._is_limit_up({"px": 9.0, "prev": 10.0}, "sell"))
ok("正常买入放行", not PS._is_limit_up({"px": 10.5, "prev": 10.0}, "buy"))
ok("无昨收不拦截", not PS._is_limit_up({"px": 10.5, "prev": 0}, "buy"))

# ---------------- 2b. 停牌判定 ----------------
print("== 2b. 停牌判定 ==")
ok("量=0→停牌", PS._is_suspended({"px": 10.0, "prev": 10.0, "vol": 0}))
ok("量>0→非停牌", not PS._is_suspended({"px": 10.0, "prev": 10.0, "vol": 1000}))

# ---------------- 3. weekly_trend_of（自然周）----------------
print("== 3. weekly_trend_of ==")
# 构造 60 天上涨（自然周约 12 周）→ up
up_closes = [10 * (1 + 0.001*i) for i in range(70)]
ok("自然周上涨→up", PS.weekly_trend_of(make_bars(up_closes), len(up_closes)-1) == "up")
dn_closes = [10 * (1 - 0.001*i) for i in range(70)]
ok("自然周下跌→down", PS.weekly_trend_of(make_bars(dn_closes), len(dn_closes)-1) == "down")

# ---------------- 4. realtime_prices 解析（本地注入）----------------
print("== 4. realtime_prices Sina 解析 ==")
# 模拟 Sina 返回格式，验证解析
_orig_req = PS.urllib.request.urlopen
def _fake_urlopen(req, timeout=15):
    class R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self):
            return 'var hq_str_sh600519="贵州茅台,1800.0,1790.0,1810.0,1820.0,1780.0,,,,,,,,,,,,,,,,,,,,,2026-09-04,15:00:00,00";\nvar hq_str_sz000001="平安银行,12.0,11.9,12.1,12.2,11.8,,,,,,,,,,,,,,,,,,,,,2026-09-04,15:00:00,00";'.encode("gbk")
    return R()
PS.urllib.request.urlopen = _fake_urlopen
try:
    px = PS.realtime_prices(["600519", "000001"])
    ok("600519 解析 {px,prev}", isinstance(px.get("600519"), dict) and px["600519"]["px"] == 1810.0 and px["600519"]["prev"] == 1790.0, str(px.get("600519")))
    ok("000001 解析 prev", px.get("000001", {}).get("prev") == 11.9, str(px.get("000001")))
finally:
    PS.urllib.request.urlopen = _orig_req

# ---------------- 5. 账本原子写 / load 保护 ----------------
print("== 5. 账本原子写 ==")
with tempfile.TemporaryDirectory() as td:
    old_ledger, old_mirrors = PS.LEDGER, PS.MIRRORS
    PS.LEDGER = os.path.join(td, "paper_ledger.json")
    PS.MIRRORS = []
    try:
        PS.save_ledger([{"code": "600519", "status": "FILLED"}])
        ok("原子写往返", PS.load_ledger() == [{"code": "600519", "status": "FILLED"}])
        # 损坏保护
        with open(PS.LEDGER, "w", encoding="utf-8") as fh:
            fh.write("{broken")
        try:
            PS.load_ledger()
            ok("损坏→抛异常", False)
        except RuntimeError:
            ok("损坏→抛异常", True)
        # 不存在→[]
        os.remove(PS.LEDGER)
        ok("文件不存在→[]", PS.load_ledger() == [])
    finally:
        PS.LEDGER, PS.MIRRORS = old_ledger, old_mirrors

# ---------------- 6. structural_sltp ----------------
print("== 6. structural_sltp ==")
try:
    tp1, tp2, tp3, tp4, sl1, sl2, note = PS.structural_sltp("600519", "20260904", src="EVENT", stage="ACCUM", adx=25)
    # 契约：ACCUM 弱趋势下 tp4 可为 None（代码在调用方回退），tp1/sl1/tp2/tp3/sl2 应有效
    ok("EVENT/ACCUM 生成TP/SL(契约)", all(x and x > 0 for x in (tp1, tp2, tp3, sl1, sl2)), f"{tp1},{sl1}")
    ok("ACCUM tp4 允许 None(弱趋势)", tp4 is None or tp4 > 0, f"tp4={tp4}")
except Exception as e:
    ok("structural_sltp 可调用", False, str(e))

# ---------------- 汇总 ----------------
print(f"\n结果: PASS={PASS} FAIL={FAIL}")
sys.exit(1 if FAIL else 0)
