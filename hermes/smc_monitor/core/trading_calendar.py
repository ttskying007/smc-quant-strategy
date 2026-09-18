# -*- coding: utf-8 -*-
"""交易日历模块（第七轮审计 P1 清单第 3 项, 2026-09-13）。

单一权威: 从腾讯个股日线缓存(全市场 4662 只, 覆盖至最新交易日)聚合出
"至少 N 只股票当日有 bar" 的交易日集合; 缺文件的日期回退周末规则
(周六/周日休市; 法定节假日由数据源对齐 —— 若交易所开市而个股缓存
尚未更新, 当日不出现在日历, 行为等同"数据未就绪日", fail-closed)。

用途(替代自然日近似):
  - PENDING TTL: valid_from 后 N 个交易日未成交 → EXPIRED
  - CONT/事件腿持有期: 交易日 bar 计数
  - T+1/valid_from: 下一交易日推算

接口:
  td_set()            -> set[str] 全部交易日('YYYYMMDD')
  is_td(d8)           -> bool
  next_td(d8)         -> str | None       严格 > d8 的下一交易日
  prev_td(d8)         -> str | None       严格 < d8 的上一交易日
  add_td_days(d8, n)  -> str | None       d8 起(含)第 n 个交易日; n=0 → d8(若为交易日)
  td_between(a, b)    -> int              [a,b] 闭区间内交易日数(无序自动交换)
  asof_latest()       -> str              日历最新交易日

缓存: 模块级 _CAL, 进程内一次加载(~1.5s 首次); 文件缺失/解析失败回退
周末日历(仅周末规则, 无节假日 —— 调用方应优先保证缓存就绪)。
"""
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config as CFG

_CAL = None          # set[str] 交易日集合
_LATEST = None       # str 最新交易日
# 聚合阈值: 当日有 bar 的抽样文件数 >= 抽样总数 60% 才算交易日
# (停牌/坏文件 ~5-10%, 60% 有充分余量; 固定绝对值会在抽样数 < 阈值时
#  全量失效 → 悄然回退周末日历, 春节等节假日错判为交易日 —— R3 冒烟发现)
_MIN_FRAC_PER_DAY = 0.60


def _load():
    global _CAL, _LATEST
    if _CAL is not None:
        return
    cal = {}
    kt = CFG.KT_CACHE
    n_files = 0
    try:
        files = sorted(f for f in os.listdir(kt) if f.endswith("_daily_800.json"))
        # 抽样上限 ~400 只足以覆盖全市场开市日(全量 4662 只逐一解析太慢)
        step = max(1, len(files) // 400)
        sampled = files[::step]
        n_files = len(sampled)
        for f in sampled:
            try:
                raw = json.load(open(os.path.join(kt, f), encoding="utf-8"))
                for b in raw if isinstance(raw, list) else []:
                    t = "".join(c for c in str(b.get("t") or "") if c.isdigit())[:8]
                    if len(t) == 8:
                        cal[t] = cal.get(t, 0) + 1
            except Exception:
                continue
    except Exception:
        cal = {}
    _thr = max(30, int(n_files * _MIN_FRAC_PER_DAY))
    days = {d for d, n in cal.items() if n >= _thr}
    if not days:
        # 回退: 周末日历(2023-01-01 起连续生成到今日, 仅排除周六周日)
        from datetime import date, timedelta
        d0, d1 = date(2023, 1, 1), date.today()
        days, d = set(), d0
        while d <= d1:
            if d.weekday() < 5:
                days.add(d.strftime("%Y%m%d"))
            d += timedelta(days=1)
    _CAL = days
    _LATEST = max(days) if days else None


def td_set():
    _load()
    return _CAL


def is_td(d8):
    _load()
    return str(d8) in _CAL


def _is_fwd_td(s, d_obj):
    """前向外推判定: 缓存覆盖期内的日期用真实日历; 超过 asof_latest 的未来日
    按周末规则(法定节假日未知 → 视为交易日)。影响方向保守: TTL 会略早触发,
    撮合侧不用日历(用实时快照 today), 外推不影响成交判定。"""
    _load()
    if _LATEST is None or s <= _LATEST:
        return s in _CAL
    return d_obj.weekday() < 5


def next_td(d8):
    _load()
    from datetime import date, timedelta
    d = date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
    for _ in range(30):  # 最长春节休市 ~11 天
        d += timedelta(days=1)
        s = d.strftime("%Y%m%d")
        if _is_fwd_td(s, d):
            return s
    return None


def prev_td(d8):
    _load()
    from datetime import date, timedelta
    d = date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
    for _ in range(30):
        d -= timedelta(days=1)
        s = d.strftime("%Y%m%d")
        if s in _CAL:
            return s
    return None


def add_td_days(d8, n):
    """d8 起(含)第 n 个交易日。n=0 → d8 本身(若为交易日, 否则 None);
    n>0 → 顺推; n<0 → 回推。d8 无需是交易日。"""
    _load()
    from datetime import date, timedelta
    if n == 0:
        return d8 if str(d8) in _CAL else None
    d = date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))
    step = 1 if n > 0 else -1
    left = abs(n)
    while left > 0:
        d += timedelta(days=1) * step
        s = d.strftime("%Y%m%d")
        if (_is_fwd_td(s, d) if step > 0 else s in _CAL):
            left -= 1
        # 安全阀: 最多扫 400 天
        if abs((d - date(int(d8[:4]), int(d8[4:6]), int(d8[6:8]))).days) > 400:
            return None
    return d.strftime("%Y%m%d")


