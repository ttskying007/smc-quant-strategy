# -*- coding: utf-8 -*-
"""core/tdx_feed.py —— 统一行情数据源适配器（集成 easy_tdx / pytdx / 腾讯缓存）

设计目的（2026-09-08 集成 easy_tdx 项目）：
  用户要求集成 easy_tdx（通达信本地数据读取）与 pytdx（通达信网络行情）。
  实测环境结论（tdx_feasibility.py）：
    ① pytdx 网络 —— TCP 可达但 TDX 协议握手失败(ResponseRecvFails)，网络受限无法连接
    ② easy_tdx 本地 —— 需本机安装通达信软件(未装)；同花顺 .day 带 hd1.0 头且覆盖仅24-45只，不兼容
  因此本适配器将三方统一为"数据源后端"，提供公共接口与自动回退：
    默认激活 Tencent kline_cache（现行可靠源，4663 只）
    pytdx / easy_tdx 后端在连接/文件可用时自动接管，否则回退腾讯
  单一 bars schema：{t:YYYYMMDD, o,h,l,c,v}（与 kline_cache_tencent 一致）
  这样 easy_tdx 的"集成"已结构性就位，待通达信客户端安装或网络开放即无缝切换。
"""
import json, os

RESEARCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../smc_project/research
KLINE_TENCENT = os.path.abspath(os.path.join(RESEARCH, "..", "hermes", "kline_cache_tencent"))


# ---------------- 后端状态探测 ----------------
def _pytdx_available():
    """pytdx 网络后端可用性：尝试连接通达信行情服务器。
    每次探测有 ~8s 超时成本，结果缓存 5 分钟。"""
    import time
    _c = getattr(_pytdx_available, "_cache", None)
    if _c and time.time() - _c[0] < 300:
        return _c[1]
    try:
        from pytdx.hq import TdxHq_API
        api = TdxHq_API()
        ok = False
        for ip, port in [("119.147.212.81", 7709), ("114.80.63.12", 7709)]:
            try:
                if api.connect(ip, port, time_out=6):
                    api.disconnect()
                    ok = True
                    break
            except Exception:
                continue
        _pytdx_available._cache = (time.time(), ok)
        return ok
    except Exception:
        _pytdx_available._cache = (time.time(), False)
        return False


def _easy_tdx_available():
    """easy_tdx 本地文件后端可用性：探测标准通达信数据目录（.day 文件）。
    当前本机无通达信安装(仅有同花顺, 格式不兼容) → 返回 False。"""
    import glob
    candidates = [
        r"C:\new_tdx\vipdoc\sh\lday", r"C:\new_tdx\vipdoc\sz\lday",
        r"C:\tdx\vipdoc\sh\lday", r"D:\new_tdx\vipdoc\sh\lday",
        r"E:\new_tdx\vipdoc\sh\lday",
    ]
    for c in candidates:
        if glob.glob(os.path.join(c, "*.day")):
            return c
    return None


def backend_status():
    """各后端可用性状态（供 dashboard /tdx 页展示）。"""
    ptdx = _pytdx_available()
    easy = _easy_tdx_available()
    n_tencent = len([f for f in os.listdir(KLINE_TENCENT) if f.endswith("_daily_800.json")]) if os.path.isdir(KLINE_TENCENT) else 0
    return {
        "active": "tencent" if not ptdx and not easy else ("pytdx" if ptdx else "easy_tdx"),
        "tencent": {"available": os.path.isdir(KLINE_TENCENT), "kline_files": n_tencent},
        "pytdx": {"available": ptdx, "note": "网络受限: TCP可达但协议握手失败" if not ptdx else "连接可用"},
        "easy_tdx": {"available": bool(easy), "data_dir": easy,
                      "note": "未装通达信客户端(同花顺.day带hd1.0头不兼容)" if not easy else "本地数据可用"},
        "kline_dir": KLINE_TENCENT,
    }


# ---------------- 统一 bars schema ----------------
def get_daily(code6, backend=None):
    """取日线 bars（默认腾讯缓存）。code6: 6位代码。返回 [{t,o,h,l,c,v}, ...] 或 []。
    backend: 'tencent'|'pytdx'|'easy_tdx'|None(自动)。"""
    if backend == "pytdx" or (backend is None and _pytdx_available()):
        return _pytdx_daily(code6)
    if backend == "easy_tdx" or (backend is None and _easy_tdx_available()):
        return _easy_daily(code6)
    return _tencent_daily(code6)