def td_between(a, b):
    """[a,b] 闭区间内交易日数(含端点; 无序自动交换)。
    覆盖区(<=asof)用真实日历; 超出 asof 的未来区按工作日前向外推
    (法定节假日未知→视为交易日; 与 add_td_days/next_td 同口径,
    TTL 判定方向保守=可能略早过期, 撮合不受影响)。"""
    _load()
    a, b = str(a), str(b)
    if a > b:
        a, b = b, a
    if _LATEST is None or b <= _LATEST:
        return sum(1 for d in _CAL if a <= d <= b)
    # 缓存区内直接计数
    n = sum(1 for d in _CAL if a <= d <= b)
    # 超出 asof 的前向外推区
    from datetime import date, timedelta
    dl = date(int(_LATEST[:4]), int(_LATEST[4:6]), int(_LATEST[6:8])) + timedelta(days=1)
    start = max(a, dl.strftime("%Y%m%d"))
    if start <= b:
        d = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
        de = date(int(b[:4]), int(b[4:6]), int(b[6:8]))
        while d <= de:
            if d.weekday() < 5:
                n += 1
            d += timedelta(days=1)
    return n


def asof_latest():
    _load()
    return _LATEST


if __name__ == "__main__":
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    _load()
    print("交易日数:", len(_CAL), "最新:", _LATEST)
    # 冒烟: 2026-09 周边界(09-11 周五开市, 09-12/13 周末休市)
    print("is_td(20260911):", is_td("20260911"), "| is_td(20260912):", is_td("20260912"),
          "| is_td(20260913):", is_td("20260913"))
    print("next_td(20260911):", next_td("20260911"), "(外推: 下一工作日周一 09-14)")
    print("add_td_days(20260911, 3):", add_td_days("20260911", 3), "(外推 3 个交易日: 周一/二/三)")
    print("td_between(20260907, 20260913):", td_between("20260907", "20260913"), "(近一周交易日数)")
    # 节假日核查: 国庆 10/1(2026 数据未至, 应 False 或未来外推区)
    print("is_td(20261001):", is_td("20261001"))
    # 回溯方向: 2024 春节前后
    print("prev_td(20240219):", prev_td("20240219"), "(春节后首日之前)")
    print("td_between(20240205, 20240219):", td_between("20240205", "20240219"), "(春节周交易日数, 应少)")
    # PASS/FAIL 汇总
    checks = [
        ("20260911 是交易日", is_td("20260911") is True),
        ("20260912 周六休市", is_td("20260912") is False),
        ("next_td 跨周末外推周一", next_td("20260911") == "20260914"),
        ("add_td_days 前向", add_td_days("20260911", 3) == "20260916"),
        ("td_between 周内=5", td_between("20260907", "20260913") == 5),
        ("春节周交易日=5(2/5-8+2/19)", td_between("20240205", "20240219") == 5),
        ("春节休市区间(2/9-2/18)=0", td_between("20240209", "20240218") == 0),
    ]
    p = sum(1 for _, ok in checks if ok)
    print(f"\n结果: PASS={p} FAIL={len(checks)-p}")
    sys.exit(0 if p == len(checks) else 1)