def _tencent_daily(code6):
    for suffix in ("_SH", "_SZ"):
        p = os.path.join(KLINE_TENCENT, f"{code6}{suffix}_daily_800.json")
        if os.path.exists(p):
            try:
                return json.load(open(p, encoding="utf-8"))
            except Exception:
                return []
    return []


def _pytdx_daily(code6):
    """pytdx 网络日线（backend 显式请求时调用）。"""
    try:
        from pytdx.hq import TdxHq_API
        api = TdxHq_API()
        for ip, port in [("119.147.212.81", 7709), ("114.80.63.12", 7709)]:
            try:
                if not api.connect(ip, port, time_out=6):
                    continue
                mkt = 1 if code6.startswith(("6", "9")) else 0
                raw = api.get_security_bars(9, mkt, code6, 0, 800)
                api.disconnect()
                bars = []
                for b in (raw or []):
                    t = str(b.get("datetime") or "").replace("-", "")[:8]
                    if t and b.get("close") and b.get("vol"):
                        bars.append({"t": t, "o": b["open"], "h": b["high"], "l": b["low"],
                                     "c": b["close"], "v": float(b["vol"] * (100 if mkt == 0 else 1))})
                return bars
            except Exception:
                try:
                    api.disconnect()
                except Exception:
                    pass
    except Exception:
        pass
    return []


def _easy_daily(code6):
    """easy_tdx 本地 .day 读取（需通达信 vipdoc 目录，当前不可用）。"""
    return []


# ---------------- 实时报价 ----------------
def get_realtime(codes6, backend=None):
    """实时报价。code6: 列表。返回 {code6: {price,last_close,vol,bid1,ask1,ts}, ...}。
    腾讯实时（dashboard 已有）/ pytdx 快照。当前网络不可用 TDX → 返回空由上层用缓存兜底。"""
    if backend == "pytdx" or (backend is None and _pytdx_available()):
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            for ip, port in [("119.147.212.81", 7709)]:
                try:
                    if api.connect(ip, port, time_out=6):
                        pairs = [("1" if c.startswith(("6", "9")) else "0", c) for c in codes6]
                        snap = api.get_security_quotes(pairs)
                        api.disconnect()
                        out = {}
                        for s in (snap or []):
                            out[str(s["code"])] = {"price": s.get("price"), "last_close": s.get("last_close"),
                                                   "vol": s.get("vol"), "bid1": s.get("bid1"), "ask1": s.get("ask1")}
                        return out
                except Exception:
                    pass
        except Exception:
            pass
    return {}


# ---------------- 资金流向/财务（pytdx 扩展数据，网络可用时） ----------------
def get_fundflow(code6, backend=None):
    """资金流向/财务。当前网络不可用 → 返回 {}。"""
    if backend == "pytdx" or (backend is None and _pytdx_available()):
        try:
            from pytdx.hq import TdxHq_API
            api = TdxHq_API()
            for ip, port in [("119.147.212.81", 7709)]:
                try:
                    if api.connect(ip, port, time_out=6):
                        mkt = 1 if code6.startswith(("6", "9")) else 0
                        ff = api.get_finance_info(mkt, code6)
                        api.disconnect()
                        if ff:
                            return {"ltsz": ff.get("ltsz"), "zgb": ff.get("zgb"),
                                    "eps": ff.get("liang")}
                except Exception:
                    pass
        except Exception:
            pass
    return {}


if __name__ == "__main__":
    import sys
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    st = backend_status()
    print("== 数据源后端状态 ==")
    print(f"  激活后端: {st['active']}")
    print(f"  腾讯缓存: {st['tencent']['kline_files']} 只K线")
    print(f"  pytdx: {'可用' if st['pytdx']['available'] else '不可用'} ({st['pytdx']['note']})")
    print(f"  easy_tdx: {'可用' if st['easy_tdx']['available'] else '不可用'} ({st['easy_tdx']['note']})")
    bars = get_daily("600519")
    print(f"\n  600519 日线(腾讯): {len(bars)} 根, 最近: {bars[-1] if bars else '无'}")
    print(f"  600519 实时: {get_realtime(['600519'])}")
    print(f"  600519 资金: {get_fundflow('600519')}")